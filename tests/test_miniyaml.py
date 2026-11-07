import unittest

from umwayi import miniyaml
from umwayi.miniyaml import YamlError, loads


class MiniYamlTests(unittest.TestCase):
    def test_rules_shape(self):
        data = loads(
            """
rules:
  - id: a   # comment
    title: "Quoted: title"
    matchers:
      type: [x, 'y z', 3]
      flag: true
  - id: b
    matchers:
      - nope
"""
        )
        self.assertEqual(data["rules"][0]["id"], "a")
        self.assertEqual(data["rules"][0]["title"], "Quoted: title")
        self.assertEqual(data["rules"][0]["matchers"]["type"], ["x", "y z", 3])
        self.assertIs(data["rules"][0]["matchers"]["flag"], True)
        self.assertEqual(data["rules"][1]["matchers"], ["nope"])

    def test_yes_no_stay_strings(self):
        d = loads("a: no\nb: yes\nc: ask")
        self.assertEqual(d, {"a": "no", "b": "yes", "c": "ask"})

    def test_list_at_same_indent_as_key(self):
        self.assertEqual(loads("k:\n- a\n- b"), {"k": ["a", "b"]})

    def test_hash_inside_quotes_is_kept(self):
        self.assertEqual(loads('a: "x # y"'), {"a": "x # y"})

    def test_empty_inputs(self):
        self.assertIsNone(loads(""))
        self.assertIsNone(loads("# only a comment\n"))
        self.assertEqual(loads("a:"), {"a": None})

    def test_rejections(self):
        bad = [
            "a:\n\tb: 1",  # tab
            "a: 1\na: 2",  # duplicate key
            "a: &x 1",  # anchor
            "a: !tag 1",  # tag
            "a: |\n  text",  # block scalar
            "a: {b: 1}",  # flow mapping
            "a: [[1]]",  # nested list
            'a: "open',  # unterminated
            "a: [1, 2",  # unterminated list
            "a: 1\n  b: 2",  # bad indentation
            "- a\nb: 1",  # mixed
            "just text",  # not a mapping
            "a: b: c",  # stray colon
            'a: "bad \\q escape"',
        ]
        for text in bad:
            with self.subTest(text=text):
                with self.assertRaises(YamlError):
                    loads(text)

    def test_error_does_not_echo_content(self):
        try:
            loads("secret_token: abc123\nsecret_token: abc123")
        except YamlError as e:
            self.assertNotIn("abc123", str(e))
            self.assertNotIn("secret_token", str(e))
        else:
            self.fail("expected YamlError")


if __name__ == "__main__":
    unittest.main()
