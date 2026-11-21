"""Durability helpers for local state files."""

import os


def sync_directory(directory):
    if os.name == "nt":
        from ._windows import sync_directory as windows_sync_directory

        windows_sync_directory(directory)
        return

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(directory), flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
