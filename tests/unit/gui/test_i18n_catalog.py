from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "ui" / "src"
EN_JSON = SRC / "i18n" / "en.json"
ZH_JSON = SRC / "i18n" / "zh.json"


def _flatten(value: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(child, dict):
            result.update(_flatten(child, path))
        else:
            result[path] = child
    return result


def _static_t_keys() -> set[str]:
    pattern = re.compile(r"\bt\(\s*[\"']([^\"'`$]+)[\"']")
    keys: set[str] = set()
    for path in SRC.rglob("*.tsx"):
        keys.update(pattern.findall(path.read_text(encoding="utf-8")))
    return keys


def test_i18n_catalogs_have_identical_leaf_keys():
    en = _flatten(json.loads(EN_JSON.read_text(encoding="utf-8")))
    zh = _flatten(json.loads(ZH_JSON.read_text(encoding="utf-8")))

    assert set(en) == set(zh)


def test_static_translation_keys_exist_in_both_catalogs():
    en = _flatten(json.loads(EN_JSON.read_text(encoding="utf-8")))
    zh = _flatten(json.loads(ZH_JSON.read_text(encoding="utf-8")))
    missing = sorted(key for key in _static_t_keys() if key not in en or key not in zh)

    assert not missing
