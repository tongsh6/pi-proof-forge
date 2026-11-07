"""LLM 式证据提炼引擎。

把原始材料 + 提示词模板交给统一 LLMClient，取回结构化 YAML/JSON 文本。
本模块只负责提示词组装、模型调用与 base_url 安全解析，不落盘、不解析业务
语义；是否可用、输出到哪个文件由调用方决定。
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.domain.models import EvidenceCard
from tools.infra.llm.client import (
    LLMClient,
    STRATA_UNIFIED_BASE_URL,
    provider_is_keyless,
)
from tools.infra.persistence.yaml_io import parse_simple_yaml

DEFAULT_BASE_URL = "https://api.openai.com/v1"
SYSTEM_PROMPT = "你是证据提炼器，必须严格遵循提示词格式输出，不得编造事实。"


def load_prompt_template(template_path: str | Path, raw_material: str) -> str:
    template = Path(template_path).read_text(encoding="utf-8")
    return template.replace("<RAW_MATERIAL>", raw_material)


def resolve_base_url(*, provider: str, base_url: str) -> str:
    """解析模型调用地址。

    显式传入优先；Strata 走 App 管理的统一入口；其它 keyless 本地 provider
    缺地址时必须报错，不能悄悄落到 OpenAI 默认地址。
    """
    explicit = base_url.strip()
    if explicit:
        return explicit
    normalized = provider.strip().lower()
    if normalized == "strata":
        return STRATA_UNIFIED_BASE_URL
    if provider_is_keyless(provider):
        raise ValueError(
            "Missing base URL for keyless local provider. Set --base-url or LLM_BASE_URL."
        )
    return DEFAULT_BASE_URL


def build_payload(*, model: str, prompt: str) -> dict[str, object]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }


def extract_yaml_text(client: LLMClient, *, model: str, prompt: str) -> str:
    """调用模型并返回模型输出的卡 YAML 文本；空内容视为失败。"""
    response = client.post_json(
        client.chat_completions_url, build_payload(model=model, prompt=prompt)
    )
    content = client.extract_content(response)
    if not content:
        raise ValueError("Empty response content.")
    return content


class LLMEvidenceExtractor:
    """Agent 编排 evidence 策略：把模型输出适配为 domain EvidenceCard。"""

    def __init__(self, client: LLMClient, model: str) -> None:
        self._client = client
        self._model = model

    def extract(self, raw_material: str) -> EvidenceCard:
        payload = {
            "model": self._model,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Extract evidence card JSON with keys: "
                        "id,title,raw_source,results,artifacts,tags. "
                        f"Input:\n{raw_material}"
                    ),
                }
            ],
        }
        response = self._client.post_json(self._client.chat_completions_url, payload)
        content = self._client.extract_content(response)

        parsed: dict[str, object]
        try:
            loaded = json.loads(content)
            parsed = loaded if isinstance(loaded, dict) else {}
        except json.JSONDecodeError:
            parsed = {}

        return EvidenceCard(
            id=str(parsed.get("id", "ec-llm-generated")),
            title=str(parsed.get("title", "LLM Evidence")),
            raw_source=str(parsed.get("raw_source", raw_material)),
            results=tuple(_ensure_str_list(parsed.get("results"))),
            artifacts=tuple(_ensure_str_list(parsed.get("artifacts"))),
            tags=tuple(_ensure_str_list(parsed.get("tags"))),
        )


def parse_card_yaml(text: str) -> dict[str, object]:
    """把模型返回的卡 YAML 解析为标量/列表字典（供需要结构化结果的调用方）。"""
    return parse_simple_yaml(text)


def _ensure_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    for item in value:
        output.append(str(item))
    return output
