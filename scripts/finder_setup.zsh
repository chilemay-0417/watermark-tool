# 双击安装/卸载入口共用的引导；不依赖已安装的项目包。
setup_finder() {
  local operation="$1"
  local candidate resolved setup_python=""
  local candidates=("/usr/local/bin/python3" "python3" "/opt/homebrew/bin/python3")
  if [[ -n "${WATERMARK_PYTHON_BIN:-}" ]]; then
    candidates=("$WATERMARK_PYTHON_BIN")
  fi
  if [[ "$(uname -s)" != "Darwin" ]]; then
    print -u2 '此安装器仅支持 macOS。'
    return 1
  fi
  for candidate in "${candidates[@]}"; do
    [[ -n "$candidate" ]] || continue
    resolved="$(command -v "$candidate")" || continue
    # Avoid triggering Apple's developer-tools installer through the system stub.
    [[ "$resolved" == "/usr/bin/python3" ]] && continue
    if "$resolved" -c 'import sys; raise SystemExit(sys.version_info < (3, 10))' 2>/dev/null; then
      setup_python="$resolved"
      break
    fi
  done
  if [[ -z "$setup_python" ]]; then
    print -u2 '未找到 Python 3.10 或更新版本。请先从 https://www.python.org/downloads/macos/ 安装 Python，然后重新双击此文件。'
    return 1
  fi
  local arguments=()
  [[ "$operation" == "uninstall" ]] && arguments+=(--uninstall)
  "$setup_python" "$SCRIPT_DIR/scripts/install_finder.py" "${arguments[@]}"
}
