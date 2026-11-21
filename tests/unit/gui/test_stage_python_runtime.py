import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


def _load_stage_module():
    script_path = (
        Path(__file__).resolve().parents[3] / "ui" / "scripts" / "stage_python_runtime.py"
    )
    spec = importlib.util.spec_from_file_location("stage_python_runtime", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("stale_kind", ["directory", "symlink"])
def test_project_staging_excludes_user_data_even_at_sample_paths(tmp_path, stale_kind) -> None:
    module = _load_stage_module()
    source = tmp_path / "repo"
    target = tmp_path / "resources"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "entry.py").write_text("APPLICATION = True\n", encoding="utf-8")
    (source / "tools" / "sample_raw.txt").write_text("private replacement\n", encoding="utf-8")
    samples = (
        "evidence_cards/ec-2026-001.yaml", "evidence_cards/ec-2026-002.yaml",
        "evidence_cards/ec-2026-003.yaml", "matching_reports/mr-2026-001.yaml",
        "job_profiles/jp-2026-001.yaml", "job_profiles/jp-2026-003.yaml",
        "job_profiles/jp-2026-004.yaml", "job_profiles/jp-2026-005.yaml",
    )
    for name in samples:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("private content replacing a source demo\n", encoding="utf-8")
    outside = tmp_path / "local-data"
    outside.mkdir()
    (outside / "private.yaml").write_text("retain local user data\n", encoding="utf-8")
    target.mkdir()
    for name in ("evidence_cards", "matching_reports", "job_profiles"):
        (source / name / "local-run.yaml").write_text("private local run\n", encoding="utf-8")
        stale = target / name
        if stale_kind == "symlink":
            stale.symlink_to(outside, target_is_directory=True)
        else:
            stale.mkdir()
            (stale / "old-run.yaml").write_text("previous private bundle\n", encoding="utf-8")

    with patch.object(module, "REPO_ROOT", source), patch.object(module, "RESOURCES_DIR", target):
        module._stage_project_assets()

    assert {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()} == {
        "tools/entry.py",
    }
    assert not any((target / name).exists() for name in ("evidence_cards", "matching_reports", "job_profiles"))
    assert (outside / "private.yaml").read_text(encoding="utf-8") == "retain local user data\n"


@pytest.mark.parametrize("link_component", ["resources", "src-tauri"])
def test_project_staging_rejects_redirected_resource_root_before_cleanup(tmp_path, link_component) -> None:
    module = _load_stage_module()
    source = tmp_path / "repo"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "entry.py").write_text("APPLICATION = True\n", encoding="utf-8")
    (source / "ui").mkdir()
    outside = tmp_path / "user-workspace"
    outside.mkdir()
    target = source / "ui" / "src-tauri" / "resources"
    if link_component == "resources":
        target.parent.mkdir()
        target.symlink_to(outside, target_is_directory=True)
        actual_root = outside
    else:
        target.parent.symlink_to(outside, target_is_directory=True)
        actual_root = outside / "resources"
        actual_root.mkdir()
    for name in ("evidence_cards", "matching_reports", "job_profiles", "tools"):
        (actual_root / name).mkdir()
        (actual_root / name / "retain.txt").write_text(f"untouched {name}\n", encoding="utf-8")
    before = {path.relative_to(outside).as_posix(): path.read_bytes()
              for path in outside.rglob("*") if path.is_file()}

    with patch.object(module, "REPO_ROOT", source), patch.object(module, "RESOURCES_DIR", target):
        with pytest.raises(ValueError, match="project_resource_root_redirected"):
            module._stage_project_assets()

    after = {path.relative_to(outside).as_posix(): path.read_bytes()
             for path in outside.rglob("*") if path.is_file()}
    assert after == before


def test_project_staging_accepts_empty_user_workspace(tmp_path) -> None:
    module = _load_stage_module()
    source = tmp_path / "repo"
    target = tmp_path / "resources"
    (source / "tools").mkdir(parents=True)
    (source / "tools" / "entry.py").write_text("APPLICATION = True\n", encoding="utf-8")
    with patch.object(module, "REPO_ROOT", source), patch.object(module, "RESOURCES_DIR", target):
        module._stage_project_assets()
    assert (target / "tools" / "entry.py").is_file()


def test_staged_sidecar_lists_empty_workspace_without_seed_data(tmp_path) -> None:
    module = _load_stage_module()
    target = tmp_path / "resources"
    with patch.object(module, "RESOURCES_DIR", target):
        module._stage_project_assets()
    methods = ("system.handshake", "system.ping", "overview.get", "evidence.list",
               "jobs.listProfiles", "jobs.listLeads")
    requests = [
        {"jsonrpc": "2.0", "id": str(index), "method": method,
         "params": {"meta": {"correlation_id": "empty-workspace"}, "protocol_version": "1.0.0"}}
        for index, method in enumerate(methods)
    ]
    result = subprocess.run(
        [sys.executable, "-m", "tools.sidecar.server"],
        input="".join(json.dumps(request) + "\n" for request in requests),
        cwd=target, text=True, capture_output=True, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == len(requests), result.stdout
    assert all("error" not in response for response in responses), responses
    assert responses[0]["result"]["accepted_protocol_version"] == "1.0.0"
    assert responses[1]["result"]["state"] == "ready"
    metrics = responses[2]["result"]["metrics"]
    assert all(metrics[name] == 0 for name in
               ("evidence_count", "matched_jobs_count", "resume_count", "submission_count"))
    assert all(response["result"]["items"] == [] for response in responses[3:])


def test_stages_optional_pdf_packages_and_metadata() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        target = root / "target"
        package_dir = source / "weasyprint"
        dist_info = source / "weasyprint-65.1.dist-info"
        package_dir.mkdir(parents=True)
        dist_info.mkdir()
        (package_dir / "__init__.py").write_text("VERSION = 'test'\n", encoding="utf-8")
        (package_dir / "__pycache__").mkdir()
        (package_dir / "__pycache__" / "ignored.pyc").write_bytes(b"cache")
        (dist_info / "METADATA").write_text("Name: weasyprint\n", encoding="utf-8")

        copied = module._stage_optional_python_packages(
            version="3.14",
            source_roots=[source],
            target_site_packages=target,
            package_map={"weasyprint": ("weasyprint",)},
        )

        assert "weasyprint" in copied
        assert (target / "weasyprint" / "__init__.py").exists()
        assert not (target / "weasyprint" / "__pycache__").exists()
        assert (target / "weasyprint-65.1.dist-info" / "METADATA").exists()
        assert "weasyprint" in (
            target / "piproofforge-pdf-runtime.txt"
        ).read_text(encoding="utf-8")


def test_distribution_metadata_matching_does_not_use_prefix_only() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        target = root / "target"
        markdown_dir = source / "markdown"
        weasyprint_dir = source / "weasyprint"
        markdown_it_dist = source / "markdown_it_py-3.0.0.dist-info"
        markdown_dist = source / "Markdown-3.8.dist-info"
        markdown_dir.mkdir(parents=True)
        weasyprint_dir.mkdir()
        markdown_it_dist.mkdir()
        markdown_dist.mkdir()
        (markdown_dir / "__init__.py").write_text("", encoding="utf-8")
        (weasyprint_dir / "__init__.py").write_text("", encoding="utf-8")
        (markdown_it_dist / "METADATA").write_text(
            "Name: markdown-it-py\n", encoding="utf-8"
        )
        (markdown_dist / "METADATA").write_text("Name: Markdown\n", encoding="utf-8")

        module._stage_optional_python_packages(
            version="3.14",
            source_roots=[source],
            target_site_packages=target,
            package_map={"markdown": ("Markdown",), "weasyprint": ("weasyprint",)},
        )

        assert (target / "Markdown-3.8.dist-info").exists()
        assert not (target / "markdown_it_py-3.0.0.dist-info").exists()


def test_staging_removes_stale_optional_packages_when_missing() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        target = root / "target"
        source.mkdir()
        (target / "markdown").mkdir(parents=True)
        (target / "Markdown-3.8.dist-info").mkdir()

        copied = module._stage_optional_python_packages(
            version="3.14",
            source_roots=[source],
            target_site_packages=target,
            package_map={"markdown": ("Markdown",)},
        )

        assert copied == []
        assert not (target / "markdown").exists()
        assert not (target / "Markdown-3.8.dist-info").exists()
        assert (target / "piproofforge-pdf-runtime.txt").read_text(
            encoding="utf-8"
        ) == "\n"


def test_staging_honors_explicit_empty_source_roots() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        target = Path(tmp_dir) / "target"

        copied = module._stage_optional_python_packages(
            version="3.14",
            source_roots=[],
            target_site_packages=target,
            package_map={"markdown": ("Markdown",)},
        )

        assert copied == []
        assert (target / "piproofforge-pdf-runtime.txt").exists()


def test_staging_does_not_copy_transitive_packages_without_pdf_runtime() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        target = root / "target"
        cffi_dir = source / "cffi"
        cffi_dir.mkdir(parents=True)
        (cffi_dir / "__init__.py").write_text("", encoding="utf-8")

        copied = module._stage_optional_python_packages(
            version="3.14",
            source_roots=[source],
            target_site_packages=target,
            package_map={"markdown": ("Markdown",), "cffi": ("cffi",)},
        )

        assert copied == []
        assert not (target / "cffi").exists()


def test_staging_requires_complete_pdf_runtime_before_copying_group() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        source = root / "source"
        target = root / "target"
        markdown_dir = source / "markdown"
        cffi_dir = source / "cffi"
        markdown_dir.mkdir(parents=True)
        cffi_dir.mkdir()
        (markdown_dir / "__init__.py").write_text("", encoding="utf-8")
        (cffi_dir / "__init__.py").write_text("", encoding="utf-8")

        copied = module._stage_optional_python_packages(
            version="3.14",
            source_roots=[source],
            target_site_packages=target,
            package_map={
                "markdown": ("Markdown",),
                "weasyprint": ("weasyprint",),
                "cffi": ("cffi",),
            },
        )

        assert copied == []
        assert not (target / "markdown").exists()
        assert not (target / "cffi").exists()


def test_validate_optional_pdf_runtime_checks_staged_imports() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        bin_dir = Path(tmp_dir) / "sidecar" / "bin"
        wrapper = bin_dir / "python3"
        bin_dir.mkdir(parents=True)
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

        with patch.object(module, "SIDECAR_BIN_DIR", bin_dir):
            with patch.object(
                module.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=0, stdout="ok"),
            ) as run_mock:
                module._validate_optional_pdf_runtime(["weasyprint"])

        assert run_mock.called
        assert run_mock.call_args.args[0][0] == str(wrapper)
        assert "from weasyprint import HTML" in run_mock.call_args.args[0][2]


def test_validate_optional_pdf_runtime_fails_on_broken_staged_imports() -> None:
    module = _load_stage_module()
    with TemporaryDirectory() as tmp_dir:
        bin_dir = Path(tmp_dir) / "sidecar" / "bin"
        wrapper = bin_dir / "python3"
        bin_dir.mkdir(parents=True)
        wrapper.write_text("#!/bin/sh\n", encoding="utf-8")

        with patch.object(module, "SIDECAR_BIN_DIR", bin_dir):
            with patch.object(
                module.subprocess,
                "run",
                return_value=CompletedProcess(args=[], returncode=1, stderr="boom"),
            ):
                try:
                    module._validate_optional_pdf_runtime(["markdown", "weasyprint"])
                    assert False, "Expected RuntimeError"
                except RuntimeError as error:
                    assert "failed to import" in str(error)
