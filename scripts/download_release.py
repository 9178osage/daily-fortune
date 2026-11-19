#!/usr/bin/env python3
"""Download a release archive with Range resume support and SHA-256 verification."""

import argparse
import hashlib
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_release(url, output, sha256=None, timeout=30):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_name(output.name + ".part")
    start = part.stat().st_size if part.exists() else 0
    headers = {"Accept-Encoding": "identity"}
    if start:
        headers["Range"] = f"bytes={start}-"

    request = urllib.request.Request(url, headers=headers)
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        if start and error.code == 416:
            os.replace(part, output)
        else:
            raise
    else:
        status = getattr(response, "status", 200)
        mode = "ab" if start and status == 206 else "wb"
        if status not in (200, 206):
            raise OSError(f"服务器不支持下载（HTTP {status}）。")
        with response, part.open(mode) as stream:
            chunk_size = 1024 * 1024
            while chunk := response.read(chunk_size):
                stream.write(chunk)
                stream.flush()
        os.replace(part, output)

    if sha256:
        sha256 = sha256.lower()
        actual = sha256_file(output)
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise ValueError("SHA-256 校验值格式异常。")
        if actual != sha256:
            raise ValueError(f"SHA-256 校验失败：{actual} != {sha256}")
    return output


def checksum_from_url(checksum_url, archive_name):
    request = urllib.request.Request(checksum_url, headers={"Accept-Encoding": "identity"})
    with urllib.request.urlopen(request, timeout=30) as response:
        lines = response.read().decode("ascii").splitlines()
    for line in lines:
        match = re.fullmatch(r"([0-9a-fA-F]{64})  (.+)", line)
        if match and match.group(2) == archive_name:
            return match.group(1).lower()
    raise ValueError(f"校验和文件中没有找到：{archive_name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="断点续传下载今日运势发布包")
    parser.add_argument("url")
    parser.add_argument("output")
    parser.add_argument("--sha256")
    parser.add_argument("--checksum-url")
    args = parser.parse_args(argv)
    output = Path(args.output)
    try:
        sha256 = args.sha256
        if args.checksum_url:
            sha256 = checksum_from_url(args.checksum_url, output.name)
        if not sha256:
            raise ValueError("请提供 --sha256 或 --checksum-url。")
        downloaded = download_release(args.url, output, sha256)
    except (OSError, ValueError, urllib.error.URLError) as error:
        print(f"下载失败：{error}", file=sys.stderr)
        return 1
    print(f"下载成功：{downloaded}")
    print(f"校验和：{sha256_file(downloaded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
