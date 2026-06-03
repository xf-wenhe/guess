#!/bin/bash
# 启动 embedding server，提供模型和词库服务
# 用法: ./scripts/start_embedding_server.sh [--detach]

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# 默认参数
HOST="127.0.0.1"
PORT=8000
DETACH=false

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --detach|-d)
            DETACH=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# 检查端口是否已被占用
if lsof -i ":$PORT" -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "[start_embedding_server] 端口 $PORT 已被占用，检查是否为 embedding server..."
    if curl -sS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
        echo "[start_embedding_server] Embedding server 已在运行"
        exit 0
    else
        echo "[start_embedding_server] 端口被其他进程占用，退出"
        exit 1
    fi
fi

# 检查虚拟环境
if [[ -z "$VIRTUAL_ENV" ]]; then
    if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
        source "$PROJECT_ROOT/.venv/bin/activate"
    fi
fi

# 设置环境变量
export PUZZLES_PATH="$PROJECT_ROOT/assets/puzzles.json"

echo "[start_embedding_server] 启动 embedding server on $HOST:$PORT"
echo "[start_embedding_server] PUZZLES_PATH=$PUZZLES_PATH"

if [[ "$DETACH" == "true" ]]; then
    # 后台运行
    nohup python embedding_server.py --host "$HOST" --port "$PORT" \
        > /tmp/embedding_server.log 2>&1 &
    echo "[start_embedding_server] Server PID: $!"

    # 等待 server 就绪
    for i in {1..30}; do
        if curl -sS "http://$HOST:$PORT/health" >/dev/null 2>&1; then
            echo "[start_embedding_server] Server 就绪"
            exit 0
        fi
        sleep 1
    done
    echo "[start_embedding_server] Server 启动超时"
    exit 1
else
    # 前台运行
    exec python embedding_server.py --host "$HOST" --port "$PORT"
fi
