"""Real HTTP/Chromium checks of names, escaping, selected states and form submissions."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import expect, sync_playwright
from redis.connection import Connection
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app as vote_app
from test_vote_accessibility import OPTION_CASES


def check_page(page, session, options, choice):
    expect(page.locator("#choice button")).to_have_count(2)
    assert page.locator("#choice").get_attribute("method") == "POST"
    assert page.locator("#choice").get_attribute("action") == "/"
    assert page.locator("img").count() == 0
    assert page.locator("script").count() == (3 if choice else 2)
    assert page.evaluate("window.injected === undefined")
    document = session.send("DOM.getDocument")["root"]["nodeId"]
    buttons = {}
    for value in ("a", "b"):
        button = page.locator("#" + value)
        name = "投给" + options[value]
        expect(button).to_have_accessible_name(name)
        expect(page.get_by_role("button", name=name, exact=True).and_(button)).to_have_count(1)
        assert button.is_disabled() == (choice == value)
        attrs = button.evaluate("el => Object.fromEntries(Array.from(el.attributes, a => [a.name, a.value]))")
        expected_attrs = {"id": value, "type": "submit", "name": "vote", "class": value,
                          "value": value, "aria-label": name}
        if choice == value:
            expected_attrs["disabled"] = ""
        elif choice:
            expected_attrs["style"] = "opacity: 0.5;"
        assert attrs == expected_attrs, attrs
        # The original option remains a text node, even when it looks like HTML or an entity.
        assert button.evaluate("el => Array.from(el.childNodes).filter(n => n.nodeType === 3)"
                               ".map(n => n.textContent).join('')") == options[value] + (" " if choice == value else "")
        expect(button.locator("i.fa-check-circle")).to_have_count(1 if choice == value else 0)
        assert button.locator("*").count() == (1 if choice == value else 0)
        if choice == value:
            assert button.locator("i").get_attribute("aria-hidden") == "true"
        node = session.send("DOM.querySelector", {"nodeId": document, "selector": "#" + value})["nodeId"]
        ax = session.send("Accessibility.getPartialAXTree", {"nodeId": node, "fetchRelatives": False})["nodes"][0]
        assert ax["role"]["value"] == "button"
        assert ax["name"]["value"] == name
        buttons[value] = {"computed_name": ax["name"]["value"], "role": ax["role"]["value"],
                          "disabled": button.is_disabled(), "dom": button.evaluate("el => el.outerHTML")}
    confirmation = page.locator("#vote-confirmation")
    expect(confirmation).to_have_count(1 if choice else 0)
    if choice:
        expect(confirmation).to_have_text("你已投给" + options[choice])
    return {"choice": choice, "options": options, "buttons": buttons}


def main():
    artifacts = ROOT / ".test-artifacts"
    artifacts.mkdir(exist_ok=True)
    report = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
              "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
              "environment": "isolated local HTTP, not a deployed candidate", "states": [],
              "submissions": [], "page_errors": [], "blocked_external_requests": []}
    try:
        with patch.object(vote_app.Redis, "rpush", autospec=True, return_value=1) as writes, patch.object(
            vote_app.Redis, "execute_command", side_effect=AssertionError("Unexpected Redis command")
        ), patch.object(Connection, "connect", side_effect=AssertionError("Redis network forbidden")):
            server = make_server("127.0.0.1", 0, vote_app.app)
            url = "http://127.0.0.1:" + str(server.server_port)
            report["url"] = url
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch(headless=True)
                    report["browser"] = "Chromium " + browser.version
                    try:
                        context = browser.new_context(viewport={"width": 1000, "height": 800})

                        def route_request(route):
                            if urlparse(route.request.url).netloc == urlparse(url).netloc:
                                route.continue_()
                            else:
                                report["blocked_external_requests"].append(route.request.url)
                                route.abort()

                        context.route("**/*", route_request)
                        page = context.new_page()
                        page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
                        session = context.new_cdp_session(page)
                        for case, (option_a, option_b) in enumerate(OPTION_CASES):
                            with patch.object(vote_app, "option_a", option_a), patch.object(vote_app, "option_b", option_b):
                                options = context.request.get(url + "/api/options").json()
                                assert options == {"a": option_a, "b": option_b}
                                for choice in (None, "a", "b"):
                                    context.clear_cookies()
                                    if choice:
                                        context.add_cookies([{"name": "vote", "value": choice, "url": url}])
                                    before = writes.call_count
                                    assert page.goto(url, wait_until="load").status == 200
                                    state = check_page(page, session, options, choice)
                                    state["case"] = case
                                    report["states"].append(state)
                                    assert writes.call_count == before
                                    if case == 0:
                                        page.screenshot(path=str(artifacts / ("accessibility-" + (choice or "none") + ".png")))
                                # Start from b, switch to a and back to b using the actual enabled buttons.
                                voter_id = next(c["value"] for c in context.cookies() if c["name"] == "voter_id")
                                for choice in ("a", "b"):
                                    before = writes.call_count
                                    with page.expect_navigation(wait_until="load") as navigation:
                                        page.locator("#" + choice).click()
                                    response = navigation.value
                                    assert response.status == 200
                                    assert response.request.method == "POST"
                                    assert urlparse(response.request.url).path == "/"
                                    assert parse_qs(response.request.post_data) == {"vote": [choice]}
                                    assert writes.call_count == before + 1
                                    redis, queue, message = writes.call_args.args
                                    assert isinstance(redis, vote_app.Redis) and queue == "votes"
                                    assert json.loads(message) == {"voter_id": voter_id, "vote": choice}
                                    check_page(page, session, options, choice)
                                    cookies = {c["name"]: c["value"] for c in context.cookies()}
                                    assert cookies["vote"] == choice and cookies["voter_id"] == voter_id
                                    # GET then refresh avoids intentionally resubmitting the POST.
                                    assert page.goto(url, wait_until="load").status == 200
                                    assert page.reload(wait_until="load").status == 200
                                    check_page(page, session, options, choice)
                                    assert writes.call_count == before + 1
                                    report["submissions"].append({"case": case, "choice": choice,
                                                                  "method": "POST", "refresh_verified": True})
                        assert not report["page_errors"], report["page_errors"]
                        report["redis_writes"] = writes.call_count
                        report["status"] = "pass"
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
    finally:
        if report["status"] != "pass":
            report["status"] = "fail"
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        report["blocked_external_requests"] = sorted(set(report["blocked_external_requests"]))
        output = artifacts / "vote-accessibility-report.json"
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "git_head": report["git_head"],
                          "states": len(report["states"]), "submissions": len(report["submissions"]),
                          "page_errors": report["page_errors"], "report": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
