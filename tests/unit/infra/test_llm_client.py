import unittest

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


class AuthHeaderTests(unittest.TestCase):
    def test_headers_contain_authorization(self) -> None:
        client = LLMClient(base_url="https://api.example.com", api_key="sk-abc123")
        headers = client.build_headers()
        self.assertEqual(headers["Authorization"], "Bearer sk-abc123")

    def test_headers_contain_content_type(self) -> None:
        client = LLMClient(base_url="https://api.example.com", api_key="sk-abc123")
        headers = client.build_headers()
        self.assertEqual(headers["Content-Type"], "application/json")


if __name__ == "__main__":
    unittest.main()
