"""可复用的正文质量文本判定（评估器与生成器共用）。"""
from __future__ import annotations

import re

# 数字必须带业务单位才算可验证量化；技术版本、年份、纯序号不算。
QUANT_METRIC_RE = re.compile(
    r"\d[\d,.]*\+?\s*(?:%|ms\b|s\b|毫秒|秒|分钟|小时|万?条|次|个|人|项|QPS\b|TPS\b|GB\b|TB\b|倍)",
    re.I,
)


def compact(text: str) -> str:
    return re.sub(r"[\s*_`，,。；;：:·、|（）()\[\]【】“”\"']", "", str(text or ""))


def has_quant_metric(text: str) -> bool:
    return bool(QUANT_METRIC_RE.search(str(text or "")))


_TECH_TERM_CASES = {
    "spring": "Spring", "springboot": "SpringBoot", "boot": "Boot", "java": "Java",
    "redis": "Redis", "mysql": "MySQL", "oracle": "Oracle", "jenkins": "Jenkins",
    "docker": "Docker", "kubernetes": "Kubernetes", "nacos": "Nacos", "maven": "Maven",
    "gradle": "Gradle", "linux": "Linux", "jpa": "JPA", "hibernate": "Hibernate",
    "mybatis": "MyBatis", "kafka": "Kafka", "rabbitmq": "RabbitMQ", "nginx": "Nginx",
    "git": "Git", "http": "HTTP", "rest": "REST", "json": "JSON", "api": "API",
    "sql": "SQL", "jvm": "JVM", "ci": "CI", "cd": "CD", "mongodb": "MongoDB",
}

def _normalize_tech_terms(text: str) -> str:
    def replace(match: "re.Match[str]") -> str:
        term = match.group(1)
        canonical = _TECH_TERM_CASES.get(term.casefold()) if term.isascii() else None
        return canonical or term

    return re.sub(r"(?<![A-Za-z])([A-Za-z][A-Za-z0-9+#./-]*)(?![A-Za-z])", replace, text)


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u2705\u274C\u26A0]"
)


def render_fact_text(text: str) -> str:
    value = re.sub(r"\*\*|__|`", "", str(text or ""))
    value = _EMOJI_RE.sub("", value)
    return _normalize_tech_terms(" ".join(value.split()))
