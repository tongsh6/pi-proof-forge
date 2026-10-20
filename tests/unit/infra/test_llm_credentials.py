"""按 provider 保存 LLM API Key 的本机权限文件测试。"""

from __future__ import annotations

import os
from pathlib import Path
import stat

import pytest

from tools.infra import llm_credentials as credentials


def test_save_load_delete_is_scoped_per_provider(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.save("deepseek", "sk-deepseek")
    store.save("openai", "sk-openai")

    assert store.load("deepseek") == "sk-deepseek"
    assert store.load("openai") == "sk-openai"
    assert store.configured_providers() == ["deepseek", "openai"]
    assert store.path_for("deepseek").name == "llm-deepseek-api-key"
    assert stat.S_IMODE(store.path_for("deepseek").stat().st_mode) == 0o600
    assert stat.S_IMODE(store.root.stat().st_mode) == 0o700

    store.delete("deepseek")
    assert store.load("deepseek") is None
    assert store.configured_providers() == ["openai"]
    store.delete("deepseek")


def test_provider_names_are_normalized_and_traversal_is_rejected(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.save("DeepSeek", "sk-deepseek")
    assert store.load("deepseek") == "sk-deepseek"

    for invalid in ("../evil", "a/b", "", "deepseek api", "A" * 40, "1deepseek"):
        with pytest.raises(ValueError):
            store.save(invalid, "sk-test")


def test_configured_providers_ignores_unsafe_or_unreadable_entries(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.save("deepseek", "sk-deepseek")

    unsafe = store.root / "llm-openai-api-key"
    unsafe.write_text("sk-openai", encoding="utf-8")
    unsafe.chmod(0o644)

    symlink = store.root / "llm-openai_compatible-api-key"
    target = tmp_path / "outside"
    target.write_text("sk-outside", encoding="utf-8")
    target.chmod(0o600)
    symlink.symlink_to(target)

    assert store.configured_providers() == ["deepseek"]


def test_environment_root_override(tmp_path, monkeypatch):
    monkeypatch.setenv("PPF_CREDENTIAL_DIR", str(tmp_path / "env-credentials"))
    store = credentials.LLMApiKeyStore()
    assert store.root == tmp_path / "env-credentials"
    store.save("deepseek", "sk-deepseek")
    assert store.load("deepseek") == "sk-deepseek"


def test_saved_key_does_not_appear_in_repr_or_errors(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.save("deepseek", "sk-secret-value")
    assert "sk-secret-value" not in repr(store)
    assert "sk-secret-value" not in repr(store.status("deepseek"))


def test_status_reports_update_time_without_key(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.save("deepseek", "sk-deepseek")
    status = store.status("deepseek")
    assert status["configured"] is True
    assert status["updated_at"]
    assert "sk-deepseek" not in repr(status)

    store.delete("deepseek")
    assert store.status("deepseek") == {"configured": False, "updated_at": ""}


def test_symlinked_target_is_rejected_for_all_operations(tmp_path):
    store = credentials.LLMApiKeyStore(tmp_path / "credentials")
    store.root.mkdir(mode=0o700)
    real = tmp_path / "outside-key"
    real.write_text("sk-outside", encoding="utf-8")
    real.chmod(0o600)
    store.path_for("deepseek").symlink_to(real)

    with pytest.raises(credentials.CredentialStorageError):
        store.load("deepseek")
    with pytest.raises(credentials.CredentialStorageError):
        store.save("deepseek", "sk-new")
    with pytest.raises(credentials.CredentialStorageError):
        store.delete("deepseek")
    assert real.read_text(encoding="utf-8") == "sk-outside"


def test_default_root_uses_application_support(tmp_path, monkeypatch):
    monkeypatch.delenv("PPF_CREDENTIAL_DIR", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    store = credentials.LLMApiKeyStore()
    assert store.root == (
        tmp_path / "Library/Application Support/PiProofForge/credentials"
    )
    assert list(tmp_path.iterdir()) == []
