#!/bin/zsh
# 仅卸载由安装器管理的操作；保留项目和照片。
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_setup.zsh" || exit 1
setup_finder uninstall
result=$?
if [[ -t 0 ]]; then
  read -r '?按回车键关闭此窗口…'
fi
exit "$result"
