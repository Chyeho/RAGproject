'''向量存储服务（Qdrant 版，P1：格式感知分块 + 确定性 chunk ID）'''
import os
import uuid
from typing import Optional

from langchain_qdrant import QdrantVectorStore                                     # Qdrant向量库
from langchain_core.documents import Document
from qdrant_client import QdrantClient                                            # Qdrant客户端
from qdrant_client.models import Distance, VectorParams                           # Qdrant建集参数

from app.utils.config_handler import qdrant_conf, retrieval_conf             # Qdrant/检索配置项
from app.utils.logger_handler import logger                                      # 日志器
from app.modelFactory.factory import embed_model                                 # 文本嵌入模型
from app.service.rag.chunking import chunk_file                                  # 格式感知分块（P1）

# chunk ID 确定性命名空间：同一 document_id + chunk_index 生成的 ID 稳定，
# 重建向量时按 ID 覆盖（upsert），保证幂等
CHUNK_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "privrag.chunk.v1")


def build_chunk_id(document_id: int, chunk_index: int) -> str:
    '''生成确定性 chunk ID：uuid5(namespace, "{document_id}:{chunk_index}")'''
    return str(uuid.uuid5(CHUNK_ID_NAMESPACE, f"{document_id}:{chunk_index}"))


class VectorStoreService(object):
    def __init__(self):
        # 连接地址：优先取环境变量（docker 内 QDRANT_HOST=qdrant），否则用 qdrant_config.yml 配置
        host = os.environ.get("QDRANT_HOST", qdrant_conf["host"])
        port = int(os.environ.get("QDRANT_PORT", qdrant_conf["port"]))

        # qdrant客户端（关闭与服务端小版本差兼容性告警）
        self.client = QdrantClient(host=host, port=port, check_compatibility=False)

        # collection 不存在时自动创建（向量维度按嵌入模型探测，距离度量 Cosine）
        if not self.client.collection_exists(qdrant_conf["collection_name"]):
            dim = len(embed_model.embed_query("初始化"))
            self.client.create_collection(
                collection_name=qdrant_conf["collection_name"],
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"[向量库]collection {qdrant_conf['collection_name']} 创建成功（维度{dim}）")

        # qdrant向量存储
        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=qdrant_conf["collection_name"],                       # 要操作的集合名
            embedding=embed_model,                                                # 文本嵌入模型
            validate_collection_config=False,                                     # 不预校验，collection 不存在时自动创建
        )

    def get_retriever(self, k: int | None = None):
        """返回稠密检索器（P2 起默认 k 取 retrieval_config.yml 的 legacy_k，全开关关闭时等价旧链路）"""
        if k is None:
            k = int(retrieval_conf.get("legacy_k", 3))
        return self.vector_store.as_retriever(search_kwargs={"k": k})

    def upload_file(self, file_path: str, document_id: Optional[int] = None) -> list[tuple[str, str]]:
        """
        单个文件经格式感知分块后写入 Qdrant 向量库。
        Args:
            file_path (str): 待向量化的文件路径
            document_id (int, optional): 关联的 document 表 ID，写入分块 metadata，
                供问答引用来源反查文档信息；提供时启用确定性 chunk ID（支持幂等重建）

        Returns:
            list[tuple[str, str]]: [(chunk_text, vector_id)]，供写入 document_chunk 表
        """
        try:
            # 格式感知解析与智能分块（章节路径/页码/行号等结构信息写入 metadata）
            documents: list[Document] = chunk_file(file_path)

            # 如果分块后无有效内容
            if not documents:
                raise ValueError(f"[上传向量化]{file_path}内没有有效文本内容")

            # 合并元数据：保留 chunker 产出的结构信息，附加索引信息（不覆盖原有键）
            total = len(documents)
            for i, doc in enumerate(documents):
                doc.metadata = {
                    **doc.metadata,
                    "chunk_index": i,
                    "total_chunks": total,
                }
                if document_id is not None:
                    doc.metadata["document_id"] = document_id

            # 确定性 chunk ID：同时作为 Qdrant point id 与 metadata.vector_id
            ids: Optional[list[str]] = None
            if document_id is not None:
                ids = [build_chunk_id(document_id, i) for i in range(total)]
                for doc, chunk_id in zip(documents, ids):
                    doc.metadata["vector_id"] = chunk_id

            # 将内容存入 Qdrant（带 ids 时按 point id 覆盖写入），返回各分块的 point id
            vector_ids: list[str] = self.vector_store.add_documents(documents, ids=ids)

            logger.info(f"[上传向量化]{file_path}向量化成功，共 {len(vector_ids)} 个分块")
            return list(zip([doc.page_content for doc in documents], vector_ids))
        except Exception as e:
            logger.error(f"[上传向量化]{file_path}向量化失败，报错信息:{str(e)}", exc_info=True)
            raise

    def delete_by_vector_ids(self, vector_ids: list[str]):
        """按 vector_id 批量删除 Qdrant 向量"""
        if not vector_ids:
            return
        try:
            self.vector_store.delete(ids=vector_ids)
            logger.info(f"[删除向量]已删除 {len(vector_ids)} 个向量分块")
        except Exception as e:
            logger.error(f"[删除向量]删除向量失败，报错信息:{str(e)}", exc_info=True)
            raise
