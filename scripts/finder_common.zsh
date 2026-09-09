# Finder 两个入口共用的 Python 检查、提示和日志函数。
# 调用者先设置 SCRIPT_DIR 并切换到项目目录。

show_dialog() {
  osascript - "$1" <<'APPLESCRIPT'
on run argv
  display dialog (item 1 of argv) buttons {"好"} default button "好"
end run
APPLESCRIPT
}

show_notification() {
  osascript - "$1" "$2" <<'APPLESCRIPT'
on run argv
  display notification (item 2 of argv) with title (item 1 of argv)
end run
APPLESCRIPT
}

find_python_bin() {
  local candidates=()
  [[ -n "$PYTHON_BIN" ]] && candidates+=("$PYTHON_BIN")
  candidates+=("$SCRIPT_DIR/.venv/bin/python" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "python3" "/usr/bin/python3")
  local candidate resolved
  for candidate in "${candidates[@]}"; do
    resolved="$(command -v "$candidate")" || continue
    if "$resolved" - "$@" <<'PY' >/dev/null 2>&1
from pathlib import Path
import sys

sys.path.insert(0, str(Path.cwd() / "src"))
from watermark_tool.drawing import HEIC_SUFFIXES
import pyspng

suffixes = {Path(path).suffix.lower() for path in sys.argv[1:]}
if suffixes & HEIC_SUFFIXES:
    import pillow_heif
PY
    then
      PYTHON_BIN="$resolved"
      return 0
    fi
  done
  return 1
}

initialize_finder() {
  PY_SCRIPT="$SCRIPT_DIR/layout.py"
  if [[ $# -eq 0 ]]; then
    show_dialog $'没有收到照片文件。\n\n请在 Finder 中选中照片后运行快速操作。'
    return 1
  fi
  if [[ ! -f "$PY_SCRIPT" ]]; then
    show_dialog $'找不到 layout.py。\n\n请将入口脚本、scripts/、src/ 和 assets/ 保存在项目文件夹内。'
    return 1
  fi
  if ! find_python_bin "$@"; then
    show_dialog $'找不到能处理所选照片的 Python。\n\n请运行 python3 -m pip install -r requirements.txt，或通过 WATERMARK_PYTHON_BIN 指定 Python。'
    return 1
  fi
}

create_error_log() {
  if ! ERROR_LOG="$(mktemp "${TMPDIR:-/tmp}/watermark_${1}_error.XXXXXX")"; then
    show_dialog '无法创建错误日志，请检查临时目录权限。'
    return 1
  fi
  {
    echo "照片加水印日志"
    echo "时间：$(date)"
    echo "Python：$PYTHON_BIN"
    echo "工作目录：$SCRIPT_DIR"
  } > "$ERROR_LOG"
}
