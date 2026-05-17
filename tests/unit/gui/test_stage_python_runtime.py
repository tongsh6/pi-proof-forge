import importlib.util
from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch


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
                module._validate_optional_pdf_runtime(["markdown", "weasyprint"])

        assert run_mock.call_args.args[0][0] == str(wrapper)


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
