'''设置路由：RAG 参数读写（P2 起参数收敛于 retrieval_config.yml）'''
from typing import Optional

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.response import err, ok
from app.dependencies import get_current_user
from app.models.users import User
from app.utils.config_handler import retrieval_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path

router = APIRouter(prefix="/api/settings", tags=["settings"])

CONFIG_PATH = get_abs_path("config/retrieval_config.yml")


def conf_to_dict() -> dict:
    """retrieval_conf → 契约 RAG 参数结构"""
    chunking = retrieval_conf.get("chunking", {})
    return {
        "chunkSize": chunking.get("chunk_size"),
        "topK": retrieval_conf.get("top_k"),
        "chunkOverlap": chunking.get("chunk_overlap"),
        "separators": chunking.get("separators"),
    }


class RagConfigReq(BaseModel):
    chunkSize: Optional[int] = Field(default=None, ge=10, le=2000, description="切分块大小")
    topK: Optional[int] = Field(default=None, ge=1, le=20, description="检索 Top-K（最终送入生成的文档数）")


@router.get("/rag-config")
async def get_rag_config(current_user: User = Depends(get_current_user)):
    """获取 RAG 参数配置"""
    return ok(conf_to_dict())


@router.put("/rag-config")
async def update_rag_config(
    req: RagConfigReq,
    current_user: User = Depends(get_current_user),
):
    """保存 RAG 参数（写入 retrieval_config.yml，重启服务后生效；P4 将支持热更新）"""
    if req.chunkSize is None and req.topK is None:
        return err(1001, "没有需要保存的参数")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    if req.chunkSize is not None:
        config.setdefault("chunking", {})["chunk_size"] = req.chunkSize
    if req.topK is not None:
        config["top_k"] = req.topK
        # rerank 开启时最终上下文条数由 rerank.top_k 决定，保持两处同步
        if config.get("rerank", {}).get("enabled"):
            config["rerank"]["top_k"] = req.topK

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    # 同步内存中的配置
    retrieval_conf.update(config)

    logger.info(f"[设置]用户{current_user.id}更新 RAG 参数：chunk_size={config['chunking']['chunk_size']}, "
                f"top_k={config['top_k']}（重启后生效）")
    return ok(conf_to_dict(), "保存成功，重启后生效")
