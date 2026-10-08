"""只用临时目录与合成凭据验证本地权限文件。"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import traceback

import pytest

from tools.infra import liepin_token_file as storage


TOKEN = "unit-test-private-token"


@pytest.fixture
def store(tmp_path):
    return storage.LiepinTokenFile(tmp_path / "private" / "credentials" / "liepin-token")


def assert_storage_error(call):
    with pytest.raises(storage.CredentialStorageError) as caught:
        call()
    error = caught.value
    assert str(error) == "本地凭据文件操作失败。"
    assert TOKEN not in "".join(traceback.format_exception(error))
    assert error.__context__ is None
    assert error.__cause__ is None
    return error


def test_constructor_and_missing_reads_do_not_create_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    value = storage.LiepinTokenFile()
    assert value.path == tmp_path / "Library/Application Support/PiProofForge/credentials/liepin-token"
    assert list(tmp_path.iterdir()) == []
    assert value.load() is None
    value.delete()
    assert list(tmp_path.iterdir()) == []


def test_saved_token_survives_new_object_with_restricted_permissions(store):
    store.save(TOKEN)
    assert storage.LiepinTokenFile(store.path).load() == TOKEN
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.parent.parent.stat().st_mode) == 0o700
    assert store.path.stat().st_uid == os.getuid()
    assert TOKEN not in repr(store)
    store.save("replacement-token")
    assert store.load() == "replacement-token"
    store.delete()
    assert store.load() is None
    store.delete()


def test_failed_atomic_replacement_keeps_original_and_removes_temporary_file(store, monkeypatch):
    store.save(TOKEN)

    def fail_replace(*args, **kwargs):
        raise PermissionError(TOKEN)

    monkeypatch.setattr(storage.os, "replace", fail_replace)
    assert_storage_error(lambda: store.save("replacement-token"))
    assert store.load() == TOKEN
    assert list(store.path.parent.iterdir()) == [store.path]


def test_failed_write_keeps_original_and_removes_temporary_file(store, monkeypatch):
    store.save(TOKEN)

    def fail_sync(*args, **kwargs):
        raise OSError(TOKEN)

    monkeypatch.setattr(storage.os, "fsync", fail_sync)
    assert_storage_error(lambda: store.save("replacement-token"))
    assert store.load() == TOKEN
    assert list(store.path.parent.iterdir()) == [store.path]


def test_temporary_name_collision_does_not_delete_existing_file(store, monkeypatch):
    store.save(TOKEN)
    temporary = store.path.parent / ".liepin-token.collision.tmp"
    temporary.write_text("existing-file", encoding="utf-8")
    temporary.chmod(0o600)
    monkeypatch.setattr(storage.secrets, "token_hex", lambda size: "collision")
    assert_storage_error(lambda: store.save("replacement-token"))
    assert store.load() == TOKEN
    assert temporary.read_text(encoding="utf-8") == "existing-file"


def test_delete_failure_preserves_saved_value_and_hides_error(store, monkeypatch):
    store.save(TOKEN)

    def fail_unlink(*args, **kwargs):
        raise PermissionError(TOKEN)

    monkeypatch.setattr(storage.os, "unlink", fail_unlink)
    assert_storage_error(store.delete)
    assert store.load() == TOKEN


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
@pytest.mark.parametrize("location", ["file", "directory", "ancestor"])
def test_symlinks_are_rejected_without_touching_target(store, tmp_path, operation, location):
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    real_file = actual / "liepin-token"
    real_file.write_text(TOKEN, encoding="utf-8")
    real_file.chmod(0o600)
    if location == "file":
        store.path.parent.mkdir(parents=True, mode=0o700)
        store.path.symlink_to(real_file)
    elif location == "directory":
        store.path.parent.parent.mkdir(mode=0o700)
        store.path.parent.symlink_to(actual, target_is_directory=True)
    else:
        store.path.parent.parent.symlink_to(actual, target_is_directory=True)
    call = (lambda: store.save("replacement-token")) if operation == "save" else getattr(store, operation)
    assert_storage_error(call)
    assert real_file.read_text(encoding="utf-8") == TOKEN


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
@pytest.mark.parametrize(("location", "mode"), [("file", 0o644), ("file", 0o400), ("directory", 0o755)])
def test_existing_unsafe_permissions_are_rejected(store, operation, location, mode):
    store.save(TOKEN)
    target = store.path if location == "file" else store.path.parent
    target.chmod(mode)
    call = (lambda: store.save("replacement-token")) if operation == "save" else getattr(store, operation)
    assert_storage_error(call)
    assert stat.S_IMODE(target.stat().st_mode) == mode


@pytest.mark.parametrize("kind", ["directory", "fifo"])
@pytest.mark.parametrize("operation", ["load", "save", "delete"])
def test_non_regular_target_is_rejected(store, operation, kind):
    store.path.parent.mkdir(parents=True, mode=0o700)
    if kind == "directory":
        store.path.mkdir(mode=0o600)
    else:
        os.mkfifo(store.path, mode=0o600)
    call = (lambda: store.save("replacement-token")) if operation == "save" else getattr(store, operation)
    assert_storage_error(call)


@pytest.mark.parametrize("operation", ["load", "save", "delete"])
def test_wrong_owner_is_rejected(store, monkeypatch, operation):
    store.save(TOKEN)
    actual_uid = os.getuid()
    monkeypatch.setattr(storage.os, "getuid", lambda: actual_uid + 1)
    call = (lambda: store.save("replacement-token")) if operation == "save" else getattr(store, operation)
    assert_storage_error(call)


@pytest.mark.parametrize("raw", [b"", b"bad\nvalue", b"\xff", b"x" * 32769])
def test_invalid_file_content_returns_safe_error(store, raw):
    store.save(TOKEN)
    store.path.write_bytes(raw)
    assert_storage_error(store.load)


def test_unsupported_platform_fails_without_filesystem_access(store, monkeypatch):
    monkeypatch.setattr(storage.os, "name", "nt")
    assert_storage_error(store.load)
    assert_storage_error(lambda: store.save(TOKEN))
    assert_storage_error(store.delete)


@pytest.mark.parametrize("token", ["", "  ", "bad\nvalue", "x" * 8193, None])
def test_invalid_save_does_not_create_file(store, token):
    assert_storage_error(lambda: store.save(token))
    assert not store.path.parent.exists()
