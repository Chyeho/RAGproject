'''设置路由：RAG 参数读写（qdrant_config.yml）'''
from typing import Optional

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.response import err, ok
from app.dependencies import get_current_user
from app.models.users import User
from app.utils.config_handler import qdrant_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path

router = APIRouter(prefix="/api/settings", tags=["settings"])

CONFIG_PATH = get_abs_path("config/qdrant_config.yml")


def conf_to_dict() -> dict:
    """qdrant_conf → 契约 RAG 参数结构"""
    return {
        "chunkSize": qdrant_conf["chunk_size"],
        "topK": qdrant_conf["k"],
        "chunkOverlap": qdrant_conf["chunk_overlap"],
        "separators": qdrant_conf["separators"],
    }


class RagConfigReq(BaseModel):
    chunkSize: Optional[int] = Field(default=None, ge=10, le=2000, description="切分块大小")
    topK: Optional[int] = Field(default=None, ge=1, le=20, description="检索 Top-K")


@router.get("/rag-config")
async def get_rag_config(current_user: User = Depends(get_current_user)):
    """获取 RAG 参数配置"""
    return ok(conf_to_dict())


@router.put("/rag-config")
async def update_rag_config(
    req: RagConfigReq,
    current_user: User = Depends(get_current_user),
):
    """保存 RAG 参数（写入 qdrant_config.yml，重启服务后生效）"""
    if req.chunkSize is None and req.topK is None:
        return err(1001, "没有需要保存的参数")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    if req.chunkSize is not None:
        config["chunk_size"] = req.chunkSize
    if req.topK is not None:
        config["k"] = req.topK

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    # 同步内存中的配置
    qdrant_conf.update(config)

    logger.info(f"[设置]用户{current_user.id}更新 RAG 参数：chunk_size={config['chunk_size']}, k={config['k']}（重启后生效）")
    return ok(conf_to_dict(), "保存成功，重启后生效")
