"""Remember successful daily draws across processes and restarts."""

from contextlib import contextmanager
import fcntl
import os
import stat


class DrawMemoryError(Exception):
    pass


@contextmanager
def daily_draw(directory, day):
    """Hold the date lock through output and mark it only after a successful flush."""
    path = directory / f"drawn-{day.isoformat()}"
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as exc:
        raise DrawMemoryError(f"无法打开今日抽签记录（{exc.strerror}）。") from exc

    with os.fdopen(fd, "r+b", buffering=0) as marker:
        try:
            if not stat.S_ISREG(os.fstat(marker.fileno()).st_mode):
                raise DrawMemoryError("抽签记录必须是普通文件。")
            fcntl.flock(marker.fileno(), fcntl.LOCK_EX)
            flag = marker.read(2)
        except OSError as exc:
            raise DrawMemoryError(f"无法读取今日抽签记录（{exc.strerror}）。") from exc
        if flag not in (b"", b"1"):
            raise DrawMemoryError("今日抽签记录格式异常。")

        first_draw = not flag
        yield first_draw

        # An empty file left after interrupted output still counts as undrawn.
        if first_draw:
            try:
                if marker.write(b"1") != 1:
                    raise DrawMemoryError("无法保存今日抽签记录。")
                os.fsync(marker.fileno())
            except OSError as exc:
                raise DrawMemoryError(f"无法保存今日抽签记录（{exc.strerror}）。") from exc
