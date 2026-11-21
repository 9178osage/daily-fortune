"""Store a private, anonymous installation identifier without device inspection."""

import os
import re
import secrets
import stat
import sys
import tempfile
from pathlib import Path

from ._state import sync_directory

if os.name == "nt":
    from ._windows import open_state_file


class IdentityError(Exception):
    pass


def _absolute_path(value, setting):
    raw = os.fspath(value)
    if raw.startswith("~") and raw != "~" and not raw.startswith(("~/", "~\\")):
        raise IdentityError("无法解析%s：不支持指定其他用户的主目录。" % setting)
    try:
        path = Path(raw).expanduser()
    except (OSError, RuntimeError) as exc:
        raise IdentityError("无法解析%s：%s。" % (setting, exc)) from exc
    if not path.is_absolute():
        raise IdentityError("%s 必须是绝对路径。" % setting)
    return path


def _home_directory():
    try:
        home = Path.home()
    except (OSError, RuntimeError) as exc:
        raise IdentityError("无法确定用户主目录：%s。" % exc) from exc
    return _absolute_path(home, "用户主目录")


def state_directory():
    setting = os.environ.get("DAILY_FORTUNE_HOME")
    if setting:
        return _absolute_path(setting, "DAILY_FORTUNE_HOME")
    if os.name == "nt":
        setting = os.environ.get("LOCALAPPDATA")
        base = _absolute_path(setting, "LOCALAPPDATA") if setting else _home_directory() / "AppData" / "Local"
        return base / "daily-fortune" / "state"
    return _home_directory() / ".local/share/daily-fortune/state"


def load_identity(directory=None):
    """Publish a complete ID atomically; concurrent first runs share the winner."""
    directory = Path(directory) if directory is not None else state_directory()
    if not directory.is_absolute():
        raise IdentityError("状态目录必须是绝对路径。")
    target = directory / "user-id"
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        info = directory.lstat()
        if not stat.S_ISDIR(info.st_mode) or (
            sys.platform == "win32" and info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
        ):
            raise IdentityError("状态目录不能是符号链接，且必须是目录。")
        directory_changed = False
        if not target.exists() and not target.is_symlink():
            fd, temporary = tempfile.mkstemp(prefix=".identity-", dir=str(directory))
            directory_changed = True
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write((secrets.token_hex(16) + "\n").encode("ascii"))
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    # Windows rename fails if a concurrent first run already published its ID.
                    if sys.platform == "win32":
                        os.rename(temporary, target)
                    else:
                        os.link(temporary, target)
                except FileExistsError:
                    pass
            finally:
                Path(temporary).unlink(missing_ok=True)
        if directory_changed:
            sync_directory(directory)
        if os.name == "nt":
            fd = open_state_file(target)
        else:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            fd = os.open(target, flags)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IdentityError("匿名标识必须是普通文件。")
            if os.name != "nt" and stat.S_IMODE(os.fstat(stream.fileno()).st_mode) & 0o077:
                raise IdentityError("匿名标识权限过宽，请将其设置为仅当前用户可访问（0600）。")
            value = stream.read(100)
        if not re.fullmatch(rb"[0-9a-f]{32}\n?", value):
            raise IdentityError("匿名标识文件格式异常；请保留原文件并检查，程序不会自动重置它。")
        return value.decode("ascii").strip()
    except OSError as exc:
        raise IdentityError("无法读取或保存匿名标识（%s）。请检查状态目录权限：%s" %
                            (exc.strerror or exc, directory)) from exc
