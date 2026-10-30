'''设置路由：RAG 参数读写与热更新（P2 参数收敛于 retrieval_config.yml，P4 全参数化）

- GET 返回 v1 平铺字段（旧前端兼容）+ P4 分组字段（hybrid/rerank/queryOptimize/chunking 全量）
- PUT 接受平铺与分组任意组合；写入 yaml 后同步内存 retrieval_conf，
  检索参数变更时线程安全重建 RAG 链单例（不重启即时生效），并记录 before/after 审计日志
'''
import asyncio
import os
from typing import Literal, Optional

import yaml
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.permissions import SETTINGS_RAG
from app.core.response import err, ok
from app.dependencies import get_current_user, require_permission
from app.models.users import User
from app.service.rag import registry
from app.service.rag.retrieval import bm25_retriever, fetch_chunk_documents
from app.utils.config_handler import retrieval_conf
from app.utils.logger_handler import logger
from app.utils.path_tool import get_config_path

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 容器部署下指向运行时可写副本（RUNTIME_CONFIG_DIR），本地开发回退到 app/config
CONFIG_PATH = get_config_path("retrieval_config.yml")


def conf_to_dict() -> dict:
    """retrieval_conf → 契约 RAG 参数结构（v1 平铺 + P4 分组全量）"""
    chunking = retrieval_conf.get("chunking", {})
    hybrid = retrieval_conf.get("hybrid", {})
    rerank = retrieval_conf.get("rerank", {})
    qo = retrieval_conf.get("query_optimize", {})
    return {
        # ---- v1 平铺字段（旧前端兼容） ----
        "chunkSize": chunking.get("chunk_size"),
        "topK": retrieval_conf.get("top_k"),
        "chunkOverlap": chunking.get("chunk_overlap"),
        "separators": chunking.get("separators"),
        # ---- P4 分组字段 ----
        "legacyK": retrieval_conf.get("legacy_k"),
        "hybrid": {
            "enabled": hybrid.get("enabled"),
            "denseTopn": hybrid.get("dense_topn"),
            "bm25Topn": hybrid.get("bm25_topn"),
            "rrfK": hybrid.get("rrf_k"),
            "topn": hybrid.get("topn"),
        },
        "rerank": {
            "enabled": rerank.get("enabled"),
            "remoteModel": rerank.get("remote_model"),
            "localModel": rerank.get("local_model"),
            "topK": rerank.get("top_k"),
        },
        "queryOptimize": {
            "mode": qo.get("mode"),
            "multiQueryCount": qo.get("multi_query_count"),
            "fuseThenRerank": qo.get("fuse_then_rerank"),
        },
        "chunking": {
            "chunkSize": chunking.get("chunk_size"),
            "chunkOverlap": chunking.get("chunk_overlap"),
            "minChunkSize": chunking.get("min_chunk_size"),
            "maxChunkSize": chunking.get("max_chunk_size"),
            "excelRowsPerChunk": chunking.get("excel_rows_per_chunk"),
            "separators": chunking.get("separators"),
        },
    }


class HybridReq(BaseModel):
    """混合检索参数（平铺同键冲突时以平铺 topK 优先）"""
    enabled: Optional[bool] = Field(default=None, description="混合检索开关")
    denseTopn: Optional[int] = Field(default=None, ge=1, le=100, description="稠密检索候选数")
    bm25Topn: Optional[int] = Field(default=None, ge=1, le=100, description="BM25 候选数")
    rrfK: Optional[int] = Field(default=None, ge=1, le=500, description="RRF 平滑常数")
    topn: Optional[int] = Field(default=None, ge=1, le=100, description="RRF 融合后候选数")


class RerankReq(BaseModel):
    """精排重排参数"""
    enabled: Optional[bool] = Field(default=None, description="精排开关")
    remoteModel: Optional[str] = Field(default=None, description="远端精排模型名")
    localModel: Optional[str] = Field(default=None, description="本地精排模型名（需 local-rerank 依赖组）")
    topK: Optional[int] = Field(default=None, ge=1, le=20, description="精排后保留条数")


class QueryOptimizeReq(BaseModel):
    """查询优化参数"""
    mode: Optional[Literal["off", "multi_query", "hyde"]] = Field(default=None, description="查询优化模式")
    multiQueryCount: Optional[int] = Field(default=None, ge=2, le=5, description="multi_query 变体查询数")
    fuseThenRerank: Optional[bool] = Field(default=None, description="融合后统一精排变体开关")


class ChunkingReq(BaseModel):
    """分块参数（上传向量化时按次读取，修改无需重建链路）"""
    chunkSize: Optional[int] = Field(default=None, ge=10, le=2000, description="切分块大小")
    chunkOverlap: Optional[int] = Field(default=None, ge=0, le=1000, description="切分块重叠")
    minChunkSize: Optional[int] = Field(default=None, ge=1, le=2000, description="智能合并最小块")
    maxChunkSize: Optional[int] = Field(default=None, ge=1, le=8000, description="智能合并最大块")
    excelRowsPerChunk: Optional[int] = Field(default=None, ge=1, le=500, description="Excel 每分块行数")
    separators: Optional[list[str]] = Field(default=None, description="分隔符列表")


class RagConfigReq(BaseModel):
    """RAG 参数保存请求（v1 平铺 + P4 分组，同键冲突时平铺字段优先）"""
    chunkSize: Optional[int] = Field(default=None, ge=10, le=2000, description="切分块大小")
    topK: Optional[int] = Field(default=None, ge=1, le=20, description="检索 Top-K（最终送入生成的文档数）")
    legacyK: Optional[int] = Field(default=None, ge=1, le=20, description="全关闭链路的稠密检索 k")
    hybrid: Optional[HybridReq] = None
    rerank: Optional[RerankReq] = None
    queryOptimize: Optional[QueryOptimizeReq] = None
    chunking: Optional[ChunkingReq] = None


def _flat_conf(conf: dict) -> dict:
    """配置扁平化（点分键），供变更 diff 与审计日志"""
    flat: dict = {}
    for key, value in conf.items():
        if isinstance(value, dict):
            for k2, v2 in value.items():
                flat[f"{key}.{k2}"] = v2
        else:
            flat[key] = value
    return flat


def _is_retrieval_key(key: str) -> bool:
    """是否为检索链路参数（变更需重建单例）；chunking 上传时按次读取无需重建"""
    return key in ("top_k", "legacy_k") or key.startswith(("hybrid.", "rerank.", "query_optimize."))


@router.get("/rag-config")
async def get_rag_config(current_user: User = Depends(get_current_user)):
    """获取 RAG 参数配置（全量）"""
    return ok(conf_to_dict())


@router.put("/rag-config")
async def update_rag_config(
    req: RagConfigReq,
    current_user: User = Depends(require_permission(SETTINGS_RAG)),
):
    """保存 RAG 参数：写盘 + 内存同步 + 检索参数变更时热更新重建链路（无需重启）"""
    has_any = any([
        req.chunkSize is not None, req.topK is not None, req.legacyK is not None,
        req.hybrid is not None, req.rerank is not None,
        req.queryOptimize is not None, req.chunking is not None,
    ])
    if not has_any:
        return err(1001, "没有需要保存的参数")

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = yaml.load(f, Loader=yaml.FullLoader) or {}
    before = _flat_conf(config)

    # ---- 应用分组修改（section 浅合并，None 字段跳过） ----
    def merge_section(section: str, values: dict):
        target = config.setdefault(section, {})
        for k, v in values.items():
            if v is not None:
                target[k] = v

    if req.hybrid is not None:
        merge_section("hybrid", {
            "enabled": req.hybrid.enabled,
            "dense_topn": req.hybrid.denseTopn,
            "bm25_topn": req.hybrid.bm25Topn,
            "rrf_k": req.hybrid.rrfK,
            "topn": req.hybrid.topn,
        })
    if req.rerank is not None:
        merge_section("rerank", {
            "enabled": req.rerank.enabled,
            "remote_model": req.rerank.remoteModel,
            "local_model": req.rerank.localModel,
            "top_k": req.rerank.topK,
        })
    if req.queryOptimize is not None:
        merge_section("query_optimize", {
            "mode": req.queryOptimize.mode,
            "multi_query_count": req.queryOptimize.multiQueryCount,
            "fuse_then_rerank": req.queryOptimize.fuseThenRerank,
        })
    if req.chunking is not None:
        merge_section("chunking", {
            "chunk_size": req.chunking.chunkSize,
            "chunk_overlap": req.chunking.chunkOverlap,
            "min_chunk_size": req.chunking.minChunkSize,
            "max_chunk_size": req.chunking.maxChunkSize,
            "excel_rows_per_chunk": req.chunking.excelRowsPerChunk,
            "separators": req.chunking.separators,
        })

    # ---- 应用平铺修改（同键冲突时平铺优先） ----
    if req.chunkSize is not None:
        config.setdefault("chunking", {})["chunk_size"] = req.chunkSize
    if req.legacyK is not None:
        config["legacy_k"] = req.legacyK
    if req.topK is not None:
        config["top_k"] = req.topK
        # rerank 开启时最终上下文条数由 rerank.top_k 决定，保持两处同步
        if config.get("rerank", {}).get("enabled"):
            config["rerank"]["top_k"] = req.topK

    after = _flat_conf(config)
    changed = {k: (before.get(k), after[k]) for k in after if before.get(k) != after[k]}

    # ---- 写盘 + 内存同步（临时文件 + 原子替换，避免写一半损坏 YAML） ----
    tmp_path = f"{CONFIG_PATH}.tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)
        os.replace(tmp_path, CONFIG_PATH)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    retrieval_conf.update(config)

    # ---- 审计日志（before/after diff + 用户） ----
    if changed:
        changes_text = "、".join(f"{k}: {v[0]}→{v[1]}" for k, v in changed.items())
        logger.info(f"[热更新]用户{current_user.id}更新 RAG 参数：{changes_text}")

    # ---- 检索参数变更 → 热更新重建链路 ----
    retrieval_changed = any(_is_retrieval_key(k) for k in changed)
    if not retrieval_changed:
        return ok(conf_to_dict(), "保存成功，已即时生效")

    # hybrid off→on 且索引为空（启动时未构建）→ 按 DB 全量构建 BM25 索引
    if bool(after.get("hybrid.enabled", False)) and bm25_retriever.size == 0:
        try:
            bm25_retriever.load_documents(await fetch_chunk_documents())
        except Exception as e:
            logger.warning(f"[热更新]BM25 索引全量构建失败，混合检索以空稀疏路降级：{e}", exc_info=True)
    # bm25_topn 为检索期参数，直接更新单例即可生效
    if "hybrid.bm25_topn" in changed:
        bm25_retriever.topn = int(after["hybrid.bm25_topn"])

    rebuilt = await asyncio.to_thread(registry.rebuild)
    if rebuilt:
        return ok(conf_to_dict(), "保存成功，检索链路已重建即时生效")
    return ok(conf_to_dict(), "配置已保存，但链路重建失败，将在下次重启后生效")
