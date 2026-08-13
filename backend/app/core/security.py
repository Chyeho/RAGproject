'''安全工具：密码哈希（bcrypt）+ JWT 签发/校验（pyjwt）'''
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# JWT 密钥：优先取环境变量，开发环境提供默认值
SECRET_KEY = os.environ.get("SECRET_KEY", "privrag-dev-secret-key-change-in-prod")
ALGORITHM = "HS256"
# remember=true 有效期 7 天，否则 24 小时
EXPIRE_DAYS_REMEMBER = 7
EXPIRE_DAYS_DEFAULT = 1


def hash_password(password: str) -> str:
    """bcrypt 密码哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码与哈希是否匹配"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, remember: bool = True) -> str:
    """签发 JWT 访问令牌"""
    days = EXPIRE_DAYS_REMEMBER if remember else EXPIRE_DAYS_DEFAULT
    expire = datetime.now(timezone.utc) + timedelta(days=days)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> int | None:
    """解析 JWT 令牌，返回用户 ID；无效或过期返回 None"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
