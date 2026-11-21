#!/usr/bin/env python3
"""Build a reproducible source archive from a tagged Git release."""

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_version(source_root=ROOT, ref=None):
    if ref is None:
        contents = (source_root / "daily_fortune" / "__init__.py").read_text(encoding="utf-8")
    else:
        shown = subprocess.run(
            ["git", "-C", str(source_root), "show", f"{ref}:daily_fortune/__init__.py"],
            check=True,
            capture_output=True,
            text=True,
        )
        contents = shown.stdout
    match = re.search(r'^__version__ = "([^"]+)"$', contents, re.MULTILINE)
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
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag):
        raise ValueError("版本标签必须为 vX.Y.Z，例如 v1.6.1。")
    try:
        subprocess.run(
            ["git", "-C", str(source_root), "cat-file", "-e", f"{tag}^{{commit}}"],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as error:
        raise ValueError("未找到 Git 标签：{}".format(tag)) from error
    version = tag.removeprefix("v")
    if version != read_version(source_root, tag):
        raise ValueError("标签版本与 daily_fortune/__init__.py 不一致：{} != {}".format(
            version, read_version(source_root, tag)))

    dist = Path(dist_dir) if dist_dir is not None else source_root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    archive = dist / f"daily-fortune-{tag}.zip"
    prefix = f"daily-fortune-{tag}/"
    subprocess.run(
        ["git", "-C", str(source_root), "archive", "--format=zip",
         f"--prefix={prefix}", f"--output={archive}", tag],
        check=True,
        capture_output=True,
    )

    checksum = sha256_file(archive)
    checksum_file = dist / "SHA256SUMS.txt"
    checksum_file.write_text(f"{checksum}  {archive.name}\n", encoding="ascii")
    return archive, checksum_file


def main(argv=None):
    parser = argparse.ArgumentParser(description="构建标签版本的源码发布包")
    parser.add_argument("tag", help="例如 v1.6.0")
    parser.add_argument("--dist", help="输出目录（默认 dist）")
    args = parser.parse_args(argv)
    try:
        archive, checksum = build_release(args.tag, args.dist)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"构建发布包失败：{error}", file=sys.stderr)
        return 1
    print(f"发布包：{archive}")
    print(f"校验和：{checksum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
