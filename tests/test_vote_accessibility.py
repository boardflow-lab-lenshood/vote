import importlib
import json
import os
import unittest
from html.parser import HTMLParser
from unittest.mock import MagicMock, patch


OPTION_SETS = (
    {"a": "猫派", "b": "狗派"},
    {
        "a": '茶 " autofocus onfocus="window.optionExecuted=true" '
             '<img src=x onerror="window.optionExecuted=true"> & &#x41; \' \\',
        "b": "咖啡 </script><script>window.optionExecuted=true</script> "
             '<b>不是标签</b> &quot; " \' \\',
    },
)


def configured_app(options):
    import app as vote_app

    with patch.dict(os.environ, {"OPTION_A": options["a"], "OPTION_B": options["b"]}):
        importlib.reload(vote_app)
    return vote_app


class ButtonParser(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.buttons = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "button":
            attributes = dict(attrs)
            self.current = {"attrs": attributes, "text": "", "children": []}
            self.buttons[attributes["id"]] = self.current
        elif self.current is not None:
            self.current["children"].append(tag)

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "button":
            self.current = None


class VoteAccessibilityTest(unittest.TestCase):
    def tearDown(self):
        import app as vote_app

        importlib.reload(vote_app)

    def assert_buttons(self, response, options):
        self.assertEqual(response.status_code, 200)
        buttons = ButtonParser(response.get_data(as_text=True)).buttons
        self.assertEqual(set(buttons), {"a", "b"})
        for choice, label in options.items():
            with self.subTest(button=choice):
                self.assertEqual(buttons[choice]["attrs"], {
                    "id": choice,
                    "type": "submit",
                    "name": "vote",
                    "class": choice,
                    "value": choice,
                    "aria-label": "投给" + label,
                })
                self.assertEqual(buttons[choice]["text"], label)
                self.assertEqual(buttons[choice]["children"], [])

    def test_labels_and_escaping_in_all_cookie_states(self):
        for options in OPTION_SETS:
            vote_app = configured_app(options)
            for vote in (None, "a", "b"):
                with self.subTest(options=options, vote=vote):
                    client = vote_app.app.test_client()
                    if vote is not None:
                        client.set_cookie("vote", vote)
                    with patch.object(vote_app, "get_redis") as get_redis:
                        response = client.get("/")
                    get_redis.assert_not_called()
                    self.assert_buttons(response, options)

    def test_post_switch_and_refresh_preserve_labels_and_queue_contract(self):
        for options in OPTION_SETS:
            vote_app = configured_app(options)
            for first, second in (("a", "b"), ("b", "a")):
                with self.subTest(options=options, first=first):
                    client = vote_app.app.test_client()
                    client.set_cookie("voter_id", "accessibility-test-voter")
                    redis = MagicMock()
                    with patch.object(vote_app, "get_redis", return_value=redis):
                        for choice in (first, second):
                            response = client.post("/", data={"vote": choice})
                            self.assert_buttons(response, options)
                            self.assertEqual(client.get_cookie("vote").value, choice)
                            refreshed = client.get("/")
                            self.assert_buttons(refreshed, options)
                            self.assertIn('data-vote="' + choice + '"',
                                          refreshed.get_data(as_text=True))
                    self.assertEqual(redis.rpush.call_count, 2)
                    for call, choice in zip(redis.rpush.call_args_list, (first, second)):
                        queue, payload = call.args
                        self.assertEqual(queue, "votes")
                        self.assertEqual(json.loads(payload), {
                            "voter_id": "accessibility-test-voter", "vote": choice,
                        })


if __name__ == "__main__":
    unittest.main()
