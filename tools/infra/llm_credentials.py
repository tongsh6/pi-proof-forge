"""按 provider 保存 LLM API Key 的本机凭据仓库。"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import re

from tools.infra.liepin_token_file import CredentialStorageError, LocalCredentialFile


_PROVIDER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_FILE_TEMPLATE = "llm-{provider}-api-key"


def normalize_provider(provider: str) -> str:
    """Provider id 只允许小写字母、数字和下划线，避免路径穿越。"""
    if not isinstance(provider, str):
        raise ValueError("unsupported provider id")
    value = provider.strip().lower()
    if not _PROVIDER_PATTERN.fullmatch(value):
        raise ValueError("unsupported provider id")
    return value


def _default_root() -> Path:
    override = os.environ.get("PPF_CREDENTIAL_DIR", "").strip()
    if override:
        return Path(override)
    return Path.home() / "Library/Application Support/PiProofForge/credentials"


class LLMApiKeyStore:
    def __init__(self, root: Path | None = None) -> None:
        selected = root if root is not None else _default_root()
        self._root = Path(os.path.abspath(Path(selected)))

    @property
    def root(self) -> Path:
        return self._root

    def path_for(self, provider: str) -> Path:
        normalized = normalize_provider(provider)
        return self.root / _FILE_TEMPLATE.format(provider=normalized)

    def load(self, provider: str) -> str | None:
        return LocalCredentialFile(self.path_for(provider)).load()

    def save(self, provider: str, api_key: str) -> None:
        LocalCredentialFile(self.path_for(provider)).save(api_key)

    def delete(self, provider: str) -> None:
        LocalCredentialFile(self.path_for(provider)).delete()

    def status(self, provider: str) -> dict[str, object]:
        path = self.path_for(provider)
        try:
            saved = LocalCredentialFile(path).load()
        except CredentialStorageError:
            return {"configured": False, "updated_at": ""}
        if not saved:
            return {"configured": False, "updated_at": ""}
        try:
            updated_at = (
                datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
        except OSError:
            updated_at = ""
        return {"configured": True, "updated_at": updated_at}

    def configured_providers(self) -> list[str]:
        if self.root.is_symlink() or not self.root.is_dir():
            return []
        providers: list[str] = []
        try:
            entries = list(self.root.iterdir())
        except OSError:
            return []
        for entry in entries:
            name = entry.name
            if not name.startswith("llm-") or not name.endswith("-api-key"):
                continue
            provider = name[len("llm-") : -len("-api-key")]
            try:
                normalize_provider(provider)
                saved = LocalCredentialFile(entry).load()
            except (ValueError, CredentialStorageError):
                continue
            if saved:
                providers.append(provider)
        return sorted(providers)
