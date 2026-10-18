"""引用外部目录已迁到系统设置：证据页抽屉只留跳转，设置页承载扫描/创建/检查/刷新/解除。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_reference_management_lives_in_settings():
    evidence = (ROOT / "ui/src/pages/evidence/index.tsx").read_text(encoding="utf-8")
    settings = (ROOT / "ui/src/pages/system-settings/index.tsx").read_text(encoding="utf-8")

    # 证据页只剩抽屉入口与设置跳转，不再有引用目录管理面板。
    assert "evidence-open-drawer" in evidence
    assert "referenceMoved" in evidence and "/system-settings?section=materialSources" in evidence
    for removed in ("material-reference-scan", "material-reference-create", "material-reference-check", "material-reference-refresh", "material-reference-remove", "createMaterialReference"):
        assert removed not in evidence, removed

    # 设置页承载全部引用操作与确认。
    for marker in (
        "material-reference-card",
        "material-reference-root",
        "material-reference-relpath",
        "material-reference-scan",
        "material-reference-label",
        "material-reference-create",
        "material-reference-list",
        "material-reference-check",
        "material-reference-refresh",
        "material-reference-remove",
        "scanMaterialReference",
        "createMaterialReference",
        "checkMaterialReference",
        "refreshMaterialReference",
        "removeMaterialReference",
        "referenceRefreshConfirm",
        "referenceRemoveConfirm",
    ):
        assert marker in settings, marker
