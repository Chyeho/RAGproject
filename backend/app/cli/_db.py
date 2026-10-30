'''CLI 数据库连接工具（同步 PyMySQL，供迁移/重置密码脚本使用）

连接参数优先级：命令行参数 > 进程环境变量 > docker/env/.env.dev
在宿主机执行时自动把容器内主机名/端口换成宿主机映射值，容器内执行保持原值。
'''
import os
from pathlib import Path

import pymysql

from app.utils.env_loader import DEFAULT_ENV_FILE, parse_env_file

# 是否运行在容器内（/.dockerenv 存在即容器）
_IN_CONTAINER = os.path.exists("/.dockerenv")


def resolve_mysql_params(host: str | None = None, port: int | None = None) -> dict:
    """解析 MySQL 连接参数"""
    env_file = Path(os.environ.get("PRIVRAG_ENV_FILE", "") or DEFAULT_ENV_FILE)
    parsed = parse_env_file(env_file)

    db_host = host or os.environ.get("MYSQL_HOST") or parsed.get("MYSQL_HOST") or "127.0.0.1"
    db_port = port or int(os.environ.get("MYSQL_PORT") or parsed.get("MYSQL_PORT") or 3306)

    if not _IN_CONTAINER:
        # 宿主机执行：容器内主机名不可解析，端口需用映射到宿主机的端口
        if db_host == "mysql":
            db_host = "127.0.0.1"
        if db_port == 3306 and parsed.get("MYSQL_HOST_PORT"):
            db_port = int(parsed["MYSQL_HOST_PORT"])

    return {
        "host": db_host,
        "port": db_port,
        "user": os.environ.get("MYSQL_USER") or parsed.get("MYSQL_USER") or "privrag",
        "password": os.environ.get("MYSQL_PASSWORD") or parsed.get("MYSQL_PASSWORD") or "",
        "database": os.environ.get("MYSQL_DATABASE") or parsed.get("MYSQL_DATABASE") or "privrag_dev",
    }


def connect(host: str | None = None, port: int | None = None):
    """建立数据库连接（自动提交关闭，由脚本显式 commit）"""
    params = resolve_mysql_params(host, port)
    return pymysql.connect(charset="utf8mb4", autocommit=False, **params), params
