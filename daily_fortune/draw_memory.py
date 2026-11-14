"""Remember successful daily draws across processes and restarts."""

from contextlib import contextmanager
import os
import stat

if os.name == "nt":
    import errno
    import msvcrt
    import time

    from ._windows import open_state_file
else:
    import fcntl


class DrawMemoryError(Exception):
    pass


@contextmanager
def _lock_marker(marker):
    fd = marker.fileno()
    try:
        if os.name == "nt":
            # Windows locks a range from the current position, even for an empty file.
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno != errno.EACCES:
                        raise
                    time.sleep(0.05)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)
    except OSError as exc:
        raise DrawMemoryError(f"无法锁定今日抽签记录（{exc.strerror}）。") from exc
    try:
        yield
    finally:
        if os.name == "nt":
            try:
                marker.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError as exc:
                raise DrawMemoryError(f"无法解锁今日抽签记录（{exc.strerror}）。") from exc


@contextmanager
def daily_draw(directory, day):
    """Hold the date lock through output and mark it only after a successful flush."""
    path = directory / f"drawn-{day.isoformat()}"
    try:
        if os.name == "nt":
            fd = open_state_file(path, writable=True)
        else:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError as exc:
        raise DrawMemoryError(f"无法打开今日抽签记录（{exc.strerror or exc}）。") from exc

    with os.fdopen(fd, "r+b", buffering=0) as marker:
        if not stat.S_ISREG(os.fstat(marker.fileno()).st_mode):
            raise DrawMemoryError("抽签记录必须是普通文件。")
        with _lock_marker(marker):
            try:
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
