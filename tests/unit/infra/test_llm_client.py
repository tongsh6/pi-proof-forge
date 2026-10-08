import copy
import json
import unittest
from unittest.mock import Mock, patch

from tools.infra.llm.client import LLMClient


class ExtractContentTests(unittest.TestCase):
    def test_extracts_content_from_standard_response(self) -> None:
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Hello, world!",
                    }
                }
            ]
        }
        result = LLMClient.extract_content(response)
        self.assertEqual(result, "Hello, world!")

    def test_returns_empty_string_when_choices_empty(self) -> None:
        response: dict = {"choices": []}
        result = LLMClient.extract_content(response)
        self.assertEqual(result, "")

    def test_returns_empty_string_when_content_missing(self) -> None:
        response = {"choices": [{"message": {}}]}
        result = LLMClient.extract_content(response)
        self.assertEqual(result, "")

    def test_returns_empty_string_when_choices_missing(self) -> None:
        response: dict = {}
        result = LLMClient.extract_content(response)
        self.assertEqual(result, "")

    def test_returns_empty_string_when_message_missing(self) -> None:
        response = {"choices": [{"index": 0}]}
        result = LLMClient.extract_content(response)
        self.assertEqual(result, "")


class URLConstructionTests(unittest.TestCase):
    def test_constructs_url_with_trailing_slash(self) -> None:
        client = LLMClient(base_url="https://api.example.com/v1/", api_key="test-key")
        self.assertEqual(client.chat_completions_url, "https://api.example.com/v1/chat/completions")

    def test_constructs_url_without_trailing_slash(self) -> None:
        client = LLMClient(base_url="https://api.example.com/v1", api_key="test-key")
        self.assertEqual(client.chat_completions_url, "https://api.example.com/v1/chat/completions")

    def test_constructs_models_url(self) -> None:
        client = LLMClient(base_url="https://api.example.com/v1/", api_key="test-key")
        self.assertEqual(client.models_url, "https://api.example.com/v1/models")


class AuthHeaderTests(unittest.TestCase):
    def test_headers_contain_authorization(self) -> None:
        client = LLMClient(base_url="https://api.example.com", api_key="sk-abc123")
        headers = client.build_headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-abc123")

    def test_headers_contain_content_type(self) -> None:
        client = LLMClient(base_url="https://api.example.com", api_key="sk-abc123")
        headers = client.build_headers()
        self.assertEqual(headers["Content-Type"], "application/json")


class ListModelsTests(unittest.TestCase):
    def test_list_models_extracts_model_ids(self) -> None:
        response = Mock()
        response.read.return_value = b'{"data":[{"id":"model-a"},{"id":"model-b"}]}'
        response.close.return_value = None
        client = LLMClient(base_url="https://api.example.com/v1", api_key="sk-abc123")

        with patch("tools.infra.llm.client.request.urlopen", return_value=response) as urlopen:
            models = client.list_models()

        self.assertEqual(models, ["model-a", "model-b"])
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 120)

    def test_list_models_returns_empty_for_unexpected_payload(self) -> None:
        response = Mock()
        response.read.return_value = b'{"object":"list"}'
        response.close.return_value = None
        client = LLMClient(base_url="https://api.example.com/v1", api_key="sk-abc123")

        with patch("tools.infra.llm.client.request.urlopen", return_value=response):
            models = client.list_models()

        self.assertEqual(models, [])


class StructuredOutputTests(unittest.TestCase):
    def _sent_payload(
        self, payload: dict, provider: str = "lm_studio", *, response_schema: dict | None = None
    ) -> dict:
        response = Mock()
        response.read.return_value = b'{}'
        client = LLMClient(
            base_url="http://127.0.0.1:1234/v1", api_key="lm-studio", provider=provider
        )
        with patch("tools.infra.llm.client.request.urlopen", return_value=response) as urlopen:
            if response_schema is None:
                client.post_json(client.chat_completions_url, payload)
            else:
                client.post_json(client.chat_completions_url, payload, response_schema=response_schema)
        self.assertEqual(urlopen.call_count, 1)
        return json.loads(urlopen.call_args.args[0].data)

    def test_lm_studio_uses_supplied_schema_without_mutating_schema_or_payload(self) -> None:
        payload = {"model": "local-model", "response_format": {"type": "json_object"}}
        schema = {
            "type": "object",
            "properties": {"signals": {"type": "array", "items": {"type": "string"}}},
            "required": ["signals"],
        }
        original_payload, original_schema = copy.deepcopy(payload), copy.deepcopy(schema)
        sent = self._sent_payload(payload, response_schema=schema)
        self.assertEqual(sent["response_format"]["json_schema"]["schema"], schema)
        self.assertNotIn("response_schema", sent)
        self.assertEqual(payload, original_payload)
        self.assertEqual(schema, original_schema)

    def test_response_schema_is_not_sent_to_other_providers(self) -> None:
        payload = {"model": "example", "response_format": {"type": "json_object"}}
        for provider in ("openai", "openai_compatible"):
            with self.subTest(provider=provider):
                self.assertEqual(
                    self._sent_payload(payload, provider, response_schema={"type": "object"}), payload
                )

    def test_supplied_schema_does_not_replace_explicit_format(self) -> None:
        payload = {
            "model": "local-model",
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "explicit", "schema": {"type": "array"}},
            },
        }
        self.assertEqual(
            self._sent_payload(payload, response_schema={"type": "object"}), payload
        )

    def test_verified_qwen_structured_extraction_disables_reasoning_without_mutation(self) -> None:
        payload = {
            "model": "qwen/qwen3.8-27b",
            "response_format": {"type": "json_object"},
        }
        original = copy.deepcopy(payload)
        sent = self._sent_payload(payload)
        self.assertEqual(sent["reasoning_effort"], "none")
        self.assertEqual(sent["response_format"]["type"], "json_schema")
        self.assertEqual(payload, original)

    def test_verified_qwen_preserves_explicit_reasoning_effort(self) -> None:
        for effort in ("low", "none", None):
            with self.subTest(effort=effort):
                payload = {
                    "model": "qwen/qwen3.8-27b",
                    "response_format": {"type": "json_object"},
                    "reasoning_effort": effort,
                }
                self.assertEqual(self._sent_payload(payload)["reasoning_effort"], effort)

    def test_reasoning_default_does_not_apply_to_other_models_or_providers(self) -> None:
        for provider, model in (
            ("lm_studio", "local-model"),
            ("lm_studio", "qwen/qwen3.8-27b-other"),
            ("openai", "qwen/qwen3.8-27b"),
            ("openai_compatible", "qwen/qwen3.8-27b"),
        ):
            with self.subTest(provider=provider, model=model):
                sent = self._sent_payload(
                    {"model": model, "response_format": {"type": "json_object"}}, provider
                )
                self.assertNotIn("reasoning_effort", sent)

    def test_verified_qwen_without_json_object_keeps_request_unchanged(self) -> None:
        for response_format in (
            None,
            {"type": "text"},
            {"type": "json_schema", "json_schema": {
                "name": "custom", "schema": {"type": "object"}
            }},
        ):
            with self.subTest(response_format=response_format):
                payload = {"model": "qwen/qwen3.8-27b"}
                if response_format is not None:
                    payload["response_format"] = response_format
                self.assertEqual(self._sent_payload(payload), payload)

    def test_lm_studio_json_object_uses_object_schema_without_mutating_input(self) -> None:
        payload = {
            "model": "local-model",
            "messages": [{"role": "user", "content": "Return a JSON object."}],
            "response_format": {"type": "json_object"},
        }
        original = copy.deepcopy(payload)
        response = Mock()
        response.read.return_value = b'{"choices":[]}'
        client = LLMClient(
            base_url="http://127.0.0.1:1234/v1", api_key="lm-studio", provider="lm_studio"
        )

        with patch("tools.infra.llm.client.request.urlopen", return_value=response) as urlopen:
            result = client.post_json(client.chat_completions_url, payload)

        sent = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(sent["response_format"], {
            "type": "json_schema",
            "json_schema": {"name": "json_object", "schema": {"type": "object"}},
        })
        self.assertEqual(sent["model"], payload["model"])
        self.assertEqual(sent["messages"], payload["messages"])
        self.assertEqual(payload, original)
        self.assertEqual(result, {"choices": []})
        self.assertEqual(urlopen.call_count, 1)

    def test_other_providers_keep_json_object_format(self) -> None:
        payload = {"model": "example", "response_format": {"type": "json_object"}}
        for provider in (None, "openai", "openai_compatible"):
            with self.subTest(provider=provider):
                response = Mock()
                response.read.return_value = b'{}'
                kwargs = {} if provider is None else {"provider": provider}
                client = LLMClient(
                    base_url="http://127.0.0.1:1234/v1", api_key="test", **kwargs
                )
                with patch("tools.infra.llm.client.request.urlopen", return_value=response) as urlopen:
                    client.post_json(client.chat_completions_url, payload)
                self.assertEqual(json.loads(urlopen.call_args.args[0].data), payload)

    def test_lm_studio_keeps_explicit_schema_text_and_omitted_format(self) -> None:
        for response_format in (
            None,
            {"type": "text"},
            {"type": "json_schema", "json_schema": {
                "name": "custom", "schema": {"type": "object", "required": ["title"]}
            }},
        ):
            with self.subTest(response_format=response_format):
                payload = {"model": "local-model"}
                if response_format is not None:
                    payload["response_format"] = response_format
                response = Mock()
                response.read.return_value = b'{}'
                client = LLMClient(
                    base_url="http://127.0.0.1:1234/v1", api_key="lm-studio", provider="lm_studio"
                )
                with patch("tools.infra.llm.client.request.urlopen", return_value=response) as urlopen:
                    client.post_json(client.chat_completions_url, payload)
                self.assertEqual(json.loads(urlopen.call_args.args[0].data), payload)


if __name__ == "__main__":
    unittest.main()
