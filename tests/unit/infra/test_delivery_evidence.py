"""投递证据对象纯函数单测：唯一身份、回执判定、复传判定与序列化往返。"""
import json

import pytest

from tools.infra.delivery_evidence import (
    AttachmentEvidence,
    DeliveryEvidence,
    SendEvidence,
    build_evidence,
    evidence_id,
    from_dict,
    is_delivered,
    needs_reupload,
    same_attachment,
    to_dict,
    validate_evidence,
)

PDF = "a" * 64
RECEIPT = "b" * 64
SNAPSHOT = "c" * 64


def valid_evidence(**overrides):
    """构造一份平台回执完整、附件字节与批准 PDF 一致的合法证据。"""
    values = dict(
        run_id="ar_test",
        pdf_sha256=PDF,
        attempt_id="attempt-1",
        snapshot_sha256=SNAPSHOT,
        observed_at="2026-11-08T00:00:00+00:00",
        attachment=AttachmentEvidence(
            filename="resume_ar_test.pdf",
            file_id="file-1",
            encry_attachment_id="enc-1",
            download_sha256=PDF,
            observed_count=1,
        ),
        send=SendEvidence(
            http_status=200,
            business_flag=1,
            receipt_sha256=RECEIPT,
            final_send_started=True,
        ),
    )
    values.update(overrides)
    return build_evidence(**values)


def raw_evidence(**overrides):
    """绕过 build 直接构造，用于测试校验函数对非法字段的拒绝。"""
    values = dict(
        run_id="ar_test",
        attempt_id="",
        pdf_sha256=PDF,
        snapshot_sha256="",
        attachment=AttachmentEvidence(filename="r.pdf", file_id="file-1"),
        send=SendEvidence(),
        observed_at="2026-11-08T00:00:00+00:00",
    )
    values.update(overrides)
    return DeliveryEvidence(**values)


def test_build_evidence_and_roundtrip():
    evidence = valid_evidence()
    assert evidence.run_id == "ar_test"
    assert evidence.pdf_sha256 == PDF
    assert evidence.attempt_id == "attempt-1"
    assert evidence.attachment.observed_count == 1
    payload = to_dict(evidence)
    assert isinstance(payload, dict) and isinstance(payload["attachment"], dict)
    assert json.loads(json.dumps(payload)) == payload
    assert from_dict(payload) == evidence
    assert validate_evidence(evidence) == []


def test_build_normalizes_hex_to_lowercase():
    evidence = build_evidence(
        run_id="ar_upper",
        pdf_sha256=PDF.upper(),
        snapshot_sha256=SNAPSHOT.upper(),
        observed_at="2026-11-08T00:00:00+00:00",
        attachment=AttachmentEvidence(download_sha256=PDF.upper()),
        send=SendEvidence(receipt_sha256=RECEIPT.upper()),
    )
    assert evidence.pdf_sha256 == PDF
    assert evidence.snapshot_sha256 == SNAPSHOT
    assert evidence.attachment.download_sha256 == PDF
    assert evidence.send.receipt_sha256 == RECEIPT


def test_build_evidence_rejects_missing_or_invalid_required_fields():
    base = dict(
        run_id="ar_test",
        pdf_sha256=PDF,
        attachment=AttachmentEvidence(file_id="file-1"),
        send=SendEvidence(),
        observed_at="2026-11-08T00:00:00+00:00",
    )
    with pytest.raises(ValueError, match="run_id_missing"):
        build_evidence(**{**base, "run_id": ""})
    with pytest.raises(ValueError, match="observed_at_missing"):
        build_evidence(**{**base, "observed_at": ""})
    with pytest.raises(ValueError, match="pdf_sha256_invalid"):
        build_evidence(**{**base, "pdf_sha256": "xyz"})
    with pytest.raises(ValueError, match="attachment_invalid"):
        build_evidence(**{**base, "attachment": {"file_id": "file-1"}})
    with pytest.raises(ValueError, match="send_invalid"):
        build_evidence(**{**base, "send": None})


def test_validate_rejects_invalid_pdf_sha256():
    for invalid in ("A" * 64, "a" * 63, "g" * 64, PDF + "\n"):
        problems = validate_evidence(raw_evidence(pdf_sha256=invalid))
        assert problems == ["pdf_sha256_invalid"], invalid


def test_validate_rejects_attachment_bytes_mismatch():
    mismatched = raw_evidence(
        attachment=AttachmentEvidence(file_id="file-1", download_sha256="d" * 64)
    )
    assert validate_evidence(mismatched) == ["attachment_bytes_mismatch"]
    matching = raw_evidence(attachment=AttachmentEvidence(file_id="file-1", download_sha256=PDF))
    assert validate_evidence(matching) == []


def test_validate_rejects_missing_attachment_file_id():
    evidence = raw_evidence(attachment=AttachmentEvidence(filename="r.pdf"))
    assert validate_evidence(evidence) == ["attachment_file_id_missing"]


def test_validate_rejects_invalid_attachment_count():
    for count in (0, -1):
        evidence = raw_evidence(attachment=AttachmentEvidence(file_id="file-1", observed_count=count))
        assert validate_evidence(evidence) == ["attachment_count_invalid"], count


def test_validate_flags_unknown_send_result():
    started_without_network = raw_evidence(
        attachment=AttachmentEvidence(file_id="file-1"),
        send=SendEvidence(http_status=0, final_send_started=True),
    )
    assert validate_evidence(started_without_network) == ["send_result_unknown"]
    started_with_reply = raw_evidence(
        attachment=AttachmentEvidence(file_id="file-1"),
        send=SendEvidence(http_status=200, final_send_started=True),
    )
    assert validate_evidence(started_with_reply) == []


def test_validate_flags_missing_receipt():
    evidence = raw_evidence(
        attachment=AttachmentEvidence(file_id="file-1"),
        send=SendEvidence(http_status=200, business_flag=1, receipt_sha256=""),
    )
    assert validate_evidence(evidence) == ["receipt_missing"]


def test_validate_reports_all_independent_problems():
    evidence = raw_evidence(
        pdf_sha256="A" * 64,
        attachment=AttachmentEvidence(filename="r.pdf", observed_count=0),
        send=SendEvidence(http_status=0, final_send_started=True),
    )
    assert set(validate_evidence(evidence)) == {
        "pdf_sha256_invalid",
        "attachment_file_id_missing",
        "attachment_count_invalid",
        "send_result_unknown",
    }


def test_is_delivered_success():
    assert is_delivered(valid_evidence()) is True
    no_download_observed = valid_evidence(
        attachment=AttachmentEvidence(filename="r.pdf", file_id="file-1", download_sha256="")
    )
    assert is_delivered(no_download_observed) is True


def test_is_delivered_false_cases():
    assert is_delivered(valid_evidence(send=SendEvidence(http_status=0, business_flag=-1))) is False
    assert (
        is_delivered(
            valid_evidence(
                send=SendEvidence(http_status=200, business_flag=0, receipt_sha256=RECEIPT)
            )
        )
        is False
    )
    assert (
        is_delivered(
            valid_evidence(
                send=SendEvidence(http_status=200, business_flag=1, receipt_sha256="")
            )
        )
        is False
    )
    assert (
        is_delivered(
            valid_evidence(
                attachment=AttachmentEvidence(
                    filename="r.pdf", file_id="file-1", download_sha256="d" * 64
                )
            )
        )
        is False
    )
    assert is_delivered("not-evidence") is False


def test_needs_reupload_before_final_send():
    missing_handle = valid_evidence(
        attachment=AttachmentEvidence(filename="r.pdf", file_id=""),
        send=SendEvidence(http_status=0, final_send_started=False),
    )
    assert needs_reupload(missing_handle) is True
    empty_platform_list = valid_evidence(
        attachment=AttachmentEvidence(filename="r.pdf", file_id="file-1", observed_count=0),
        send=SendEvidence(http_status=0, final_send_started=False),
    )
    assert needs_reupload(empty_platform_list) is True
    complete = valid_evidence(
        attachment=AttachmentEvidence(filename="r.pdf", file_id="file-1", observed_count=1),
        send=SendEvidence(http_status=0, final_send_started=False),
    )
    assert needs_reupload(complete) is False


def test_needs_reupload_false_after_final_send():
    already_sent = valid_evidence(
        attachment=AttachmentEvidence(filename="r.pdf", file_id="", observed_count=0),
        send=SendEvidence(http_status=0, final_send_started=True),
    )
    assert needs_reupload(already_sent) is False
    assert needs_reupload(None) is False


def test_same_attachment_by_handle_and_by_content():
    first = AttachmentEvidence(filename="r.pdf", file_id="file-1", encry_attachment_id="enc-1")
    same_handle = AttachmentEvidence(filename="r.pdf", file_id="file-1", encry_attachment_id="enc-1")
    renamed = AttachmentEvidence(filename="copy.pdf", file_id="file-1", encry_attachment_id="enc-1")
    other_handle = AttachmentEvidence(filename="r.pdf", file_id="file-2", encry_attachment_id="enc-2")
    assert same_attachment(first, same_handle) is True
    assert same_attachment(first, renamed) is False
    assert same_attachment(first, other_handle) is False
    downloaded = AttachmentEvidence(
        filename="copy.pdf", file_id="file-9", encry_attachment_id="enc-9", download_sha256=PDF
    )
    unread = AttachmentEvidence(filename="r.pdf", file_id="file-1", encry_attachment_id="enc-1")
    assert same_attachment(downloaded, unread, pdf_sha256=PDF) is True
    assert same_attachment(downloaded, unread, pdf_sha256=PDF.upper()) is True
    assert same_attachment(first, other_handle, pdf_sha256="d" * 64) is False
    assert same_attachment(first, {"file_id": "file-1"}) is False


def test_evidence_id_is_stable():
    evidence = valid_evidence()
    expected = f"ar_test:{PDF[:12]}"
    assert evidence_id(evidence) == expected
    assert evidence_id(from_dict(to_dict(evidence))) == expected
    assert evidence_id(valid_evidence(run_id="ar_other")) != expected
    other_pdf = valid_evidence(pdf_sha256="d" * 64)
    assert evidence_id(other_pdf) == f"ar_test:{'d' * 12}"
    with pytest.raises(ValueError, match="delivery_evidence_invalid"):
        evidence_id("not-evidence")


def test_from_dict_rejects_invalid_payload():
    payload = to_dict(valid_evidence())
    invalid_payloads = [None, [], "evidence"]
    missing_run_id = dict(payload)
    missing_run_id.pop("run_id")
    invalid_payloads.append(missing_run_id)
    missing_attachment = dict(payload)
    missing_attachment.pop("attachment")
    invalid_payloads.append(missing_attachment)
    invalid_payloads.append({**payload, "attachment": "file-1"})
    invalid_payloads.append(
        {**payload, "attachment": {**payload["attachment"], "observed_count": "1"}}
    )
    invalid_payloads.append({**payload, "send": {**payload["send"], "final_send_started": 1}})
    invalid_payloads.append({**payload, "send": {**payload["send"], "http_status": True}})
    invalid_payloads.append({**payload, "pdf_sha256": "z" * 64})
    invalid_payloads.append({**payload, "observed_at": ""})
    for invalid in invalid_payloads:
        with pytest.raises(ValueError) as excinfo:
            from_dict(invalid)
        assert str(excinfo.value) == "delivery_evidence_invalid", invalid
