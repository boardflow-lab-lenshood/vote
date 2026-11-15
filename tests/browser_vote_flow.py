"""Exercise real HTTP, cookies and refreshes in an isolated Chromium session."""
import json
from pathlib import Path
import sys
from threading import Thread
from unittest.mock import patch
from urllib.parse import urlencode, urlparse

from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app as vote_app
from test_vote_validation import INVALID_FORMS


def main():
    artifacts = ROOT / ".test-artifacts"
    artifacts.mkdir(exist_ok=True)
    report = {"invalid_requests": 0, "valid_requests": 0, "page_errors": []}
    with patch.object(vote_app.Redis, "rpush", autospec=True, return_value=1) as writes, patch.object(
        vote_app.Redis, "execute_command", side_effect=AssertionError("Unexpected Redis network command")
    ):
        server = make_server("127.0.0.1", 0, vote_app.app)
        url = "http://127.0.0.1:" + str(server.server_port)
        report["url"] = url
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                try:
                    # Keep the test independent of third-party fonts, icons and jQuery CDNs.
                    browser_context = browser.new_context(viewport={"width": 1000, "height": 800})
                    browser_context.route("**/*", lambda route: route.continue_()
                                          if urlparse(route.request.url).netloc == urlparse(url).netloc
                                          else route.abort())
                    page = browser_context.new_page()
                    page.on("pageerror", lambda error: report["page_errors"].append(str(error)))
                    for existing_vote in (None, "a", "b"):
                        browser_context.clear_cookies()
                        if existing_vote:
                            browser_context.add_cookies([{"name": "vote", "value": existing_vote, "url": url}])
                        page.goto(url, wait_until="domcontentloaded")
                        voter_id = next(c["value"] for c in browser_context.cookies() if c["name"] == "voter_id")
                        for form in INVALID_FORMS:
                            before = writes.call_count
                            result = page.evaluate("""async body => {
                                const response = await fetch('/', {method: 'POST',
                                    headers: {'Content-Type': 'application/x-www-form-urlencoded'}, body});
                                return {status: response.status, contentType: response.headers.get('Content-Type'),
                                    payload: await response.json()};
                            }""", urlencode(form))
                            assert result == {"status": 400, "contentType": "application/json",
                                              "payload": {"error": "invalid_vote"}}, result
                            assert writes.call_count == before
                            cookies = {c["name"]: c["value"] for c in browser_context.cookies()}
                            assert cookies.get("vote") == existing_vote
                            assert cookies["voter_id"] == voter_id
                            page.reload(wait_until="domcontentloaded")
                            confirmation = page.locator("#vote-confirmation")
                            if existing_vote:
                                assert confirmation.get_attribute("data-vote") == existing_vote
                            else:
                                assert confirmation.count() == 0
                            assert writes.call_count == before
                            report["invalid_requests"] += 1

                    for choices in (("a", "b"), ("b", "a")):
                        browser_context.clear_cookies()
                        page.goto(url, wait_until="domcontentloaded")
                        voter_id = next(c["value"] for c in browser_context.cookies() if c["name"] == "voter_id")
                        for choice in choices:
                            before = writes.call_count
                            with page.expect_navigation(wait_until="domcontentloaded") as pending:
                                page.locator('button[value="' + choice + '"]').click()
                            response = pending.value
                            assert response.status == 200
                            assert response.headers["content-type"].startswith("text/html")
                            page.wait_for_selector("#vote-confirmation")
                            assert page.locator("#vote-confirmation").get_attribute("data-vote") == choice
                            cookies = {c["name"]: c["value"] for c in browser_context.cookies()}
                            assert cookies["vote"] == choice and cookies["voter_id"] == voter_id
                            assert writes.call_count == before + 1
                            redis, queue, raw = writes.call_args.args
                            assert isinstance(redis, vote_app.Redis) and queue == "votes" and isinstance(raw, str)
                            assert json.loads(raw) == {"voter_id": voter_id, "vote": choice}
                            # Return to GET before reloading: reloading the POST page resubmits its form.
                            page.goto(url, wait_until="domcontentloaded")
                            page.reload(wait_until="domcontentloaded")
                            assert page.locator("#vote-confirmation").get_attribute("data-vote") == choice
                            assert writes.call_count == before + 1
                            report["valid_requests"] += 1
                    page.screenshot(path=str(artifacts / "vote-confirmation.png"), full_page=True)
                    report["redis_writes"] = writes.call_count
                    report["isolation"] = "127.0.0.1 ephemeral HTTP; Redis.rpush spy; Redis commands rejected; external CDN blocked"
                finally:
                    browser.close()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
    report["page_errors"] = sorted(set(report["page_errors"]))
    report["status"] = "pass"
    (artifacts / "browser-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
