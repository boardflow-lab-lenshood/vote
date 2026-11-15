"""Render real templates without Redis; browser coverage lives in browser_vote_accessibility.py."""
from html.parser import HTMLParser
import unittest
from unittest.mock import patch

import app as vote_app


OPTION_CASES = (
    (vote_app.option_a, vote_app.option_b),
    ("春天", vote_app.option_b),
    (vote_app.option_a, "秋天"),
    ("咖啡", "茶"),
    ('中文甲\' " & < > <img src=x onerror="window.injected=1"> &amp; \\',
     '中文乙" \' & < > </script><script>window.injected=2</script> &#39; \\'),
    ("", ""),
)


class VotePageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.buttons = []
        self.forms = []
        self.tags = []
        self.current_button = None

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        if tag == "form":
            self.forms.append(dict(attrs))
        if tag == "button":
            self.current_button = {"attrs": attrs, "text": "", "children": []}
            self.buttons.append(self.current_button)
        elif self.current_button is not None:
            self.current_button["children"].append(tag)

    def handle_data(self, data):
        if self.current_button is not None:
            self.current_button["text"] += data

    def handle_endtag(self, tag):
        if tag == "button":
            self.current_button = None


class VoteAccessibilityTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(
            vote_app.Redis, "execute_command",
            side_effect=AssertionError("Unexpected Redis command in isolated test"),
        ))

    def test_current_options_are_named_and_escaped_in_each_cookie_state(self):
        for option_a, option_b in OPTION_CASES:
            with patch.object(vote_app, "option_a", option_a), patch.object(vote_app, "option_b", option_b):
                client = vote_app.app.test_client()
                self.assertEqual(client.get("/api/options").get_json(), {"a": option_a, "b": option_b})
                for existing_vote in (None, "a", "b"):
                    with self.subTest(options=(option_a, option_b), existing_vote=existing_vote):
                        client.delete_cookie("vote")
                        if existing_vote:
                            client.set_cookie("vote", existing_vote)
                        response = client.get("/")
                        self.assertEqual(response.status_code, 200)
                        page = VotePageParser()
                        page.feed(response.get_data(as_text=True))
                        self.assertEqual(len(page.buttons), 2)
                        self.assertEqual(len(page.forms), 1)
                        self.assertEqual(page.forms[0]["method"], "POST")
                        self.assertEqual(page.forms[0]["action"], "/")
                        self.assertNotIn("img", page.tags)
                        self.assertEqual(page.tags.count("script"), 3 if existing_vote else 2)
                        for button, choice, option in zip(page.buttons, ("a", "b"), (option_a, option_b)):
                            self.assertEqual(dict(button["attrs"]), {
                                "id": choice, "type": "submit", "name": "vote",
                                "class": choice, "value": choice, "aria-label": "投给" + option,
                            })
                            self.assertEqual(len(button["attrs"]), 6)
                            self.assertEqual(button["text"], option)
                            self.assertEqual(button["children"], [])


if __name__ == "__main__":
    unittest.main()
