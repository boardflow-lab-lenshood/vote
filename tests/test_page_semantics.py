import unittest
from html.parser import HTMLParser
from unittest.mock import patch

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
        if tag not in {"meta", "link", "base", "br", "img", "input"}:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1]["tag"] == tag:
            self.stack.pop()

    def handle_data(self, data):
        for node in self.stack:
            node["text"] += data

    def tagged(self, tag):
        return [node for node in self.nodes if node["tag"] == tag]


class PageSemanticsTests(unittest.TestCase):
    def test_current_options_title_and_complete_form_share_one_main(self):
        with patch.object(vote_app, "option_a", "红茶派"), patch.object(vote_app, "option_b", "绿茶派"):
            response = vote_app.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)
        page = PageParser(response.get_data(as_text=True))
        self.assertEqual(page.tagged("html")[0]["attrs"]["lang"], "zh-CN")
        self.assertEqual(len(page.tagged("main")), 1)
        self.assertEqual(len(page.tagged("h1")), 1)
        main = page.tagged("main")[0]
        heading = page.tagged("h1")[0]
        form, = page.tagged("form")
        self.assertIn(main, heading["parents"])
        self.assertIn(main, form["parents"])
        self.assertEqual(heading["text"], "红茶派 vs 绿茶派!")
        self.assertEqual(page.tagged("title")[0]["text"], heading["text"])
        self.assertEqual(form["attrs"]["method"], "POST")
        self.assertEqual(form["attrs"]["action"], "/")
        buttons = page.tagged("button")
        self.assertEqual([button["attrs"]["value"] for button in buttons], ["a", "b"])
        for button in buttons:
            self.assertEqual(button["attrs"]["type"], "submit")
            self.assertEqual(button["attrs"]["name"], "vote")
            self.assertIn(form, button["parents"])

    def test_both_submissions_keep_confirmation_inside_main(self):
        for choice, label in [("a", "红茶派"), ("b", "绿茶派")]:
            with self.subTest(choice=choice), patch.object(vote_app, "option_a", "红茶派"), patch.object(vote_app, "option_b", "绿茶派"), patch.object(vote_app, "get_redis") as redis:
                response = vote_app.app.test_client().post("/", data={"vote": choice})
            self.assertEqual(response.status_code, 200)
            redis.return_value.rpush.assert_called_once()
            page = PageParser(response.get_data(as_text=True))
            confirmation, = [node for node in page.nodes if node["attrs"].get("id") == "vote-confirmation"]
            self.assertEqual(confirmation["text"], "你已投给" + label)
            self.assertIn(page.tagged("main")[0], confirmation["parents"])


if __name__ == "__main__":
    unittest.main()
