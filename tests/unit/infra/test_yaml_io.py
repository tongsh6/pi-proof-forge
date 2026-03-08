import unittest

from tools.infra.persistence.yaml_io import dump_yaml, parse_simple_yaml, unquote


SAMPLE_YAML = """\
id: "ec-2026-001"
title: "High-peak order stability"
time_range: "2025-10 ~ 2026-01"
context: "Peak 5k QPS"
role_scope: "Owner"
actions:
  - "Refactored circuit breaker"
  - "Added canary rollback"
results:
  - "Failure rate dropped 43%"
stack:
  - "Java"
  - "Redis"
artifacts:
  - "postmortem.pdf"
tags:
  - "stability"
"""


class ParseScalarTests(unittest.TestCase):
    def test_parses_scalar_fields(self) -> None:
        doc = parse_simple_yaml(SAMPLE_YAML)
        self.assertEqual(doc["scalars"]["id"], "ec-2026-001")
        self.assertEqual(doc["scalars"]["title"], "High-peak order stability")
        self.assertEqual(doc["scalars"]["role_scope"], "Owner")

    def test_parses_scalar_without_quotes(self) -> None:
        text = "key: plain_value\n"
        doc = parse_simple_yaml(text)
        self.assertEqual(doc["scalars"]["key"], "plain_value")


class ParseListTests(unittest.TestCase):
    def test_parses_list_fields(self) -> None:
        doc = parse_simple_yaml(SAMPLE_YAML)
        self.assertEqual(doc["lists"]["actions"], ["Refactored circuit breaker", "Added canary rollback"])
        self.assertEqual(doc["lists"]["results"], ["Failure rate dropped 43%"])
        self.assertEqual(doc["lists"]["stack"], ["Java", "Redis"])
        self.assertEqual(doc["lists"]["artifacts"], ["postmortem.pdf"])
        self.assertEqual(doc["lists"]["tags"], ["stability"])


class EmptyLineAndCommentTests(unittest.TestCase):
    def test_skips_empty_lines_and_comments(self) -> None:
        text = "# This is a comment\n\nname: test\n\n# Another comment\nitems:\n  - one\n"
        doc = parse_simple_yaml(text)
        self.assertEqual(doc["scalars"]["name"], "test")
        self.assertEqual(doc["lists"]["items"], ["one"])


class UnquoteTests(unittest.TestCase):
    def test_unquote_double_quotes(self) -> None:
        self.assertEqual(unquote('"hello world"'), "hello world")

    def test_unquote_single_quotes(self) -> None:
        self.assertEqual(unquote("'hello world'"), "hello world")

    def test_unquote_no_quotes(self) -> None:
        self.assertEqual(unquote("plain"), "plain")

    def test_unquote_mismatched_quotes(self) -> None:
        self.assertEqual(unquote("\"hello'"), "\"hello'")


class DumpYamlTests(unittest.TestCase):
    def test_dump_produces_parseable_output(self) -> None:
        data = {
            "id": "ec-test-001",
            "title": "Test Card",
        }
        lists = {
            "results": ["Result A", "Result B"],
            "artifacts": ["doc.pdf"],
        }
        output = dump_yaml(data, lists)
        reparsed = parse_simple_yaml(output)
        self.assertEqual(reparsed["scalars"]["id"], "ec-test-001")
        self.assertEqual(reparsed["scalars"]["title"], "Test Card")
        self.assertEqual(reparsed["lists"]["results"], ["Result A", "Result B"])
        self.assertEqual(reparsed["lists"]["artifacts"], ["doc.pdf"])

    def test_dump_empty_list(self) -> None:
        data = {"id": "ec-001"}
        lists = {"items": []}
        output = dump_yaml(data, lists)
        self.assertIn("items:", output)


class RoundtripTests(unittest.TestCase):
    def test_parse_dump_key_fields_stable(self) -> None:
        doc = parse_simple_yaml(SAMPLE_YAML)
        output = dump_yaml(doc["scalars"], doc["lists"])
        reparsed = parse_simple_yaml(output)
        self.assertEqual(reparsed["scalars"]["id"], doc["scalars"]["id"])
        self.assertEqual(reparsed["scalars"]["title"], doc["scalars"]["title"])
        self.assertEqual(reparsed["lists"]["results"], doc["lists"]["results"])
        self.assertEqual(reparsed["lists"]["artifacts"], doc["lists"]["artifacts"])


if __name__ == "__main__":
    unittest.main()
