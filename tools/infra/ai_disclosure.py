"""投递 AI 自动化声明：固定文案与指纹。

声明是投递前由 App 自有会话向招聘方真实发送的一条聊天消息，只在系统设置开关开启时发送；
文案属于产品声明，不在运行时由用户或模型改写，避免误述。
"""
from __future__ import annotations

import hashlib

AI_DISCLOSURE_TEXT = (
    "您好，本次投递所使用的简历和投递操作均由 AI 自动化执行；"
    "如对简历内容有疑问，欢迎直接与我沟通。"
)


def disclosure_sha256(text: str = AI_DISCLOSURE_TEXT) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
