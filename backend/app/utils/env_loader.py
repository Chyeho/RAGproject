# -*- coding: utf-8 -*-
'''模型相关环境变量加载器

解决"本地直跑（uv run python / uvicorn）时 docker/env/.env.dev 中的模型配置
不会被任何代码加载"的缺口：Docker Compose 与 scripts/start-backend.ps1 各自
负责把 env 文件注入进程环境，但 `uv run` 直跑场景此前完全依赖手工 $env:。

设计要点：
- 白名单机制：只加载模型可自定义项（模型名 / API Key / base_url），
  天然规避 MYSQL_HOST=mysql、OLLAMA_BASE_URL=http://ollama:11434 等
  Docker 编排专用值污染本地进程（这些信息保留在原注入链路，不走本加载器）
- 仅注入缺失键：真实环境变量（Compose/启动脚本/手工 $env:）优先，
  本加载器只做兜底，不覆盖任何已有值
- 手写解析器：不引入 python-dotenv 依赖，保持 uv.lock 不动

默认读取 docker/env/.env.dev；可用环境变量 PRIVRAG_ENV_FILE 指定其他文件
（如生产环境 .env.prod）。
'''
import os
from pathlib import Path

from app.utils.logger_handler import logger

# 本项目根目录（backend/app/utils/env_loader.py → 上溯 3 级）
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# 默认 env 文件（本地直跑兜底用）
DEFAULT_ENV_FILE = _PROJECT_ROOT / "docker" / "env" / ".env.dev"

# 模型相关白名单：仅这些键允许从 env 文件注入进程环境。
# 聊天模型三件套可指向任意 OpenAI 协议供应商（DeepSeek/通义/月之暗面等）；
# 嵌入/精排/评测模型默认走 DashScope，可用对应变量覆盖模型名。
MODEL_ENV_WHITELIST = frozenset({
    "DASHSCOPE_API_KEY",      # DashScope API Key（嵌入/精排/评测模型共用）
    "DASHSCOPE_BASE_URL",     # DashScope OpenAI 协议兼容端点（评测聊天模型用）
    "OPENAI_CHAT_MODEL",      # 业务聊天模型名
    "OPENAI_API_KEY",         # 业务聊天模型 API Key
    "OPENAI_BASE_URL",        # 业务聊天模型端点
    "TEXT_EMBEDDING_MODEL",   # 嵌入模型名覆盖（默认取 rag_config.yml）
    "RERANK_MODEL",           # 精排模型名覆盖（默认取 retrieval_config.yml）
    "EVAL_CHAT_MODEL",        # 评测裁判/评测集生成模型名覆盖（默认 qwen-plus）
})


def _strip_paired_quotes(value: str) -> str:
    """去掉值首尾成对的单/双引号（.env 文件常见写法 KEY="value"）"""
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def parse_env_file(path: Path) -> dict[str, str]:
    """解析 env 文件为键值 dict；文件不存在返回空 dict（静默，不抛错）

    跳过空行、# 注释行与不含 = 的行；值去首尾空白与成对引号。
    """
    if not path.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            result[key] = _strip_paired_quotes(value.strip())
    return result


def load_model_env(env_file: str | Path | None = None) -> dict[str, str]:
    """按白名单把 env 文件中的模型配置注入 os.environ（仅注入缺失键）

    Args:
        env_file: env 文件路径；None 时先看 PRIVRAG_ENV_FILE 环境变量，
                  再回退默认的 docker/env/.env.dev

    Returns:
        实际注入的键值 dict（文件缺失/无白名单命中时为空 dict）
    """
    if env_file is None:
        env_file = os.environ.get("PRIVRAG_ENV_FILE", "") or DEFAULT_ENV_FILE
    parsed = parse_env_file(Path(env_file))
    injected: dict[str, str] = {}
    for key in MODEL_ENV_WHITELIST:
        if key in parsed and key not in os.environ:
            os.environ[key] = parsed[key]
            injected[key] = parsed[key]
    # 只记录键名不记录值，避免 API Key 泄漏到日志
    if injected:
        logger.info(f"[env加载器]已从 {env_file} 注入模型环境变量: {sorted(injected)}")
    return injected
