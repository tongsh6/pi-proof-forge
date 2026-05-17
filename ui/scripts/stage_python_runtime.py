from __future__ import annotations

import re
import shutil
import subprocess
import sys
import sysconfig
from os.path import relpath
from pathlib import Path


UI_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = UI_DIR.parent
RESOURCES_DIR = UI_DIR / "src-tauri" / "resources"
PYTHON_RESOURCES_DIR = RESOURCES_DIR / "python"
SIDECAR_BIN_DIR = RESOURCES_DIR / "sidecar" / "bin"
FRAMEWORK_NAME = "Python.framework"
PYTHON_VERSION = f"{sys.version_info.major}.{sys.version_info.minor}"
KEEP_BIN_NAMES = {"python3", f"python{PYTHON_VERSION}"}
KEEP_LIB_NAMES = {
    f"libpython{PYTHON_VERSION}.dylib",
    "libssl.dylib",
    "libssl.3.dylib",
    "libcrypto.dylib",
    "libcrypto.3.dylib",
}
PDF_RUNTIME_PACKAGES = {
    "markdown": ("Markdown",),
    "weasyprint": ("weasyprint",),
    "pydyf": ("pydyf",),
    "tinycss2": ("tinycss2",),
    "cssselect2": ("cssselect2",),
    "tinyhtml5": ("tinyhtml5",),
    "html5lib": ("html5lib",),
    "webencodings": ("webencodings",),
    "fontTools": ("fonttools",),
    "PIL": ("pillow",),
    "pyphen": ("pyphen",),
    "cffi": ("cffi",),
    "pycparser": ("pycparser",),
    "brotli": ("brotli", "brotlicffi"),
    "zopfli": ("zopfli",),
}
PDF_RUNTIME_ACTIVATION_IMPORTS = ("markdown", "weasyprint")
RUNTIME_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "site-packages",
    "test",
    "tests",
    "tkinter",
    "turtledemo",
    "idlelib",
    "ensurepip",
    "lib2to3",
)
OPTIONAL_PACKAGE_IGNORE = shutil.ignore_patterns(
    "__pycache__",
    "*.pyc",
    "*.pyo",
    ".DS_Store",
    "tests",
    "test",
)


def _copytree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    _ = shutil.copytree(source, target, symlinks=False, ignore=RUNTIME_IGNORE)


def _copytree_with_ignore(source: Path, target: Path, *ignore_patterns: str) -> None:
    if target.exists():
        shutil.rmtree(target)
    _ = shutil.copytree(
        source,
        target,
        symlinks=False,
        ignore=shutil.ignore_patterns(*ignore_patterns),
    )


def _copy_optional_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    _ = shutil.copytree(
        source,
        target,
        symlinks=False,
        ignore=OPTIONAL_PACKAGE_IGNORE,
    )


def _copy_file(source: Path, target: Path) -> None:
    _ = target.parent.mkdir(parents=True, exist_ok=True)
    _ = shutil.copy2(source, target)


def _run_command(*args: str) -> str:
    return subprocess.check_output(args, text=True)


def _detect_framework_root() -> Path:
    executable = Path(sys.executable).resolve()
    framework_root = executable.parents[3]
    if framework_root.name != FRAMEWORK_NAME:
        raise RuntimeError(
            f"Unsupported Python layout for bundling: {executable}. Expected a macOS framework build."
        )
    return framework_root


def _stage_framework() -> tuple[Path, str]:
    framework_root = _detect_framework_root()
    version = PYTHON_VERSION
    source_version_dir = framework_root / "Versions" / version
    target_framework_root = PYTHON_RESOURCES_DIR / FRAMEWORK_NAME
    target_version_dir = target_framework_root / "Versions" / version

    if not source_version_dir.exists():
        raise RuntimeError(f"Python version directory not found: {source_version_dir}")

    if target_framework_root.exists():
        shutil.rmtree(target_framework_root)

    target_framework_root.parent.mkdir(parents=True, exist_ok=True)
    (target_framework_root / "Versions").mkdir(parents=True, exist_ok=True)

    target_version_dir.mkdir(parents=True, exist_ok=True)

    _copy_file(source_version_dir / "Python", target_version_dir / "Python")
    _copy_framework_bin(source_version_dir / "bin", target_version_dir / "bin")
    _copy_framework_lib(source_version_dir / "lib", target_version_dir / "lib")
    _copy_framework_resources(
        source_version_dir / "Resources", target_version_dir / "Resources"
    )
    _prune_unused_runtime_bits(target_version_dir)
    _relink_runtime(source_version_dir, target_version_dir)
    _codesign_runtime(target_framework_root, target_version_dir)
    _validate_runtime_relink(source_version_dir, target_version_dir)

    return target_framework_root, version


def _copy_framework_bin(source_bin_dir: Path, target_bin_dir: Path) -> None:
    target_bin_dir.mkdir(parents=True, exist_ok=True)
    for name in KEEP_BIN_NAMES:
        _copy_file(source_bin_dir / name, target_bin_dir / name)


def _copy_framework_lib(source_lib_dir: Path, target_lib_dir: Path) -> None:
    target_lib_dir.mkdir(parents=True, exist_ok=True)

    for name in KEEP_LIB_NAMES:
        source = source_lib_dir / name
        if source.exists():
            _copy_file(source, target_lib_dir / name)

    sqlite_dir = source_lib_dir / "sqlite3.40.0"
    if sqlite_dir.exists():
        _copytree(sqlite_dir, target_lib_dir / "sqlite3.40.0")

    stdlib_dir = source_lib_dir / f"python{PYTHON_VERSION}"
    _copytree(stdlib_dir, target_lib_dir / f"python{PYTHON_VERSION}")


def _copy_framework_resources(
    source_resources_dir: Path, target_resources_dir: Path
) -> None:
    if source_resources_dir.exists():
        _copytree_with_ignore(
            source_resources_dir, target_resources_dir, "_CodeSignature"
        )


def _normalize_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _metadata_distribution_stem(path: Path) -> str:
    for suffix in (".dist-info", ".egg-info"):
        if path.name.endswith(suffix):
            return path.name[: -len(suffix)]
    return path.name


def _metadata_distribution_name(path: Path) -> str:
    metadata_candidates = (
        [path / "METADATA", path / "PKG-INFO"] if path.is_dir() else [path]
    )
    for metadata_path in metadata_candidates:
        if not metadata_path.exists():
            continue
        try:
            for line in metadata_path.read_text(encoding="utf-8").splitlines():
                if line.lower().startswith("name:"):
                    return _normalize_distribution_name(line.split(":", 1)[1].strip())
        except UnicodeDecodeError:
            continue

    stem = _metadata_distribution_stem(path)
    name_without_version = stem.rsplit("-", maxsplit=1)[0]
    return _normalize_distribution_name(name_without_version)


def _metadata_matches_distribution(path: Path, dist_names: set[str]) -> bool:
    return _metadata_distribution_name(path) in dist_names


def _site_package_roots() -> list[Path]:
    candidates: list[Path] = []
    paths = sysconfig.get_paths()
    for key in ("purelib", "platlib"):
        value = paths.get(key)
        if value:
            candidates.append(Path(value))

    for entry in sys.path:
        path = Path(entry)
        if path.name in {"site-packages", "dist-packages"}:
            candidates.append(path)

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.exists() and resolved not in seen:
            unique.append(resolved)
            seen.add(resolved)
    return unique


def _target_site_packages(version: str) -> Path:
    return (
        PYTHON_RESOURCES_DIR
        / FRAMEWORK_NAME
        / "Versions"
        / version
        / "lib"
        / f"python{PYTHON_VERSION}"
        / "site-packages"
    )


def _remove_staged_optional_packages(
    target_site_packages: Path,
    package_map: dict[str, tuple[str, ...]],
) -> None:
    dist_names = {
        _normalize_distribution_name(dist_name)
        for dist_names_for_import in package_map.values()
        for dist_name in dist_names_for_import
    }

    for import_name in package_map:
        target = target_site_packages / import_name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    if not target_site_packages.exists():
        return

    for child in target_site_packages.iterdir():
        if not child.name.endswith((".dist-info", ".egg-info")):
            continue
        if _metadata_matches_distribution(child, dist_names):
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()


def _copy_distribution_metadata(
    source_roots: list[Path],
    target_site_packages: Path,
    dist_names: tuple[str, ...],
) -> list[str]:
    copied: list[str] = []
    normalized_names = {_normalize_distribution_name(name) for name in dist_names}
    for source_root in source_roots:
        for child in source_root.iterdir():
            if not child.name.endswith((".dist-info", ".egg-info")):
                continue
            if not _metadata_matches_distribution(child, normalized_names):
                continue
            target = target_site_packages / child.name
            if child.is_dir():
                _copy_optional_tree(child, target)
            else:
                _copy_file(child, target)
            copied.append(child.name)
    return copied


def _has_optional_runtime_activation_package(
    source_roots: list[Path],
    package_map: dict[str, tuple[str, ...]],
) -> bool:
    activation_imports = [
        import_name
        for import_name in PDF_RUNTIME_ACTIVATION_IMPORTS
        if import_name in package_map
    ] or list(package_map)
    return all(
        any((source_root / import_name).exists() for source_root in source_roots)
        for import_name in activation_imports
    )


def _stage_optional_python_packages(
    version: str,
    source_roots: list[Path] | None = None,
    target_site_packages: Path | None = None,
    package_map: dict[str, tuple[str, ...]] | None = None,
) -> list[str]:
    if package_map is None:
        package_map = PDF_RUNTIME_PACKAGES
    if source_roots is None:
        source_roots = _site_package_roots()
    if target_site_packages is None:
        target_site_packages = _target_site_packages(version)
    target_site_packages.mkdir(parents=True, exist_ok=True)
    _remove_staged_optional_packages(target_site_packages, package_map)

    if not _has_optional_runtime_activation_package(source_roots, package_map):
        _write_optional_runtime_manifest(target_site_packages, [])
        return []

    copied: list[str] = []
    for import_name, dist_names in package_map.items():
        for source_root in source_roots:
            source = source_root / import_name
            if not source.exists():
                continue
            target = target_site_packages / import_name
            if source.is_dir():
                _copy_optional_tree(source, target)
            else:
                _copy_file(source, target)
            copied.append(import_name)
            copied.extend(
                _copy_distribution_metadata(
                    source_roots, target_site_packages, dist_names
                )
            )
            break

    _write_optional_runtime_manifest(target_site_packages, copied)
    return copied


def _write_optional_runtime_manifest(
    target_site_packages: Path, copied_packages: list[str]
) -> None:
    manifest_path = target_site_packages / "piproofforge-pdf-runtime.txt"
    manifest_path.write_text(
        "\n".join(sorted(set(copied_packages))) + "\n",
        encoding="utf-8",
    )


def _validate_optional_pdf_runtime(copied_packages: list[str]) -> None:
    copied = set(copied_packages)
    if not {"markdown", "weasyprint"}.issubset(copied):
        return

    wrapper_path = SIDECAR_BIN_DIR / "python3"
    if not wrapper_path.exists():
        raise RuntimeError(f"Python wrapper not found: {wrapper_path}")

    completed = subprocess.run(
        [
            str(wrapper_path),
            "-c",
            (
                "from pathlib import Path\n"
                "from tempfile import TemporaryDirectory\n"
                "from tools.infra.export.pdf_exporter import markdown_to_pdf\n"
                "with TemporaryDirectory() as tmp:\n"
                "    md = Path(tmp) / 'probe.md'\n"
                "    pdf = Path(tmp) / 'probe.pdf'\n"
                "    md.write_text('# PDF Runtime Probe\\n', encoding='utf-8')\n"
                "    markdown_to_pdf(md, pdf)\n"
                "    assert pdf.read_bytes().startswith(b'%PDF-')\n"
                "print('optional pdf runtime ok')\n"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "Staged optional PDF runtime failed to import markdown/weasyprint:\n"
            f"{completed.stderr or completed.stdout}"
        )


def _prune_unused_runtime_bits(target_version_dir: Path) -> None:
    unused_paths = [
        target_version_dir
        / "lib"
        / f"python{PYTHON_VERSION}"
        / "lib-dynload"
        / f"_curses.cpython-{sys.version_info.major}{sys.version_info.minor}-darwin.so",
        target_version_dir
        / "lib"
        / f"python{PYTHON_VERSION}"
        / "lib-dynload"
        / f"_curses_panel.cpython-{sys.version_info.major}{sys.version_info.minor}-darwin.so",
        target_version_dir
        / "lib"
        / f"python{PYTHON_VERSION}"
        / "lib-dynload"
        / f"_tkinter.cpython-{sys.version_info.major}{sys.version_info.minor}-darwin.so",
        target_version_dir
        / "lib"
        / f"python{PYTHON_VERSION}"
        / f"config-{PYTHON_VERSION}-darwin",
    ]

    for path in unused_paths:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def _iter_macho_files(root: Path) -> list[Path]:
    macho_files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        file_output = _run_command("file", "-b", str(path))
        if "Mach-O" in file_output:
            macho_files.append(path)
    return macho_files


def _loader_path_reference(from_path: Path, to_path: Path) -> str:
    relative_path = Path(relpath(to_path, start=from_path.parent))
    return f"@loader_path/{relative_path.as_posix()}"


def _set_install_id(binary_path: Path) -> None:
    install_id = f"@loader_path/{binary_path.name}"
    _ = subprocess.run(
        ["install_name_tool", "-id", install_id, str(binary_path)],
        check=True,
        capture_output=True,
        text=True,
    )


def _relink_runtime(source_version_dir: Path, target_version_dir: Path) -> None:
    rewrite_targets = {
        str(source_version_dir / "Python"): target_version_dir / "Python",
        str(
            source_version_dir / "lib" / f"libpython{PYTHON_VERSION}.dylib"
        ): target_version_dir / "lib" / f"libpython{PYTHON_VERSION}.dylib",
        str(source_version_dir / "lib" / "libssl.dylib"): target_version_dir
        / "lib"
        / "libssl.dylib",
        str(source_version_dir / "lib" / "libssl.3.dylib"): target_version_dir
        / "lib"
        / "libssl.3.dylib",
        str(source_version_dir / "lib" / "libcrypto.dylib"): target_version_dir
        / "lib"
        / "libcrypto.dylib",
        str(source_version_dir / "lib" / "libcrypto.3.dylib"): target_version_dir
        / "lib"
        / "libcrypto.3.dylib",
    }
    install_id_files = [
        target_version_dir / "Python",
        target_version_dir / "lib" / f"libpython{PYTHON_VERSION}.dylib",
        target_version_dir / "lib" / "libssl.dylib",
        target_version_dir / "lib" / "libssl.3.dylib",
        target_version_dir / "lib" / "libcrypto.dylib",
        target_version_dir / "lib" / "libcrypto.3.dylib",
    ]

    for binary_path in install_id_files:
        if binary_path.exists():
            _set_install_id(binary_path)

    for binary_path in _iter_macho_files(target_version_dir):
        links_output = _run_command("otool", "-L", str(binary_path))
        link_lines = links_output.splitlines()[1:]
        current_links = {
            line.strip().split(" (", maxsplit=1)[0]
            for line in link_lines
            if line.strip()
        }

        for source_link, target_binary in rewrite_targets.items():
            if source_link not in current_links or not target_binary.exists():
                continue
            replacement = _loader_path_reference(binary_path, target_binary)
            _ = subprocess.run(
                [
                    "install_name_tool",
                    "-change",
                    source_link,
                    replacement,
                    str(binary_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )


def _validate_runtime_relink(
    source_version_dir: Path, target_version_dir: Path
) -> None:
    source_prefix = str(source_version_dir)
    unresolved: list[tuple[Path, str]] = []

    for binary_path in _iter_macho_files(target_version_dir):
        links_output = _run_command("otool", "-L", str(binary_path))
        for line in links_output.splitlines()[1:]:
            dependency = line.strip().split(" (", maxsplit=1)[0]
            if dependency.startswith(source_prefix):
                unresolved.append((binary_path, dependency))

    if unresolved:
        details = "\n".join(
            f"{binary_path} -> {dependency}" for binary_path, dependency in unresolved
        )
        raise RuntimeError(
            f"Bundled runtime still references source Python framework:\n{details}"
        )


def _codesign_runtime(target_framework_root: Path, target_version_dir: Path) -> None:
    _ = target_framework_root
    macho_files = sorted(
        _iter_macho_files(target_version_dir),
        key=lambda path: len(path.parts),
        reverse=True,
    )

    for binary_path in macho_files:
        _ = subprocess.run(
            [
                "codesign",
                "--force",
                "--sign",
                "-",
                "--timestamp=none",
                str(binary_path),
            ],
            check=True,
            capture_output=True,
            text=True,
        )


def _write_python_wrapper(version: str) -> None:
    SIDECAR_BIN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = SIDECAR_BIN_DIR / "python3"
    wrapper = f"""#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- \"$(dirname \"$0\")\" && pwd)
RESOURCE_ROOT=\"$SCRIPT_DIR/../..\"
PYTHON_ROOT=\"$SCRIPT_DIR/../../python/{FRAMEWORK_NAME}/Versions/{version}\"
export PYTHONHOME=\"$PYTHON_ROOT\"
export PYTHONPATH=\"$RESOURCE_ROOT${{PYTHONPATH:+:$PYTHONPATH}}\"
exec \"$PYTHON_ROOT/bin/python3\" \"$@\"
"""
    _ = wrapper_path.write_text(wrapper, encoding="utf-8")
    _ = wrapper_path.chmod(0o755)


def _write_metadata(version: str) -> None:
    metadata_path = PYTHON_RESOURCES_DIR / "runtime.txt"
    _ = metadata_path.write_text(_runtime_metadata(version), encoding="utf-8")


def _runtime_metadata(version: str) -> str:
    return (
        "\n".join(
            [
                f"python_executable={sys.executable}",
                f"python_version={sys.version.split()[0]}",
                f"python_stdlib={sysconfig.get_paths()['stdlib']}",
                f"bundled_version={version}",
            ]
        )
        + "\n"
    )


def _staged_runtime_is_current() -> bool:
    metadata_path = PYTHON_RESOURCES_DIR / "runtime.txt"
    wrapper_path = SIDECAR_BIN_DIR / "python3"
    version_dir = PYTHON_RESOURCES_DIR / FRAMEWORK_NAME / "Versions" / PYTHON_VERSION
    runtime_bin = version_dir / "bin" / "python3"

    if not metadata_path.exists() or not wrapper_path.exists() or not runtime_bin.exists():
        return False
    return metadata_path.read_text(encoding="utf-8") == _runtime_metadata(PYTHON_VERSION)


def _stage_project_assets() -> None:
    asset_dirs = {
        "tools": REPO_ROOT / "tools",
        "evidence_cards": REPO_ROOT / "evidence_cards",
        "matching_reports": REPO_ROOT / "matching_reports",
        "job_profiles": REPO_ROOT / "job_profiles",
    }

    for name, source_dir in asset_dirs.items():
        if not source_dir.exists():
            continue
        _copytree(source_dir, RESOURCES_DIR / name)


def main() -> None:
    if sys.platform != "darwin":
        raise RuntimeError(
            "This staging script currently supports macOS framework Python only."
        )

    _stage_project_assets()
    if _staged_runtime_is_current():
        copied = _stage_optional_python_packages(PYTHON_VERSION)
        _validate_optional_pdf_runtime(copied)
        print(f"Using staged Python {PYTHON_VERSION} from {PYTHON_RESOURCES_DIR}")
        if copied:
            print(f"Staged optional PDF packages: {', '.join(sorted(set(copied)))}")
        return

    _, version = _stage_framework()
    _write_python_wrapper(version)
    copied = _stage_optional_python_packages(version)
    _validate_optional_pdf_runtime(copied)
    _write_metadata(version)
    print(f"Bundled Python {version} into {PYTHON_RESOURCES_DIR}")
    if copied:
        print(f"Staged optional PDF packages: {', '.join(sorted(set(copied)))}")


if __name__ == "__main__":
    main()
