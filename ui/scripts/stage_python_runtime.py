from __future__ import annotations

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
    _ = metadata_path.write_text(
        "\n".join(
            [
                f"python_executable={sys.executable}",
                f"python_version={sys.version.split()[0]}",
                f"python_stdlib={sysconfig.get_paths()['stdlib']}",
                f"bundled_version={version}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


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
    _, version = _stage_framework()
    _write_python_wrapper(version)
    _write_metadata(version)
    print(f"Bundled Python {version} into {PYTHON_RESOURCES_DIR}")


if __name__ == "__main__":
    main()
