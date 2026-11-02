# ============ 后端 FastAPI 服务 Dockerfile ============
# 基于 uv 包管理器构建

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# 启用 uv 字节码编译加速
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
# 强制使用阿里云 PyPI 镜像源（覆盖 uv.lock 中硬编码的索引地址）
ENV UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/

# 先拷贝依赖文件，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# 拷贝源码
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# ============ 运行阶段 ============
FROM python:3.13-slim-bookworm

WORKDIR /app

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 先创建非 root 用户
RUN groupadd --system app && useradd --system --gid app app

# 从 builder 复制虚拟环境（--chown 在复制时直接设定归属，避免冗余 chown）
COPY --from=builder --chown=app:app /app/.venv /app/.venv

# 复制源码
COPY --from=builder --chown=app:app /app /app

# 预创建持久化目录并授权：命名卷首次初始化时会把镜像内挂载点的属主复制进卷，
# 若不预创建，Docker 会以 root:root 创建挂载点，导致非 root 用户无写权限
#
# 需要可写目录清单（按写入方列出，新增落盘功能时记得同步这里）：
#   /app/chat_history          多轮对话历史 JSON，按会话一文件      → service/history/history_store.py（命名卷 chat_history）
#   /app/runtime_config        设置页热更新后的配置副本             → utils/path_tool.get_config_path（命名卷 rag_config）
#   /app/eval_reports          评测报告 json + md（REPORTS_DIR）    → service/eval/report.py（命名卷 eval_reports）
#   /app/app/logs              运行日志 + logs/traces 的 trace JSONL  → utils/logger_handler.py、service/observability/trace.py（命名卷 logs）
#   /home/app/.cache           本地精排模型缓存（HF 默认 ~/.cache/huggingface，system 用户无家目录）
#
# 注意：/app/app/data（知识库上传落盘）在 compose 中是**宿主机 bind mount**，
#       镜像内预创建对它无效，需在宿主机 chown 成容器用户（uid=999）；
#       详见 docs/常见报错问题解决方案速查.md 第 18 条。
RUN mkdir -p \
        /app/chat_history \
        /app/runtime_config \
        /app/eval_reports \
        /app/app/logs/traces \
        /home/app/.cache/huggingface \
    && chown -R app:app \
        /app/chat_history \
        /app/runtime_config \
        /app/eval_reports \
        /app/app/logs \
        /home/app

USER app

# 将虚拟环境加入 PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 18000

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "18000"]
