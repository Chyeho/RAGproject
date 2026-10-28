#!/usr/bin/env bash
# ============================================================================
# 一键启动后端服务（本地开发模式）
#
# 自动读取 docker/env/.env.dev 中的环境变量，并针对本地启动做必要的覆盖：
#   - MYSQL_HOST / QDRANT_HOST 从容器内主机名改为 127.0.0.1
#   - MYSQL_PORT 改用宿主机映射端口（MYSQL_HOST_PORT）
#   - OLLAMA_BASE_URL 改用 http://localhost:OLLAMA_PORT（本地模式）
#
# 用法:
#   ./scripts/start-backend.sh
#   ./scripts/start-backend.sh docker/env/.env.prod
# ============================================================================

set -e

# 定位项目根目录（脚本所在目录的父目录）
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"

# 确定环境变量文件（默认 .env.dev，可通过第一个参数指定）
ENV_FILE="${1:-$PROJECT_ROOT/docker/env/.env.dev}"

if [ ! -f "$ENV_FILE" ]; then
    echo -e "\033[31m[错误] 环境变量文件不存在: $ENV_FILE\033[0m"
    echo -e "\033[33m请先复制模板: cp docker/env/.env.dev.example docker/env/.env.dev\033[0m"
    exit 1
fi

echo -e "\033[36m[信息] 读取环境变量文件: $ENV_FILE\033[0m"

# 读取并解析 env 文件（跳过空行、注释行、去除引号）
while IFS= read -r line || [ -n "$line" ]; do
    # 去除首尾空白
    line="$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    # 跳过空行和注释
    [ -z "$line" ] && continue
    [[ "$line" =~ ^# ]] && continue

    # 解析 KEY=VALUE
    key="${line%%=*}"
    value="${line#*=}"
    # 去除首尾双引号
    value="$(echo "$value" | sed 's/^"//;s/"$//')"
    export "$key=$value"
done < "$ENV_FILE"

# ---------- 本地启动覆盖 ----------
# 容器内用服务名（mysql/qdrant/ollama）互访，本地直连需改为宿主机地址
export MYSQL_HOST="127.0.0.1"
export QDRANT_HOST="127.0.0.1"

# MySQL 容器内监听 3306，但映射到宿主机的端口是 MYSQL_HOST_PORT
if [ -n "$MYSQL_HOST_PORT" ]; then
    export MYSQL_PORT="$MYSQL_HOST_PORT"
fi

# Qdrant 容器内监听 6333，映射到宿主机的端口是 QDRANT_HOST_PORT
if [ -n "$QDRANT_HOST_PORT" ]; then
    export QDRANT_PORT="$QDRANT_HOST_PORT"
fi

# Ollama 容器内监听 11434，映射到宿主机的端口是 OLLAMA_PORT
if [ -n "$OLLAMA_PORT" ]; then
    export OLLAMA_BASE_URL="http://localhost:$OLLAMA_PORT"
fi

echo -e "\033[36m[信息] MySQL  连接: $MYSQL_HOST:$MYSQL_PORT\033[0m"
echo -e "\033[36m[信息] Qdrant 连接: $QDRANT_HOST:$QDRANT_PORT\033[0m"
echo -e "\033[36m[信息] 模型模式: $MODEL_MODE\033[0m"
if [ "$MODEL_MODE" = "local" ]; then
    echo -e "\033[36m[信息] Ollama 地址: $OLLAMA_BASE_URL\033[0m"
fi

# 进入 backend 目录并启动
cd "$BACKEND_DIR"
echo -e "\033[32m[启动] uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 18000\033[0m"
echo "============================================================"

uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 18000
