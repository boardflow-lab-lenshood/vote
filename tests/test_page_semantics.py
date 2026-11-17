from html.parser import HTMLParser
import json
import unittest
from unittest.mock import MagicMock, patch

import app as vote_app


class PageParser(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.nodes = []
        self.stack = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "parents": self.stack[:], "text": ""}
        self.nodes.append(node)
        if tag not in {"base", "meta", "link", "input", "br", "hr", "img"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index]["tag"] == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data

    def find(self, tag):
        return [node for node in self.nodes if node["tag"] == tag]


class PageSemanticsTest(unittest.TestCase):
    def assert_page(self, response, option_a, option_b):
        self.assertEqual(response.status_code, 200)
        page = PageParser(response.get_data(as_text=True))
        self.assertEqual(page.find("html")[0]["attrs"]["lang"], "zh-CN")
        self.assertEqual(len(page.find("main")), 1)
        main = page.find("main")[0]
        self.assertEqual(len(page.find("h1")), 1)
        heading = page.find("h1")[0]
        self.assertIn(main, heading["parents"])
        self.assertEqual(heading["text"], f"{option_a} vs {option_b}!")
        self.assertEqual(page.find("title")[0]["text"], heading["text"])
        self.assertEqual(len(page.find("form")), 1)
        form = page.find("form")[0]
        self.assertIn(main, form["parents"])
        self.assertEqual(form["attrs"]["method"].upper(), "POST")
        self.assertEqual(form["attrs"]["action"], "/")
        buttons = page.find("button")
        self.assertEqual(len(buttons), 2)
        self.assertEqual([button["attrs"]["value"] for button in buttons], ["a", "b"])
        self.assertEqual([button["text"] for button in buttons], [option_a, option_b])
        for button in buttons:
            self.assertIn(main, button["parents"])
            self.assertIn(form, button["parents"])
            self.assertEqual(button["attrs"]["type"], "submit")
            self.assertEqual(button["attrs"]["name"], "vote")

    def test_initial_page_uses_current_labels_in_main_and_title(self):
        for option_a, option_b in [("猫派", "狗派"), ("茶 & 咖啡", "果汁 <汽水>")]:
            with self.subTest(labels=(option_a, option_b)):
                with patch.object(vote_app, "option_a", option_a), patch.object(
                    vote_app, "option_b", option_b
                ):
                    self.assert_page(vote_app.app.test_client().get("/"), option_a, option_b)

    def test_both_confirmations_preserve_semantics_and_form_contract(self):
        for choice in ("a", "b"):
            with self.subTest(choice=choice):
                redis = MagicMock()
                with patch.object(vote_app, "get_redis", return_value=redis):
                    client = vote_app.app.test_client()
                    response = client.post("/", data={"vote": choice})
                    self.assert_page(response, vote_app.option_a, vote_app.option_b)
                    self.assert_page(client.get("/"), vote_app.option_a, vote_app.option_b)
                queue, payload = redis.rpush.call_args.args
                self.assertEqual(queue, "votes")
                self.assertEqual(json.loads(payload)["vote"], choice)
                label = vote_app.option_a if choice == "a" else vote_app.option_b
                self.assertIn(f"你已投给{label}", response.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
