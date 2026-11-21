"""投递证据对象：以 PDF 内容哈希为唯一身份的统一证据模型（纯函数，无 IO）。

本模块把投递链路里散落的状态补丁收敛成一个不可变对象：
- ``pdf_sha256`` 是跨环节的唯一身份，平台 ``file_id`` / ``encry_attachment_id`` 只是句柄；
- 最终发送是否成功只看平台回执（http_status + business_flag + receipt_sha256）；
- 附件字节回读哈希与批准 PDF 不一致视为不同附件，同字节的重复卡片可容忍。

模块只依赖标准库，所有函数无文件/网络 IO、无全局状态，可直接单测。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any

_INVALID = "delivery_evidence_invalid"
_PDF_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AttachmentEvidence:
    """平台附件句柄与回读观测；句柄不构成身份，``download_sha256`` 才是内容证据。"""

    filename: str = ""
    file_id: str = ""
    encry_attachment_id: str = ""
    download_sha256: str = ""
    observed_count: int = 1


@dataclass(frozen=True)
class SendEvidence:
    """最终发送回执；HTTP 0 表示没有网络回执，业务 flag -1 表示平台未给出结论。"""

    http_status: int = 0
    business_flag: int = -1
    receipt_sha256: str = ""
    final_send_started: bool = False


@dataclass(frozen=True)
class DeliveryEvidence:
    """一次投递尝试的完整证据；``pdf_sha256`` 是唯一身份，其余字段都是观测或句柄。"""

    run_id: str
    attempt_id: str
    pdf_sha256: str
    snapshot_sha256: str
    attachment: AttachmentEvidence
    send: SendEvidence
    observed_at: str


def _text(value: Any, error: str, *, allow_none: bool = True) -> str:
    """把文本字段归一为 ``str``：``None`` 视为空串，其他非文本类型按问题码拒绝。"""
    if value is None:
        if allow_none:
            return ""
        raise ValueError(error)
    if not isinstance(value, str):
        raise ValueError(error)
    return value


def _hash_text(value: Any, error: str) -> str:
    """十六进制哈希字段统一小写，避免同一哈希出现两种写法。"""
    return _text(value, error).lower()


def build_evidence(
    *,
    run_id: str,
    pdf_sha256: str,
    attachment: AttachmentEvidence,
    send: SendEvidence,
    observed_at: str,
    attempt_id: str = "",
    snapshot_sha256: str = "",
) -> DeliveryEvidence:
    """从调用方字段构造证据对象，并对必填项做校验。

    必填：``run_id``、``pdf_sha256``（64 位十六进制）、``attachment``、``send``、``observed_at``。
    所有十六进制哈希字段统一转小写；校验失败抛 ``ValueError``，消息即问题码。
    """
    run_id = _text(run_id, "run_id_missing", allow_none=False)
    if not run_id:
        raise ValueError("run_id_missing")
    observed_at = _text(observed_at, "observed_at_missing", allow_none=False)
    if not observed_at:
        raise ValueError("observed_at_missing")
    if not isinstance(attachment, AttachmentEvidence):
        raise ValueError("attachment_invalid")
    if not isinstance(send, SendEvidence):
        raise ValueError("send_invalid")
    pdf_digest = _hash_text(pdf_sha256, "pdf_sha256_invalid")
    if not _PDF_SHA256_PATTERN.fullmatch(pdf_digest):
        raise ValueError("pdf_sha256_invalid")
    attachment = replace(
        attachment,
        download_sha256=_hash_text(attachment.download_sha256, "attachment_invalid"),
    )
    send = replace(send, receipt_sha256=_hash_text(send.receipt_sha256, "send_invalid"))
    return DeliveryEvidence(
        run_id=run_id,
        attempt_id=_text(attempt_id, "attempt_id_invalid"),
        pdf_sha256=pdf_digest,
        snapshot_sha256=_hash_text(snapshot_sha256, "snapshot_sha256_invalid"),
        attachment=attachment,
        send=send,
        observed_at=observed_at,
    )


def validate_evidence(evidence: DeliveryEvidence) -> list[str]:
    """返回证据问题码列表；空列表表示通过。

    只做静态一致性检查，不读取任何外部状态：
    - ``pdf_sha256`` 必须是 64 位小写十六进制；
    - 回读下载哈希非空时必须等于批准 PDF 哈希；
    - 附件必须有平台句柄且卡片数量合法；
    - 已发起最终发送却没有网络回执视为结果未知；
    - 平台回执 200/flag=1 却没有归档回执摘要视为回执缺失。
    """
    if not isinstance(evidence, DeliveryEvidence):
        return ["evidence_invalid"]
    problems: list[str] = []
    if not isinstance(evidence.pdf_sha256, str) or not _PDF_SHA256_PATTERN.fullmatch(
        evidence.pdf_sha256
    ):
        problems.append("pdf_sha256_invalid")
    download_sha256 = evidence.attachment.download_sha256
    if download_sha256 and download_sha256 != evidence.pdf_sha256:
        problems.append("attachment_bytes_mismatch")
    if not evidence.attachment.file_id:
        problems.append("attachment_file_id_missing")
    observed_count = evidence.attachment.observed_count
    if type(observed_count) is not int or observed_count < 1:
        problems.append("attachment_count_invalid")
    if evidence.send.http_status == 0 and evidence.send.final_send_started:
        problems.append("send_result_unknown")
    if (
        evidence.send.http_status == 200
        and evidence.send.business_flag == 1
        and not evidence.send.receipt_sha256
    ):
        problems.append("receipt_missing")
    return problems


def is_delivered(evidence: DeliveryEvidence) -> bool:
    """只有平台明确回执成功且附件字节与批准 PDF 一致时才返回 ``True``。

    回读下载哈希为空表示未回读，不否定平台回执；非空时必须与 ``pdf_sha256`` 相同。
    """
    if not isinstance(evidence, DeliveryEvidence):
        return False
    send = evidence.send
    if send.http_status != 200 or send.business_flag != 1 or not send.receipt_sha256:
        return False
    download_sha256 = evidence.attachment.download_sha256
    return not download_sha256 or download_sha256 == evidence.pdf_sha256


def needs_reupload(evidence: DeliveryEvidence) -> bool:
    """仅在最终发送尚未发起且附件缺失（无句柄或卡片数为 0）时返回 ``True``。

    已发起最终发送后永远返回 ``False``：请求可能已在平台侧生效，不能再传一次。
    """
    if not isinstance(evidence, DeliveryEvidence):
        return False
    if evidence.send.final_send_started:
        return False
    return not evidence.attachment.file_id or evidence.attachment.observed_count == 0


def same_attachment(
    left: AttachmentEvidence,
    right: AttachmentEvidence,
    *,
    pdf_sha256: str = "",
) -> bool:
    """判断两个平台附件观测是否代表同一附件。

    - 平台句柄三元组 ``file_id + encry_attachment_id + filename`` 完全一致即同一附件；
    - 调用方传入批准 PDF 的 ``pdf_sha256`` 时，任一方回读下载哈希与之一致也按内容身份
      视为同一附件（替代旧的“多卡片容忍”补丁：同一字节的重复卡片不算冲突）。
    """
    if not isinstance(left, AttachmentEvidence) or not isinstance(right, AttachmentEvidence):
        return False
    if isinstance(pdf_sha256, str) and pdf_sha256:
        approved = pdf_sha256.lower()
        if left.download_sha256 == approved or right.download_sha256 == approved:
            return True
    return (
        left.file_id,
        left.encry_attachment_id,
        left.filename,
    ) == (
        right.file_id,
        right.encry_attachment_id,
        right.filename,
    )


def evidence_id(evidence: DeliveryEvidence) -> str:
    """稳定标识 ``f"{run_id}:{pdf_sha256[:12]}"``，用于日志与对账引用。"""
    if not isinstance(evidence, DeliveryEvidence):
        raise ValueError(_INVALID)
    return f"{evidence.run_id}:{evidence.pdf_sha256[:12]}"


def to_dict(evidence: DeliveryEvidence) -> dict[str, Any]:
    """序列化为普通 dict（可直接写入 JSON），与 :func:`from_dict` 往返稳定。"""
    if not isinstance(evidence, DeliveryEvidence):
        raise ValueError(_INVALID)
    return {
        "run_id": evidence.run_id,
        "attempt_id": evidence.attempt_id,
        "pdf_sha256": evidence.pdf_sha256,
        "snapshot_sha256": evidence.snapshot_sha256,
        "observed_at": evidence.observed_at,
        "attachment": {
            "filename": evidence.attachment.filename,
            "file_id": evidence.attachment.file_id,
            "encry_attachment_id": evidence.attachment.encry_attachment_id,
            "download_sha256": evidence.attachment.download_sha256,
            "observed_count": evidence.attachment.observed_count,
        },
        "send": {
            "http_status": evidence.send.http_status,
            "business_flag": evidence.send.business_flag,
            "receipt_sha256": evidence.send.receipt_sha256,
            "final_send_started": evidence.send.final_send_started,
        },
    }


def _field_text(mapping: dict[str, Any], name: str, default: str = "") -> str:
    value = mapping.get(name, default)
    if not isinstance(value, str):
        raise ValueError(_INVALID)
    return value


def _field_int(mapping: dict[str, Any], name: str, default: int = 0) -> int:
    value = mapping.get(name, default)
    if type(value) is not int:
        raise ValueError(_INVALID)
    return value


def _field_bool(mapping: dict[str, Any], name: str, default: bool = False) -> bool:
    value = mapping.get(name, default)
    if type(value) is not bool:
        raise ValueError(_INVALID)
    return value


def from_dict(payload: dict[str, Any]) -> DeliveryEvidence:
    """从序列化快照重建证据；缺字段、类型错误或哈希非法统一抛 ``ValueError``。

    错误消息固定为 ``delivery_evidence_invalid``，调用方无需区分具体字段。
    """
    if not isinstance(payload, dict):
        raise ValueError(_INVALID)
    try:
        attachment_payload = payload["attachment"]
        send_payload = payload["send"]
        if not isinstance(attachment_payload, dict) or not isinstance(send_payload, dict):
            raise ValueError(_INVALID)
        attachment = AttachmentEvidence(
            filename=_field_text(attachment_payload, "filename"),
            file_id=_field_text(attachment_payload, "file_id"),
            encry_attachment_id=_field_text(attachment_payload, "encry_attachment_id"),
            download_sha256=_field_text(attachment_payload, "download_sha256"),
            observed_count=_field_int(attachment_payload, "observed_count", 1),
        )
        send = SendEvidence(
            http_status=_field_int(send_payload, "http_status", 0),
            business_flag=_field_int(send_payload, "business_flag", -1),
            receipt_sha256=_field_text(send_payload, "receipt_sha256"),
            final_send_started=_field_bool(send_payload, "final_send_started", False),
        )
        return build_evidence(
            run_id=_field_text(payload, "run_id"),
            attempt_id=_field_text(payload, "attempt_id"),
            pdf_sha256=_field_text(payload, "pdf_sha256"),
            snapshot_sha256=_field_text(payload, "snapshot_sha256"),
            attachment=attachment,
            send=send,
            observed_at=_field_text(payload, "observed_at"),
        )
    except (KeyError, TypeError, ValueError):
        raise ValueError(_INVALID) from None
