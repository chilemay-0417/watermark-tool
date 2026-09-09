#!/bin/zsh

# Finder 快速操作：批量给每张照片分别加水印。
# 保留整个项目目录，包括 scripts/、src/ 和 assets/。
PYTHON_BIN="${WATERMARK_PYTHON_BIN:-}"
SCRIPT_PATH="${(%):-%N}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_common.zsh" || exit 1
initialize_finder "$@" || exit 1
create_error_log batch || exit 1

FAILED=0
SUCCESS=0
for PHOTO in "$@"; do
  echo "处理文件：$PHOTO" >> "$ERROR_LOG"
  if "$PYTHON_BIN" "$PY_SCRIPT" "$PHOTO" >> "$ERROR_LOG" 2>&1; then
    SUCCESS=$((SUCCESS + 1))
  else
    FAILED=$((FAILED + 1))
  fi
done

if [[ $FAILED -eq 0 ]]; then
  rm -f "$ERROR_LOG"
  show_notification "批量加水印完成" "成功处理 $SUCCESS 张照片"
else
  open "$ERROR_LOG"
  show_dialog "部分照片处理失败：$FAILED 张。成功：$SUCCESS 张。错误日志已经打开。"
  exit 1
fi

exit 0
