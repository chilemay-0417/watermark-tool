#!/bin/zsh

# Finder 右键快速操作：将选中的 1-3 张照片合成为一张水印拼版图
# 要求：本脚本、layout.py、src/、assets/ 放在同一个项目文件夹。

PYTHON_BIN="${WATERMARK_PYTHON_BIN:-}"

SCRIPT_PATH="${(%):-%N}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PY_SCRIPT="$SCRIPT_DIR/layout.py"

find_python_bin() {
  local candidates=()

  if [[ -n "$PYTHON_BIN" ]]; then
    candidates+=("$PYTHON_BIN")
  fi

  candidates+=(
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "python3"
    "/usr/bin/python3"
  )

  local candidate
  local resolved

  for candidate in "${candidates[@]}"; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi

    resolved="$(command -v "$candidate")"

    if "$resolved" - "$@" <<'PY' >/dev/null 2>&1
from pathlib import Path
import sys

import PIL

suffixes = {Path(path).suffix.lower() for path in sys.argv[1:]}

if suffixes & {".heic", ".heif", ".hif"}:
    import pillow_heif

if suffixes & {
    ".3fr", ".arw", ".cr2", ".cr3", ".crw", ".dng", ".erf", ".fff", ".iiq",
    ".kdc", ".mef", ".mos", ".mrw", ".nef", ".nrw", ".orf", ".pef", ".raf",
    ".raw", ".rw2", ".rwl", ".sr2", ".srf", ".srw", ".x3f",
}:
    import rawpy
PY
    then
      PYTHON_BIN="$resolved"
      return 0
    fi
  done

  return 1
}

if ! find_python_bin "$@"; then
  osascript -e 'display dialog "找不到能处理所选照片的 Python。\n\nJPEG/PNG 需要 Pillow；HEIC/HEIF 需要 pillow-heif；RAW 需要 rawpy。\n\n请先运行：python3 -m pip install -r requirements.txt\n\n或设置 WATERMARK_PYTHON_BIN 指向正确的 Python。" buttons {"好"} default button "好"'
  exit 1
fi

if [[ ! -f "$PY_SCRIPT" ]]; then
  osascript -e 'display dialog "找不到 layout.py\n\n请把 watermark_combine_selected.sh 和 layout.py 放在同一个项目文件夹。" buttons {"好"} default button "好"'
  exit 1
fi

COUNT=$#

if [[ $COUNT -lt 1 || $COUNT -gt 3 ]]; then
  osascript -e "display dialog \"合成水印照片需要选择 1 到 3 张照片。\n\n你当前选择了 $COUNT 张。\" buttons {\"好\"} default button \"好\""
  exit 1
fi

OUTPUT_PATH="$("$PYTHON_BIN" - "$@" <<'PY'
from pathlib import Path
import sys

project_root = Path.cwd()
src_dir = project_root / "src"

if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from watermark_tool.cli import make_default_output_path

print(make_default_output_path(sys.argv[1:]))
PY
)"

if [[ -z "$OUTPUT_PATH" ]]; then
  osascript -e 'display dialog "无法生成默认输出文件名。" buttons {"好"} default button "好"'
  exit 1
fi

TMP_BASE="${TMPDIR:-/tmp}"
ERROR_LOG="$(mktemp "${TMP_BASE%/}/watermark_combine_error.XXXXXX")"

if [[ -z "$ERROR_LOG" || ! -f "$ERROR_LOG" ]]; then
  osascript -e 'display dialog "无法创建错误日志。\n\n请检查临时目录权限后再试。" buttons {"好"} default button "好"'
  exit 1
fi

echo "合成水印照片日志" > "$ERROR_LOG"
echo "时间：$(date)" >> "$ERROR_LOG"
echo "Python：$PYTHON_BIN" >> "$ERROR_LOG"
echo "脚本：$PY_SCRIPT" >> "$ERROR_LOG"
echo "工作目录：$SCRIPT_DIR" >> "$ERROR_LOG"
echo "输出文件：$OUTPUT_PATH" >> "$ERROR_LOG"
echo "------------------------" >> "$ERROR_LOG"

"$PYTHON_BIN" "$PY_SCRIPT" "$@" -o "$OUTPUT_PATH" >> "$ERROR_LOG" 2>&1

if [[ $? -eq 0 ]]; then
  rm -f "$ERROR_LOG"
  osascript -e "display notification \"已生成：$(basename "$OUTPUT_PATH")\" with title \"合成水印照片完成\""
  open -R "$OUTPUT_PATH"
else
  open "$ERROR_LOG"
  osascript -e "display dialog \"合成失败。\n\n错误日志已经打开。\" buttons {\"好\"} default button \"好\""
fi

exit 0
