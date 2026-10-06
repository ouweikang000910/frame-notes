#!/bin/bash
cd "$(dirname "$0")"
bash scripts/start.sh
TASK_EXIT=$?
if [ "$TASK_EXIT" -ne 0 ]; then
  echo '启动未完成，请查看上方提示。按回车关闭。'
  read -r
fi

