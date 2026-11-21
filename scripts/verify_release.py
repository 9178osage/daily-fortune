#!/usr/bin/env python3
"""Verify a downloaded release archive against SHA256SUMS.txt."""

import argparse
import hashlib
import re
import sys
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_expected(checksum_file, archive_name):
    for line in checksum_file.read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if match and match.group(2) == archive_name:
            return match.group(1).lower()
    raise ValueError("校验和文件中没有找到：{}".format(archive_name))


def verify_release(archive, checksum_file):
    archive = Path(archive)
    checksum_file = Path(checksum_file)
    expected = read_expected(checksum_file, archive.name)
    actual = sha256_file(archive)
    if actual != expected:
        raise ValueError("SHA-256 校验失败：{} != {}".format(actual, expected))
    return actual


def main(argv=None):
    parser = argparse.ArgumentParser(description="校验发布 ZIP 的 SHA-256")
    parser.add_argument("archive")
    parser.add_argument("--checksum", default="SHA256SUMS.txt")
    args = parser.parse_args(argv)
    try:
        digest = verify_release(args.archive, args.checksum)
    except (OSError, ValueError) as error:
        print(f"校验失败：{error}", file=sys.stderr)
        return 1
    print(f"校验成功：{digest}  {Path(args.archive).name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
