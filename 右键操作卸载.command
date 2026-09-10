#!/bin/zsh
# 卸载本工具的右键操作和终端命令；保留项目、个人素材、依赖和照片。
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_setup.zsh" || exit 1
setup_finder uninstall
result=$?
if [[ -t 0 ]]; then
  read -r '?按回车键关闭此窗口…'
fi
exit "$result"
