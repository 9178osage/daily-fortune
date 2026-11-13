#!/bin/sh
# No sudo, pip, shell profile changes, or network access.
set -eu
python_bin=${PYTHON:-python3}
if ! command -v "$python_bin" >/dev/null 2>&1; then
    printf '%s\n' '安装失败：找不到 Python 3。请先安装 Python 3.9 或更新版本：https://www.python.org/downloads/macos/' >&2
    exit 1
fi
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$python_bin" -I -B "$script_dir/scripts/manage_install.py" install "$@"
