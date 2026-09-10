#!/bin/zsh

# Finder 快速操作：批量给每张照片分别加水印。
# 保留整个项目目录，包括 scripts/、src/ 和 assets/。
PYTHON_BIN="${WATERMARK_PYTHON_BIN:-}"
SCRIPT_PATH="${(%):-%N}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_common.zsh" || exit 1
export WATERMARK_FINDER_PROGRESS="${WATERMARK_FINDER_PROGRESS:-1}"
initialize_finder "$@" || exit 1
create_error_log batch || exit 1

if "$PYTHON_BIN" "$PY_SCRIPT" --batch -- "$@" >> "$ERROR_LOG" 2>&1; then
  rm -f "$ERROR_LOG"
  show_notification "批量加水印完成" "成功处理 $# 张照片"
else
  open "$ERROR_LOG"
  show_dialog "部分照片处理失败，其余照片已继续处理。成功和失败数量请查看已打开的错误日志。"
  exit 1
fi

exit 0
