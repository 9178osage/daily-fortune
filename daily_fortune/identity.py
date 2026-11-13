"""Store a private, anonymous installation identifier without device inspection."""

import os
from pathlib import Path
import re
import secrets
import stat
import tempfile


class IdentityError(Exception):
    pass


def state_directory():
    setting = os.environ.get("DAILY_FORTUNE_HOME")
    path = Path(setting).expanduser() if setting else Path.home() / ".local/share/daily-fortune/state"
    if not path.is_absolute():
        raise IdentityError("DAILY_FORTUNE_HOME 必须是绝对路径。")
    return path


def load_identity(directory=None):
    """Publish a complete ID atomically; concurrent first runs share the winner."""
    directory = Path(directory) if directory is not None else state_directory()
    target = directory / "user-id"
    try:
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink() or not directory.is_dir():
            raise IdentityError("状态目录不能是符号链接，且必须是目录。")
        if not target.exists() and not target.is_symlink():
            fd, temporary = tempfile.mkstemp(prefix=".identity-", dir=str(directory))
            try:
                with os.fdopen(fd, "wb") as stream:
                    stream.write((secrets.token_hex(16) + "\n").encode("ascii"))
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    os.link(temporary, target)
                except FileExistsError:
                    pass
            finally:
                os.unlink(temporary)
        fd = os.open(str(target), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise IdentityError("匿名标识必须是普通文件。")
            value = stream.read(100)
        if not re.fullmatch(rb"[0-9a-f]{32}\n?", value):
            raise IdentityError("匿名标识文件格式异常；请保留原文件并检查，程序不会自动重置它。")
        return value.decode("ascii").strip()
    except OSError as exc:
        raise IdentityError("无法读取或保存匿名标识（%s）。请检查状态目录权限：%s" % (exc.strerror, directory)) from exc
