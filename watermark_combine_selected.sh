#!/bin/zsh

# Finder「添加水印」：单张加水印，多张合成，张数限制由 Python 按输出模式校验。
# 保留整个项目目录，包括 scripts/、src/ 和 assets/。
PYTHON_BIN="${WATERMARK_PYTHON_BIN:-}"
SCRIPT_PATH="${(%):-%N}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_common.zsh" || exit 1
export WATERMARK_FINDER_PROGRESS="${WATERMARK_FINDER_PROGRESS:-1}"
initialize_finder "$@" || exit 1

if ! OUTPUT_PATH="$("$PYTHON_BIN" - "$@" <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd() / "src"))
from watermark_tool.cli import make_default_output_path

print(make_default_output_path(sys.argv[1:]))
PY
)" || [[ -z "$OUTPUT_PATH" ]]; then
  show_dialog '无法生成默认输出文件名。'
  exit 1
fi

create_error_log combine || exit 1
echo "输出文件：$OUTPUT_PATH" >> "$ERROR_LOG"
if "$PYTHON_BIN" "$PY_SCRIPT" "$@" -o "$OUTPUT_PATH" >> "$ERROR_LOG" 2>&1; then
  rm -f "$ERROR_LOG"
  if [[ $# -eq 1 ]]; then
    show_notification "添加水印完成" "已生成：$(basename "$OUTPUT_PATH")"
  else
    show_notification "合成水印照片完成" "已生成：$(basename "$OUTPUT_PATH")"
  fi
  open -R "$OUTPUT_PATH"
else
  open "$ERROR_LOG"
  show_dialog '添加水印失败，错误日志已经打开。'
  exit 1
fi

exit 0
