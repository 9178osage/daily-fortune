#!/usr/bin/env python3
"""Build a reproducible source archive for a tagged release."""

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_version(source_root=ROOT):
    init_file = source_root / "daily_fortune" / "__init__.py"
    match = re.search(r'^__version__ = "([^"]+)"$', init_file.read_text(encoding="utf-8"),
                      re.MULTILINE)
    if not match:
        raise ValueError("无法读取 daily_fortune/__init__.py 中的版本号。")
    return match.group(1)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_release(tag, dist_dir=None, source_root=ROOT):
    if not tag.startswith("v"):
        raise ValueError("版本标签必须以 v 开头，例如 v1.6.0。")
    version = tag[1:]
    if version != read_version(source_root):
        raise ValueError("标签版本与 daily_fortune/__init__.py 不一致：{} != {}".format(
            version, read_version(source_root)))

    dist = Path(dist_dir) if dist_dir is not None else source_root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"daily-fortune-{version}.zip"
    prefix = f"daily-fortune-{version}/"
    listed = subprocess.run(
        ["git", "-C", str(source_root), "ls-files", "-z"],
        check=True,
        capture_output=True,
    )
    tracked = [Path(value.decode("utf-8")) for value in listed.stdout.split(b"\0") if value]

    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for relative in tracked:
            original = source_root / relative
            if not original.is_file() or original.is_symlink():
                raise ValueError("发布清单包含非常规文件或符号链接：{}".format(relative))
            package.write(original, prefix + relative.as_posix())

    checksum = sha256_file(archive)
    checksum_file = dist / "SHA256SUMS.txt"
    checksum_file.write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return archive, checksum_file


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建标签版本的源码发布包")
    parser.add_argument("tag", help="例如 v1.6.0")
    args = parser.parse_args(argv)
    try:
        archive, checksum = build_release(args.tag)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"构建发布包失败：{error}", file=sys.stderr)
        return 1
    print(f"发布包：{archive}")
    print(f"校验和：{checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
