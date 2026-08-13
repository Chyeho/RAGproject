'''统一响应包裹：{code, message, data}（与接口 JSON 契约文档 0.2 对齐）'''


def ok(data=None, message: str = "success") -> dict:
    """成功响应"""
    return {"code": 0, "message": message, "data": data}


def err(code: int, message: str) -> dict:
    """业务失败响应"""
    return {"code": code, "message": message, "data": None}
