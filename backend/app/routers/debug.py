'''调试接口：按 trace_id 查询可回放 trace（默认关闭，受 ENABLE_TRACE_API 控制）'''
from fastapi import APIRouter

from app.core.response import err, ok
from app.service.observability import get_trace
from app.utils.config_handler import hybrid_conf

router = APIRouter(prefix="/api/debug", tags=["debug"])


@router.get("/trace/{trace_id}")
async def get_trace_detail(trace_id: str):
    '''返回完整 trace（含 route_reason / steps / fallback / 总耗时）'''
    if not bool(hybrid_conf.get("ENABLE_TRACE_API", False)):
        return err(4044, "调试 trace 接口未开启")
    data = get_trace(trace_id)
    if data is None:
        return err(4045, "trace 不存在或已过期")
    return ok(data)
