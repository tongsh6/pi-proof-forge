"""B4/B5：突出点否决/替换的 RPC 校验与落盘。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.sidecar.handlers import agent, quality


def _prepare(tmp_path, monkeypatch):
    monkeypatch.setattr(agent, "_PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(agent, "_QUICK_RUN_DIR", tmp_path / "outputs" / "quick_runs")
    (tmp_path / "outputs" / "quick_runs").mkdir(parents=True)
    (tmp_path / "outputs" / "quick_runs" / "qr-1.json").write_text("{}", encoding="utf-8")


def _params(**overrides):
    params = {
        "meta": {"correlation_id": "corr-1"},
        "run_id": "qr-1",
        "resume_sha256": "a" * 64,
        "highlight_id": "hl_b3_d1",
        "action": "reject",
    }
    params.update(overrides)
    return params


def test_highlight_decision_writes_app_data_and_merges(tmp_path, monkeypatch):
    _prepare(tmp_path, monkeypatch)
    result = quality.handle_quality_decide_highlight(_params())
    assert result["decisions"] == {"rejected": ["hl_b3_d1"], "selected": []}
    result = quality.handle_quality_decide_highlight(_params(highlight_id="hl_b4_d2", action="select"))
    assert result["decisions"] == {"rejected": ["hl_b3_d1"], "selected": ["hl_b4_d2"]}
    payload = json.loads((tmp_path / "app-data" / "quality_decisions.json").read_text(encoding="utf-8"))
    assert payload["resumes"]["a" * 64]["rejected"] == ["hl_b3_d1"]
    assert payload["resumes"]["a" * 64]["selected"] == ["hl_b4_d2"]


@pytest.mark.parametrize(
    "overrides,error",
    [
        ({"run_id": "../escape"}, "quality_run_id_invalid"),
        ({"run_id": "qr-missing"}, "quality_run_not_found"),
        ({"resume_sha256": "not-a-sha"}, "quality_resume_sha256_invalid"),
        ({"highlight_id": "bad id"}, "quality_highlight_invalid"),
        ({"action": "delete"}, "quality_decision_invalid"),
    ],
)
def test_highlight_decision_rejects_invalid_inputs(tmp_path, monkeypatch, overrides, error):
    _prepare(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match=error):
        quality.handle_quality_decide_highlight(_params(**overrides))
    assert not (tmp_path / "app-data" / "quality_decisions.json").exists()
