# ============ 后端 FastAPI 服务 Dockerfile ============
# 基于 uv 包管理器构建

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app

# 启用 uv 字节码编译加速
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# 先拷贝依赖文件，利用 Docker 层缓存
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 拷贝源码
COPY . .

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

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

USER app

# 将虚拟环境加入 PATH
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["fastapi", "run", "app/main.py", "--host", "0.0.0.0", "--port", "8000"]
