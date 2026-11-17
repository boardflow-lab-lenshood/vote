"""Real-browser checks against isolated running vote/result apps.

Requires playwright + Chromium, redis-py, and card-local service URLs.
Run explicitly; browser/runtime setup is separate from unit-test discovery.
Database changes below are test fixtures, not worker end-to-end verification.
"""
import json
import os
from pathlib import Path
import subprocess
from urllib.parse import parse_qs
import uuid

from playwright.sync_api import expect, sync_playwright
from redis import Redis


ARTIFACTS = Path(os.environ.get("BROWSER_ARTIFACTS", ".local/browser"))
VOTE_URL = os.environ.get("VOTE_URL", "http://127.0.0.1:43811")
CUSTOM_VOTE_URL = os.environ.get("CUSTOM_VOTE_URL", "http://127.0.0.1:43813")
RESULT_URL = os.environ.get("RESULT_URL", "http://127.0.0.1:43812")


def semantics(page, heading, title, name):
    expect(page.locator("html")).to_have_attribute("lang", "zh-CN")
    expect(page.locator("main")).to_have_count(1)
    expect(page.get_by_role("main")).to_have_count(1)
    expect(page.locator("h1")).to_have_count(1)
    expect(page.get_by_role("heading", level=1)).to_have_text(heading)
    expect(page.locator("main h1")).to_be_visible()
    expect(page).to_have_title(title)
    session = page.context.new_cdp_session(page)
    tree = session.send("Accessibility.getFullAXTree")["nodes"]
    session.detach()
    mains = [node for node in tree if node.get("role", {}).get("value") == "main"]
    headings = [node for node in tree if node.get("role", {}).get("value") == "heading" and any(
        prop["name"] == "level" and prop["value"].get("value") == 1
        for prop in node.get("properties", [])
    )]
    assert len(mains) == 1, mains
    assert len(headings) == 1 and headings[0]["name"]["value"] == heading, headings
    (ARTIFACTS / f"{name}-ax.json").write_text(json.dumps(tree, ensure_ascii=False, indent=2))


def check_vote(browser, redis, url, labels, prefix):
    reports = []
    heading = f"{labels[0]} vs {labels[1]}!"
    for method in ("mouse", "keyboard"):
        for index, choice in enumerate(("a", "b")):
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.goto(url, wait_until="networkidle")
            semantics(page, heading, heading, f"{prefix}-{method}-{choice}")
            expect(page.locator("main form[method=POST] button[type=submit][name=vote]")).to_have_count(2)
            before = redis.llen("votes")
            with page.expect_navigation(wait_until="networkidle") as navigation:
                if method == "mouse":
                    page.get_by_role("button", name=labels[index], exact=True).click()
                else:
                    page.keyboard.press("Tab")
                    if index == 1:
                        page.keyboard.press("Tab")
                    expect(page.get_by_role("button", name=labels[index], exact=True)).to_be_focused()
                    page.keyboard.press("Enter")
            response = navigation.value
            assert response.status == 200
            assert response.request.method == "POST"
            assert parse_qs(response.request.post_data)["vote"] == [choice]
            expect(page.locator("#vote-confirmation")).to_have_text(f"你已投给{labels[index]}")
            semantics(page, heading, heading, f"{prefix}-{method}-{choice}-submitted")
            assert redis.llen("votes") == before + 1
            assert json.loads(redis.lindex("votes", -1))["vote"] == choice
            # The existing form returns a POST response. Reopen with GET before
            # refreshing to verify cookie readback without resubmitting the vote.
            page.goto(url, wait_until="networkidle")
            page.reload(wait_until="networkidle")
            expect(page.locator("#vote-confirmation")).to_have_text(f"你已投给{labels[index]}")
            assert redis.llen("votes") == before + 1
            semantics(page, heading, heading, f"{prefix}-{method}-{choice}-reloaded")
            page.screenshot(path=str(ARTIFACTS / f"{prefix}-{method}-{choice}.png"), full_page=True)
            reports.append({"page": prefix, "method": method, "choice": choice, "post_status": response.status, "queue_delta": 1, "refresh_preserves_confirmation": True})
            context.close()
    return reports


def check_result(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    page = context.new_page()
    page.goto(RESULT_URL, wait_until="networkidle")
    page.wait_for_function("getComputedStyle(document.body).opacity === '1'")
    semantics(page, "实时投票结果", "猫派 vs 狗派 -- Result", "result")
    for element_id in ("count-a", "count-b", "total-count"):
        expect(page.locator(f"main #{element_id}")).to_be_visible()
    page.evaluate("""() => {
      window.testScores = [];
      window.testSocket = io.connect(location.origin);
      window.testSocket.on('scores', data => window.testScores.push(JSON.parse(data)));
    }""")
    page.wait_for_function("window.testScores.length > 0")
    # Seed isolated database fixtures directly. This does not exercise worker.
    fixture = f"browser-fixture-{uuid.uuid4().hex}"
    subprocess.run([
        "node", "-e",
        "const {Client}=require('pg'); (async()=>{const c=new Client({connectionString:process.env.TEST_DATABASE_URL}); await c.connect(); await c.query('INSERT INTO votes (id,vote) VALUES ($1,$2),($3,$4)',[process.argv[1]+'-a','a',process.argv[1]+'-b','b']); await c.end();})().catch(e=>{console.error(e);process.exit(1)});",
        fixture,
    ], cwd=os.environ["RESULT_REPO"], check=True)
    response = page.request.get(f"{RESULT_URL}/api/results")
    assert response.status == 200
    counts = response.json()
    assert set(counts) == {"a", "b"}, counts
    counts["total"] = counts["a"] + counts["b"]
    expect(page.locator("main #count-a")).to_have_text(str(counts["a"]), timeout=10000)
    expect(page.locator("main #count-b")).to_have_text(str(counts["b"]), timeout=10000)
    expect(page.locator("main #total-count")).to_have_text(str(counts["total"]), timeout=10000)
    page.wait_for_function("counts => window.testScores.some(s => s.a === counts.a && s.b === counts.b)", arg=counts)
    scores = page.evaluate("window.testScores")
    assert all(set(score) == {"a", "b"} for score in scores), scores
    page.screenshot(path=str(ARTIFACTS / "result-desktop.png"), full_page=True)
    page.reload(wait_until="networkidle")
    expect(page.locator("main #total-count")).to_have_text(str(counts["total"]), timeout=10000)
    semantics(page, "实时投票结果", "猫派 vs 狗派 -- Result", "result-reloaded")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.locator("main h1")).to_be_visible()
    page.screenshot(path=str(ARTIFACTS / "result-mobile.png"), full_page=True)
    context.close()
    return {"page": "result", "actual_scores_received": scores, "database_fixture_counts": counts, "refresh_preserves_counts": True, "worker_deployment_verified": False}


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    redis = Redis(host="127.0.0.1", port=int(os.environ.get("TEST_REDIS_PORT", "46379")))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            report = {"browser": browser.version, "vote": check_vote(browser, redis, VOTE_URL, ("猫派", "狗派"), "vote-default") + check_vote(browser, redis, CUSTOM_VOTE_URL, ("茶派", "咖啡派"), "vote-custom"), "result": check_result(browser)}
            (ARTIFACTS / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            browser.close()
            redis.close()


if __name__ == "__main__":
    main()
