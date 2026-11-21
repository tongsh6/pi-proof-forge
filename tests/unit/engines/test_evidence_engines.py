import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

from tools.domain.models import EvidenceCard


def _rule_extractor_class():
    module = import_module("tools.engines.evidence.rule_extractor")
    return module.RuleEvidenceExtractor


def _store_class():
    module = import_module("tools.engines.evidence.store")
    return module.EvidenceStore


def _llm_extractor_class():
    module = import_module("tools.engines.evidence.llm_extractor")
    return module.LLMEvidenceExtractor


class ResultReviewProtocolTests(unittest.TestCase):
    def _reply(self, *reviews):
        import json
        return json.dumps({"reviews": list(reviews)})

    def _review(self, index, quote=None, *, outcome="established"):
        return {"review_index": index, "outcome": outcome,
                "measurement_quote": quote, "rationale": "保留原文依据与条件"}

    def test_one_source_quote_cannot_merge_repeated_occurrences(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "响应时间减半。"
        scopes = [{"review_index": 0, "value": value,
                   "source": {"quote": "预测：" + value + "\n实测：" + value}}]
        with self.assertRaisesRegex(ValueError, "result_review"):
            parse_result_review(self._reply(self._review(0)), scopes)

    def test_unique_context_keeps_non_digit_measurement(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "测试环境固定输入下响应时间减半。"
        scopes = [{"review_index": 0, "value": value, "source": {"quote": "实测记录：" + value}}]
        result = self._review(0, value)
        self.assertEqual(parse_result_review(self._reply(result), scopes),
                         [{key: val for key, val in result.items() if key != "review_index"}])

    def test_measurement_quote_cannot_restore_conditions_missing_from_value(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "响应时间减半。"
        full = "测试环境固定输入下" + value
        scopes = [{"review_index": 0, "value": value, "source": {"quote": full}}]
        with self.assertRaisesRegex(ValueError, "result_review"):
            parse_result_review(self._reply(self._review(0, full)), scopes)

    def test_batch_reply_is_bound_by_index_instead_of_response_order(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "测试环境固定输入下响应时间减半。"
        scopes = [{"review_index": index, "value": value, "source": {"quote": label + value}}
                  for index, label in enumerate(("预测记录：", "已测记录："))]
        predicted, measured = self._review(0, outcome="not_established"), self._review(1, value)
        result = parse_result_review(self._reply(measured, predicted), scopes)
        self.assertEqual([review["outcome"] for review in result], ["not_established", "established"])
        self.assertEqual([review["measurement_quote"] for review in result], [None, value])

    def test_batch_requires_complete_unique_integer_indices_and_exact_keys(self):
        from tools.engines.evidence.validator import parse_result_review
        import json

        value = "测试环境固定输入下响应时间减半。"
        scopes = [{"review_index": index, "value": value, "source": {"quote": value}}
                  for index in range(2)]
        first, second = self._review(0), self._review(1, value)
        invalid = [
            {"reviews": [first]},
            {"reviews": [first, first]},
            {"reviews": [first, {**second, "review_index": True}]},
            {"reviews": [first, {**second, "review_index": 1.0}]},
            {"reviews": [first, {**second, "review_index": 2}]},
            {"reviews": [first, {**second, "review_index": -1}]},
            {"reviews": [first, {**second, "basis_sha256": "a" * 64}]},
            {"reviews": [first, {key: val for key, val in second.items() if key != "rationale"}]},
            {"reviews": [first, second], "basis_sha256": "a" * 64},
            first,
        ]
        for reply in invalid:
            with self.subTest(reply=reply), self.assertRaisesRegex(ValueError, "result_review"):
                parse_result_review(json.dumps(reply), scopes)

    def test_batch_rejects_duplicate_json_keys(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "测试环境固定输入下响应时间减半。"
        scopes = [{"review_index": 0, "value": value, "source": {"quote": value}}]
        reply = ('{"reviews":[{"review_index":0,"outcome":"not_established",'
                 '"outcome":"established","measurement_quote":null,"rationale":"重复结论"}]}')
        with self.assertRaisesRegex(ValueError, "result_review"):
            parse_result_review(reply, scopes)

    def test_each_index_uses_its_own_primary_occurrence(self):
        from tools.engines.evidence.validator import parse_result_review

        value = "测试环境固定输入下响应时间减半。"
        scopes = [{"review_index": 0, "value": value, "source": {"quote": value + "\n" + value}},
                  {"review_index": 1, "value": value, "source": {"quote": value}}]
        with self.assertRaisesRegex(ValueError, "result_review"):
            parse_result_review(self._reply(self._review(1, value), self._review(0)), scopes)

    def _basis_inputs(self):
        import hashlib

        value = "测试环境固定输入下响应时间减半。"
        texts = {"a": "已测记录：" + value, "b": "责任复核：" + value + " 当前归属仍待核实。"}
        refs = [{"material_id": key, "document_id": key * 64,
                 "sha256": hashlib.sha256(text.encode()).hexdigest()} for key, text in texts.items()]
        bindings = [{"field": "results", "value": value, "quote": texts[ref["material_id"]],
                     "material_id": ref["material_id"], "document_id": ref["document_id"]} for ref in refs]
        scope = {"field": "results", "index": 0, "value": value,
                 "source": {**refs[0], "quote": texts["a"]},
                 "attribution": "self", "target": "接口", "environment": "test",
                 "implementation": "implemented", "release": "not_released"}
        documents = {(ref["material_id"], ref["document_id"]): texts[ref["material_id"]] for ref in refs}
        return scope, bindings, refs, documents

    def test_basis_changes_for_bound_peer_before_scope_adoption(self):
        from tools.infra.evidence_fact_scope import result_review_basis, result_review_input

        scope, bindings, refs, documents = self._basis_inputs()
        original = result_review_input("ec-current", scope, [scope], bindings[:1], refs, documents)
        with_peer = result_review_input("ec-current", scope, [scope], bindings, refs, documents)
        self.assertNotEqual(result_review_basis(original), result_review_basis(with_peer))
        self.assertEqual({item["material_id"] for item in with_peer["documents"]}, {"a", "b"})
        self.assertEqual(len(with_peer["scopes"]), 1)

    def test_basis_does_not_depend_on_old_reviews_or_other_fact_bindings(self):
        from tools.infra.evidence_fact_scope import result_review_basis, result_review_input

        scope, bindings, refs, documents = self._basis_inputs()
        original = result_review_input("ec-current", scope, [scope], bindings[:1], refs, documents)
        historical = {**scope, "result_review": {"outcome": "established", "measurement_quote": scope["value"],
                                               "rationale": "旧单源结论", "basis_sha256": "0" * 64}}
        unrelated = {**bindings[1], "field": "actions"}
        same = result_review_input("ec-current", historical, [historical],
                                   [unrelated, bindings[0]], list(reversed(refs)), documents)
        self.assertEqual(result_review_basis(original), result_review_basis(same))
        self.assertNotIn("result_review", same["scopes"][0])
        self.assertNotIn("basis_sha256", same["scopes"][0])

    def test_basis_binds_scope_source_version_and_exact_fact_identity(self):
        from tools.infra.evidence_fact_scope import result_review_basis, result_review_input
        import hashlib

        scope, bindings, refs, documents = self._basis_inputs()
        original = result_review_basis(result_review_input("ec-current", scope, [scope], bindings[:1], refs, documents))
        changed_scope = {**scope, "attribution": "contributor"}
        scope_basis = result_review_basis(result_review_input("ec-current", changed_scope, [changed_scope],
                                                              bindings[:1], refs, documents))
        identity_basis = result_review_basis(result_review_input("ec-other", scope, [scope], bindings[:1], refs, documents))
        newer = documents.copy()
        key = (refs[0]["material_id"], refs[0]["document_id"])
        newer[key] += "\n后续责任更正，原条件需要重新核验。"
        newer_ref = {**refs[0], "sha256": hashlib.sha256(newer[key].encode()).hexdigest()}
        newer_scope = {**scope, "source": {**scope["source"], "sha256": newer_ref["sha256"]}}
        version_basis = result_review_basis(result_review_input("ec-current", newer_scope, [newer_scope],
                                                                bindings[:1], [newer_ref, refs[1]], newer))
        self.assertEqual(len({original, scope_basis, identity_basis, version_basis}), 4)


class RuleExtractorTests(unittest.TestCase):
    def test_extract_rule_card(self) -> None:
        extractor = _rule_extractor_class()()
        card = extractor.extract(
            "\n".join(
                [
                    "# 性能优化",
                    "结果：",
                    "- 接口 P99 时延下降 30%",
                    "证据：",
                    "- pr-100",
                    "技术栈：",
                    "Python",
                ]
            )
        )
        self.assertEqual(card.title, "性能优化")
        self.assertIn("接口 P99 时延下降 30%", card.results)
        self.assertIn("pr-100", card.artifacts)
        self.assertIn("Python", card.stack)
        self.assertIn("性能", card.tags)


class EvidenceStoreTests(unittest.TestCase):
    def test_save_and_get(self) -> None:
        with TemporaryDirectory() as tmp:
            store = _store_class()(base_dir=tmp)
            card = EvidenceCard(
                id="ec-2",
                title="Card",
                raw_source="source",
                results=("R",),
                artifacts=("A",),
                tags=("T",),
            )
            path = store.save(card)
            self.assertTrue(Path(path).exists())
            loaded = store.get("ec-2")
            self.assertIsNotNone(loaded)
            assert loaded is not None
            self.assertEqual(loaded.results, ("R",))


class LLMExtractorTests(unittest.TestCase):
    def test_extract_from_llm_json(self) -> None:
        class FakeClient:
            chat_completions_url = "https://example.com/chat/completions"

            def __init__(self) -> None:
                self.called_url = ""
                self.called_payload: object = {}

            def post_json(self, url: str, payload: object) -> dict[str, object]:
                self.called_url = url
                self.called_payload = payload
                return {
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"id":"ec-llm-1","title":"LLM","raw_source":"raw",'
                                    '"results":["r1"],"artifacts":["a1"],"tags":["t1"]}'
                                )
                            }
                        }
                    ]
                }

            @staticmethod
            def extract_content(response: dict[str, object]) -> str:
                choices = response["choices"]
                if isinstance(choices, list) and choices:
                    first = choices[0]
                    if isinstance(first, dict):
                        message = first.get("message")
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, str):
                                return content
                return ""

        fake_client = FakeClient()
        extractor = _llm_extractor_class()(client=fake_client, model="gpt-test")
        card = extractor.extract("raw")
        self.assertEqual(card.id, "ec-llm-1")
        self.assertEqual(card.results, ("r1",))
        self.assertEqual(card.artifacts, ("a1",))


if __name__ == "__main__":
    _ = unittest.main()
