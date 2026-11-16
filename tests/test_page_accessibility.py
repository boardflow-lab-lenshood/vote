import unittest
from html.parser import HTMLParser
from unittest.mock import Mock, patch

import app as vote_app


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.elements = []
        self.headings = []
        self.title = []

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs), tuple(self.stack)))
        if tag not in ('meta', 'link', 'input', 'br', 'img', 'hr'):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.stack:
            del self.stack[len(self.stack) - 1 - self.stack[::-1].index(tag):]

    def handle_data(self, data):
        if 'h1' in self.stack:
            self.headings.append(data)
        if 'title' in self.stack:
            self.title.append(data)


class PageAccessibilityTests(unittest.TestCase):
    def parse(self, response):
        self.assertEqual(response.status_code, 200)
        page = PageParser()
        page.feed(response.get_data(as_text=True))
        return page

    def assert_page_structure(self, page, title):
        roots = [attrs for tag, attrs, _ in page.elements if tag == 'html']
        self.assertEqual(roots, [{'lang': 'zh-CN'}])
        self.assertEqual(sum(tag == 'main' for tag, _, _ in page.elements), 1)
        headings = [parents for tag, _, parents in page.elements if tag == 'h1']
        self.assertEqual(len(headings), 1)
        self.assertIn('main', headings[0])
        self.assertEqual(''.join(page.headings), title)
        self.assertEqual(''.join(page.title), title)
        forms = [(attrs, parents) for tag, attrs, parents in page.elements
                 if tag == 'form']
        self.assertEqual(len(forms), 1)
        self.assertEqual(forms[0][0]['method'], 'POST')
        self.assertIn('main', forms[0][1])
        buttons = [(attrs, parents) for tag, attrs, parents in page.elements
                   if tag == 'button']
        self.assertEqual(len(buttons), 2)
        self.assertEqual([attrs['value'] for attrs, _ in buttons], ['a', 'b'])
        for attrs, parents in buttons:
            self.assertEqual(attrs['type'], 'submit')
            self.assertEqual(attrs['name'], 'vote')
            self.assertIn('form', parents)
            self.assertIn('main', parents)

    def test_main_heading_uses_configured_labels(self):
        for a, b in [('猫派', '狗派'), ('红 & 蓝', '绿 <黄>')]:
            with self.subTest(a=a, b=b), patch.object(vote_app, 'option_a', a), \
                    patch.object(vote_app, 'option_b', b):
                with vote_app.app.test_client() as client:
                    self.assert_page_structure(self.parse(client.get('/')),
                                               f'{a} vs {b}!')

    def test_submission_keeps_semantics_and_reload_does_not_vote_again(self):
        redis = Mock()
        with patch.object(vote_app, 'get_redis', return_value=redis):
            with vote_app.app.test_client() as client:
                title = f'{vote_app.option_a} vs {vote_app.option_b}!'
                self.assert_page_structure(self.parse(client.post('/', data={'vote': 'b'})),
                                           title)
                self.assert_page_structure(self.parse(client.get('/')), title)
        redis.rpush.assert_called_once()


if __name__ == '__main__':
    unittest.main()
