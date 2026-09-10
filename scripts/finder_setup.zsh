# 双击安装/卸载入口共用的引导；不依赖已安装的项目包。
watermark_python_candidates() {
  local user_home="${1:-$HOME}"
  local framework_versions="${2:-/Library/Frameworks/Python.framework/Versions}"
  local prefix conda_command
  local candidates=("python3")
  [[ -n "${CONDA_PREFIX:-}" ]] && candidates+=("$CONDA_PREFIX/bin/python3" "$CONDA_PREFIX/bin/python")
  [[ -n "${CONDA_PYTHON_EXE:-}" ]] && candidates+=("$CONDA_PYTHON_EXE")
  if [[ -n "${CONDA_EXE:-}" ]]; then
    prefix="${CONDA_EXE:A:h:h}"
    candidates+=("$prefix/bin/python3" "$prefix/bin/python")
  fi
  candidates+=("/opt/homebrew/bin/python3" "/usr/local/bin/python3")
  # python.org installations need not have their optional /usr/local symlinks.
  for prefix in "$framework_versions"/*(N/on); do
    candidates+=("$prefix/bin/python3")
  done
  conda_command="$(whence -p conda)"
  if [[ -n "$conda_command" ]]; then
    prefix="${conda_command:A:h:h}"
    candidates+=("$prefix/bin/python3" "$prefix/bin/python")
  fi
  for prefix in "$user_home/miniconda3" "$user_home/anaconda3" \
                "$user_home/miniforge3" "$user_home/mambaforge" \
                "$user_home/opt/miniconda3" "$user_home/opt/anaconda3" \
                "/opt/miniconda3" "/opt/anaconda3" "/opt/miniforge3" "/opt/mambaforge"; do
    candidates+=("$prefix/bin/python3" "$prefix/bin/python")
  done
  if [[ -r "$user_home/.conda/environments.txt" ]]; then
    while IFS= read -r prefix || [[ -n "$prefix" ]]; do
      prefix="${prefix%$'\r'}"
      [[ -n "$prefix" && "$prefix" != \#* ]] || continue
      candidates+=("$prefix/bin/python3" "$prefix/bin/python")
    done < "$user_home/.conda/environments.txt"
  fi
  print -rl -- "${candidates[@]}"
}

setup_finder() {
  local operation="$1"
  shift
  local candidate resolved setup_python="" missing_pip="" result
  local candidates=()
  if [[ -n "${WATERMARK_PYTHON_BIN:-}" ]]; then
    candidates=("$WATERMARK_PYTHON_BIN")
  else
    candidates=("${(@f)$(watermark_python_candidates)}")
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
    "$resolved" -c 'import importlib.util,sys
if sys.version_info < (3, 10):
    raise SystemExit(1)
if sys.argv[1] != "uninstall" and importlib.util.find_spec("pip") is None:
    raise SystemExit(2)
' "$operation" 2>/dev/null
    result=$?
    if (( result == 0 )); then
      setup_python="$resolved"
      break
    elif (( result == 2 )); then
      missing_pip="$resolved"
    fi
  done
  if [[ -z "$setup_python" ]]; then
    if [[ -n "$missing_pip" ]]; then
      print -u2 "找到 Python，但缺少 pip：$missing_pip"
      print -u2 '请为这个已有 Python 安装 pip 后重试；Conda 用户可在对应环境运行 conda install pip，无需新建环境。'
    else
      print -u2 '未找到 Python 3.10 或更新版本。已有 Conda 时可按 docs/usage.md 指定 Python；也可安装 Python 后重试。'
    fi
    return 1
  fi
  local arguments=("$@")
  [[ "$operation" == "uninstall" ]] && arguments+=(--uninstall)
  "$setup_python" "$SCRIPT_DIR/scripts/install_finder.py" "${arguments[@]}"
}
