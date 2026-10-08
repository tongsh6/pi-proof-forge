"""按用户授权保存猎聘 Token；仅支持 POSIX 本地权限文件。"""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import stat


_MAX_BYTES = 32768


class CredentialStorageError(Exception):
    """固定错误，不保留凭据、路径或底层异常正文。"""

    def __init__(self) -> None:
        super().__init__("本地凭据文件操作失败。")


class LiepinTokenFile:
    def __init__(self, path: Path | None = None) -> None:
        selected = path if path is not None else (
            Path.home() / "Library/Application Support/PiProofForge/credentials/liepin-token"
        )
        self._path = Path(os.path.abspath(selected))

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> str | None:
        try:
            return self._load()
        except (OSError, ValueError, TypeError):
            pass
        # 在 except 块外抛出，避免错误对象携带底层异常。
        raise CredentialStorageError()

    def save(self, token: str) -> None:
        try:
            self._save(token)
            return
        except (OSError, ValueError, TypeError):
            pass
        raise CredentialStorageError()

    def delete(self) -> None:
        try:
            directory = self._open_directory(create=False)
            if directory is None:
                return
            try:
                if self._target_stat(directory) is not None:
                    os.unlink(self.path.name, dir_fd=directory)
            finally:
                os.close(directory)
            return
        except (OSError, ValueError, TypeError):
            pass
        raise CredentialStorageError()

    @staticmethod
    def _validate_token(token: str) -> bytes:
        if (not isinstance(token, str) or not token.strip() or len(token) > 8192
                or any(ord(char) < 32 or ord(char) == 127 for char in token)):
            raise ValueError("invalid credential")
        return token.encode("utf-8")

    @staticmethod
    def _validate_stat(info: os.stat_result, *, directory: bool) -> None:
        required_mode = 0o700 if directory else 0o600
        correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
        if (not correct_type or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != required_mode
                or (not directory and info.st_nlink != 1)):
            raise OSError("unsafe credential storage")

    def _open_directory(self, *, create: bool) -> int | None:
        if os.name != "posix":
            raise OSError("unsupported credential storage platform")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        directory = os.open(self.path.anchor, flags)
        try:
            # 从根逐级打开，避免凭据目录或中间目录被符号链接替代。
            for part in self.path.parent.parts[1:]:
                try:
                    child = os.open(part, flags, dir_fd=directory)
                except FileNotFoundError:
                    if not create:
                        return None
                    created = False
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=directory)
                        created = True
                    except FileExistsError:
                        pass
                    child = os.open(part, flags, dir_fd=directory)
                    if created:
                        try:
                            os.fchmod(child, 0o700)
                        except OSError:
                            os.close(child)
                            raise
                os.close(directory)
                directory = child
            self._validate_stat(os.fstat(directory), directory=True)
            result, directory = directory, -1
            return result
        finally:
            if directory >= 0:
                os.close(directory)

    def _target_stat(self, directory: int) -> os.stat_result | None:
        try:
            info = os.stat(self.path.name, dir_fd=directory, follow_symlinks=False)
        except FileNotFoundError:
            return None
        self._validate_stat(info, directory=False)
        return info

    def _load(self) -> str | None:
        directory = self._open_directory(create=False)
        if directory is None:
            return None
        try:
            if self._target_stat(directory) is None:
                return None
            descriptor = os.open(
                self.path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                dir_fd=directory,
            )
            try:
                info = os.fstat(descriptor)
                self._validate_stat(info, directory=False)
                if info.st_size > _MAX_BYTES:
                    raise ValueError("credential file too large")
                content = bytearray()
                while len(content) <= _MAX_BYTES:
                    chunk = os.read(descriptor, _MAX_BYTES + 1 - len(content))
                    if not chunk:
                        break
                    content.extend(chunk)
                if len(content) > _MAX_BYTES:
                    raise ValueError("credential file too large")
                token = content.decode("utf-8")
                self._validate_token(token)
                return token
            finally:
                os.close(descriptor)
        finally:
            os.close(directory)

    def _save(self, token: str) -> None:
        content = self._validate_token(token)
        directory = self._open_directory(create=True)
        temporary = ""
        try:
            self._target_stat(directory)
            candidate = f".liepin-token.{secrets.token_hex(16)}.tmp"
            descriptor = os.open(
                candidate, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory,
            )
            temporary = candidate
            try:
                os.fchmod(descriptor, 0o600)
                remaining = memoryview(content)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("credential write incomplete")
                    remaining = remaining[written:]
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            self._target_stat(directory)
            os.replace(temporary, self.path.name, src_dir_fd=directory, dst_dir_fd=directory)
            temporary = ""
        finally:
            if temporary:
                try:
                    os.unlink(temporary, dir_fd=directory)
                except OSError:
                    pass
            os.close(directory)
