#!/bin/zsh

# Finder 右键快速操作：批量给每张照片分别加水印
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
  osascript -e 'display dialog "找不到 layout.py\n\n请把 watermark_batch_each.sh 和 layout.py 放在同一个项目文件夹。" buttons {"好"} default button "好"'
  exit 1
fi

if [[ $# -eq 0 ]]; then
  osascript -e 'display dialog "没有收到照片文件。\n\n请先在 Finder 里选中一张或多张照片，再运行快速操作。" buttons {"好"} default button "好"'
  exit 1
fi

FAILED=0
SUCCESS=0
TMP_BASE="${TMPDIR:-/tmp}"
ERROR_LOG="$(mktemp "${TMP_BASE%/}/watermark_batch_error.XXXXXX")"

if [[ -z "$ERROR_LOG" || ! -f "$ERROR_LOG" ]]; then
  osascript -e 'display dialog "无法创建错误日志。\n\n请检查临时目录权限后再试。" buttons {"好"} default button "好"'
  exit 1
fi

echo "批量加水印日志" > "$ERROR_LOG"
echo "时间：$(date)" >> "$ERROR_LOG"
echo "Python：$PYTHON_BIN" >> "$ERROR_LOG"
echo "脚本：$PY_SCRIPT" >> "$ERROR_LOG"
echo "工作目录：$SCRIPT_DIR" >> "$ERROR_LOG"
echo "------------------------" >> "$ERROR_LOG"

for PHOTO in "$@"; do
  echo "处理文件：$PHOTO" >> "$ERROR_LOG"

  "$PYTHON_BIN" "$PY_SCRIPT" "$PHOTO" >> "$ERROR_LOG" 2>&1

  if [[ $? -ne 0 ]]; then
    FAILED=$((FAILED + 1))
    echo "结果：失败" >> "$ERROR_LOG"
  else
    SUCCESS=$((SUCCESS + 1))
    echo "结果：成功" >> "$ERROR_LOG"
  fi

  echo "------------------------" >> "$ERROR_LOG"
done

if [[ $FAILED -eq 0 ]]; then
  rm -f "$ERROR_LOG"
  osascript -e "display notification \"成功处理 $SUCCESS 张照片\" with title \"批量加水印完成\""
else
  open "$ERROR_LOG"
  osascript -e "display dialog \"部分照片处理失败：$FAILED 张。\n成功：$SUCCESS 张。\n\n错误日志已经打开。\" buttons {\"好\"} default button \"好\""
fi

exit 0
