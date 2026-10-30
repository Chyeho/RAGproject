'''安全工具：密码哈希（bcrypt）+ 密码策略/随机密码 + JWT 签发/校验（pyjwt）'''
import os
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

# JWT 密钥：优先取环境变量，开发环境提供默认值
SECRET_KEY = os.environ.get("SECRET_KEY", "privrag-dev-secret-key-change-in-prod")
ALGORITHM = "HS256"
# remember=true 有效期 7 天，否则 24 小时（可用环境变量覆盖）
EXPIRE_DAYS_REMEMBER = int(os.environ.get("JWT_EXPIRE_DAYS_REMEMBER", "7"))
EXPIRE_DAYS_DEFAULT = int(os.environ.get("JWT_EXPIRE_DAYS_DEFAULT", "1"))

# 随机密码字符集：排除易混淆字符 0/O/1/l/I
_UPPER = "ABCDEFGHJKMNPQRSTUVWXYZ"
_LOWER = "abcdefghjkmnpqrstuvwxyz"
_DIGITS = "23456789"
_ALL_CHARS = _UPPER + _LOWER + _DIGITS


def hash_password(password: str) -> str:
    """bcrypt 密码哈希"""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """校验密码与哈希是否匹配"""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def generate_password(length: int = 16) -> str:
    """生成随机初始/临时密码（保证包含大写、小写、数字）"""
    rng = secrets.SystemRandom()
    chars = [rng.choice(_UPPER), rng.choice(_LOWER), rng.choice(_DIGITS)]
    chars += [rng.choice(_ALL_CHARS) for _ in range(max(0, length - len(chars)))]
    rng.shuffle(chars)
    return "".join(chars)


def validate_password_strength(password: str) -> str | None:
    """校验用户自设密码强度；通过返回 None，否则返回错误提示"""
    if len(password) < 8 or len(password) > 64:
        return "密码长度需为 8-64 位"
    if not any(c.islower() for c in password):
        return "密码需包含小写字母"
    if not any(c.isupper() for c in password):
        return "密码需包含大写字母"
    if not any(c.isdigit() for c in password):
        return "密码需包含数字"
    return None


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
