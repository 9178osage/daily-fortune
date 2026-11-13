#!/bin/sh
set -eu
python_bin=${PYTHON:-python3}
if ! command -v "$python_bin" >/dev/null 2>&1; then
    printf '%s\n' '卸载失败：找不到 Python 3。请先提供 Python 3.9 或更新版本（可设置 PYTHON=/绝对路径/python3）。' >&2
    exit 1
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$python_bin" -I -B "$script_dir/scripts/manage_install.py" uninstall "$@"
