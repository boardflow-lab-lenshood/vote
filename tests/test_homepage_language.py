import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch


class PageParser(HTMLParser):
    VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.stack = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        element = {
            "tag": tag,
            "attrs": dict(attrs),
            "parent": self.stack[-1] if self.stack else None,
            "text": "",
        }
        self.elements.append(element)
        if tag not in self.VOID_TAGS:
            self.stack.append(element)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_data(self, data):
        for element in self.stack:
            element["text"] += data

    def find(self, tag, **attrs):
        return [
            element for element in self.elements
            if element["tag"] == tag
            and all(element["attrs"].get(key) == value for key, value in attrs.items())
        ]


class HomepageLanguageTest(unittest.TestCase):
    def load_app(self, options):
        environment = dict(os.environ)
        environment.pop("OPTION_A", None)
        environment.pop("OPTION_B", None)
        environment.update(options)
        environment_patch = patch.dict(os.environ, environment, clear=True)
        environment_patch.start()
        self.addCleanup(environment_patch.stop)

        # Load an isolated module so configuration never leaks into other tests.
        app_path = Path(__file__).resolve().parents[1] / "app.py"
        spec = importlib.util.spec_from_file_location("vote_page_test_app", app_path)
        module = importlib.util.module_from_spec(spec)
        modules_patch = patch.dict(sys.modules, {spec.name: module})
        modules_patch.start()
        self.addCleanup(modules_patch.stop)
        spec.loader.exec_module(module)
        module.app.config["TESTING"] = True
        return module

    def assert_page(self, response, option_a, option_b, vote=None):
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/html")
        page = PageParser(response.get_data(as_text=True))
        roots = [element for element in page.elements if element["parent"] is None]
        self.assertEqual([element["tag"] for element in roots], ["html"])
        self.assertEqual(roots[0]["attrs"].get("lang"), "zh-CN")
        self.assertEqual(len(page.find("html")), 1)

        title = f"{option_a} vs {option_b}!"
        self.assertEqual([node["text"] for node in page.find("title")], [title])
        self.assertEqual([node["text"] for node in page.find("h3")], [title])
        forms = page.find("form")
        self.assertEqual(len(forms), 1)
        form = forms[0]
        self.assertEqual(form["attrs"].get("id"), "choice")
        self.assertEqual(form["attrs"].get("method", "").upper(), "POST")
        self.assertEqual(form["attrs"].get("action"), "/")
        buttons = page.find("button")
        self.assertEqual(len(buttons), 2)
        for button, value, label in zip(buttons, ("a", "b"), (option_a, option_b)):
            self.assertIs(button["parent"], form)
            self.assertEqual(button["attrs"].get("id"), value)
            self.assertEqual(button["attrs"].get("type"), "submit")
            self.assertEqual(button["attrs"].get("name"), "vote")
            self.assertEqual(button["attrs"].get("value"), value)
            self.assertEqual(button["text"], label)
            if value != vote:
                self.assertNotIn("disabled", button["attrs"])

        confirmations = page.find("div", id="vote-confirmation")
        if vote is None:
            self.assertEqual(confirmations, [])
        else:
            self.assertEqual(len(confirmations), 1)
            self.assertEqual(confirmations[0]["attrs"].get("data-vote"), vote)
            label = option_a if vote == "a" else option_b
            self.assertEqual(confirmations[0]["text"], f"你已投给{label}")

    def check_voting_flow(self, options, option_a, option_b):
        module = self.load_app(options)
        client = module.app.test_client()
        redis = MagicMock()
        with patch.object(module, "get_redis", return_value=redis):
            self.assert_page(client.get("/"), option_a, option_b)
            voter_id = client.get_cookie("voter_id").value
            redis.rpush.assert_not_called()
            for vote in ("a", "b"):
                with self.subTest(vote=vote):
                    self.assert_page(client.post("/", data={"vote": vote}),
                                     option_a, option_b, vote)
                    self.assertEqual(client.get_cookie("vote").value, vote)
                    self.assertEqual(client.get_cookie("voter_id").value, voter_id)
                    queue, payload = redis.rpush.call_args.args
                    self.assertEqual(queue, "votes")
                    self.assertEqual(json.loads(payload), {"voter_id": voter_id, "vote": vote})
                    calls_before_refresh = redis.rpush.call_count
                    self.assert_page(client.get("/"), option_a, option_b, vote)
                    self.assertEqual(redis.rpush.call_count, calls_before_refresh)
            self.assertEqual(redis.rpush.call_count, 2)

    def test_default_page_language_and_voting_flow(self):
        self.check_voting_flow({}, "猫派", "狗派")

    def test_configured_page_language_and_voting_flow(self):
        self.check_voting_flow({"OPTION_A": "Tea", "OPTION_B": "Coffee"}, "Tea", "Coffee")


if __name__ == "__main__":
    unittest.main()
