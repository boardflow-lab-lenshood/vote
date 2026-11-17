import importlib
import json
import os
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from playwright.sync_api import expect, sync_playwright
from werkzeug.serving import make_server

from test_vote_accessibility import OPTION_SETS, configured_app


class VoteBrowserAccessibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch()
        except Exception:
            cls.playwright.stop()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def assert_state(self, page, options, selected):
        for choice, label in options.items():
            button = page.locator("#" + choice)
            expect(button).to_have_accessible_name("投给" + label)
            self.assertEqual(page.get_by_role(
                "button", name="投给" + label, exact=True,
            ).get_attribute("id"), choice)
            self.assertEqual(button.get_attribute("type"), "submit")
            self.assertEqual(button.get_attribute("name"), "vote")
            self.assertEqual(button.get_attribute("value"), choice)
            self.assertEqual(button.text_content(), label + (" " if choice == selected else ""))
            if choice == selected:
                expect(button).to_be_disabled()
                expect(button.locator("i.fa.fa-check-circle[aria-hidden=true]")).to_have_count(1)
                expect(button.locator("*")).to_have_count(1)
            else:
                expect(button).to_be_enabled()
                expect(button.locator("*")).to_have_count(0)
                if selected is not None:
                    expect(button).to_have_css("opacity", "0.5")
        self.assertIsNone(page.evaluate("window.optionExecuted"))
        expect(page.locator("#choice img, #choice script, #choice b")).to_have_count(0)

    def test_native_submission_switch_refresh_and_special_characters(self):
        for index, options in enumerate(OPTION_SETS):
            for first, second in (("a", "b"), ("b", "a")):
                with self.subTest(options=options, first=first):
                    vote_app = configured_app(options)
                    redis = MagicMock()
                    server = make_server("127.0.0.1", 0, vote_app.app)
                    base_url = "http://127.0.0.1:" + str(server.server_port)
                    thread = threading.Thread(target=server.serve_forever, daemon=True)
                    context = self.browser.new_context()
                    errors = []
                    post_bodies = []
                    # The actual page scripts run; only remote CDN assets are blocked.
                    context.route("**/*", lambda route: (
                        route.continue_() if route.request.url.startswith(base_url + "/")
                        else route.abort()
                    ))
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("request", lambda request: (
                        post_bodies.append(request.post_data)
                        if request.method == "POST" else None
                    ))
                    try:
                        with patch.object(vote_app, "get_redis", return_value=redis):
                            thread.start()
                            response = page.goto(base_url + "/")
                            self.assertEqual(response.status, 200)
                            self.assert_state(page, options, None)
                            for choice in (first, second):
                                with page.expect_navigation(wait_until="load") as navigation:
                                    page.locator("#" + choice).click()
                                self.assertEqual(navigation.value.status, 200)
                                self.assert_state(page, options, choice)
                                self.assertEqual(page.locator("#vote-confirmation").text_content(),
                                                 "你已投给" + options[choice])
                                # Reopen with GET before refreshing: reloading a POST
                                # would intentionally resubmit the existing form.
                                self.assertEqual(page.goto(base_url + "/").status, 200)
                                self.assert_state(page, options, choice)
                                self.assertEqual(page.reload().status, 200)
                                self.assert_state(page, options, choice)
                            self.assertEqual(post_bodies, ["vote=" + first, "vote=" + second])
                            self.assertEqual(redis.rpush.call_count, 2)
                            voter_ids = []
                            for call, choice in zip(redis.rpush.call_args_list, (first, second)):
                                queue, payload = call.args
                                self.assertEqual(queue, "votes")
                                data = json.loads(payload)
                                self.assertEqual(data["vote"], choice)
                                voter_ids.append(data["voter_id"])
                            self.assertTrue(voter_ids[0])
                            self.assertEqual(voter_ids[0], voter_ids[1])
                            self.assertEqual(errors, [])
                            artifacts = os.getenv("VOTE_BROWSER_ARTIFACTS")
                            if artifacts:
                                directory = Path(artifacts)
                                directory.mkdir(parents=True, exist_ok=True)
                                page.screenshot(path=str(directory / f"options-{index}-{first}-{second}.png"))
                                (directory / f"options-{index}-{first}-{second}.aria.txt").write_text(
                                    page.locator("#choice").aria_snapshot(), encoding="utf-8",
                                )
                    finally:
                        context.close()
                        server.shutdown()
                        server.server_close()
                        thread.join(timeout=5)
                        importlib.reload(vote_app)


if __name__ == "__main__":
    unittest.main()
