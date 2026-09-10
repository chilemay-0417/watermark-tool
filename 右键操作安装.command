#!/bin/zsh
# 双击安装 Finder 右键操作；保留整个项目文件夹。
SCRIPT_DIR="${0:A:h}"
cd "$SCRIPT_DIR" || exit 1
source "$SCRIPT_DIR/scripts/finder_setup.zsh" || exit 1
setup_finder install
result=$?
if [[ -t 0 ]]; then
  read -r '?按回车键关闭此窗口…'
fi
exit "$result"
