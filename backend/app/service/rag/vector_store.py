'''向量存储服务（Qdrant 版，替代原 Chroma 实现）'''
import os
from typing import Callable, Optional

from langchain_qdrant import QdrantVectorStore                                     # Qdrant向量库
from langchain_text_splitters import RecursiveCharacterTextSplitter               # 文本切割器
from langchain_core.documents import Document
from qdrant_client import QdrantClient                                            # Qdrant客户端
from qdrant_client.models import Distance, VectorParams                           # Qdrant建集参数

from app.utils.path_tool import get_abs_path                                      # 获取绝对路径
from app.utils.file_handler import (get_file_documents, get_file_md5_hex,
                                    listdir_with_allowed_type)                 # 文件处理工具
from app.utils.config_handler import qdrant_conf                                 # Qdrant配置项
from app.utils.logger_handler import logger                                      # 日志器
from app.modelFactory.factory import embed_model                                 # 文本嵌入模型


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

        # 文本分割器
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size=qdrant_conf["chunk_size"],        # 分割后每个文本块的大小
            chunk_overlap=qdrant_conf["chunk_overlap"],  # 相邻文本块之间的重叠字符数
            separators=qdrant_conf["separators"],        # 分割凭据符号
            length_function=len,                         # 计算文本长度的函数
        )

    def get_retriever(self):
        """返回检索器"""
        return self.vector_store.as_retriever(search_kwargs={"k": qdrant_conf["k"]})

    def upload_file(self, file_path: str, document_id: Optional[int] = None) -> list[tuple[str, str]]:
        """
        单个文件切分后写入 Qdrant 向量库。
        Args:
            file_path (str): 待向量化的文件路径
            document_id (int, optional): 关联的 document 表 ID，写入分块 metadata，
                供问答引用来源反查文档信息

        Returns:
            list[tuple[str, str]]: [(chunk_text, vector_id)]，供写入 document_chunk 表
        """
        try:
            # 获取文档内容列表
            documents: list[Document] = get_file_documents(file_path)

            # 如果文档无内容
            if not documents:
                raise ValueError(f"[上传向量化]{file_path}内没有有效文本内容")

            # 进行文本分割
            split_document: list[Document] = self.spliter.split_documents(documents)

            # 如果分割后无有效内容
            if not split_document:
                raise ValueError(f"[上传向量化]{file_path}分割后没有有效文本")

            # 关联 document_id 到分块元数据（用于问答引用来源反查）
            if document_id is not None:
                for doc in split_document:
                    doc.metadata = {"document_id": document_id}

            # 将内容存入 Qdrant，返回各分块的 point id
            vector_ids: list[str] = self.vector_store.add_documents(split_document)

            logger.info(f"[上传向量化]{file_path}向量化成功，共 {len(vector_ids)} 个分块")
            return list(zip([doc.page_content for doc in split_document], vector_ids))
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

    def load_document(self, md5_exists: Optional[Callable[[str], bool]] = None):
        """
        遍历 data 目录批量加载文档到 Qdrant 向量库。
        Args:
            md5_exists (Callable, optional): md5 去重回调 md5_exists(md5_hex)->bool，
                由调用方从 document 表查询（md5 去重已迁移至数据库），缺省则不去重
        """
        # 获取数据文件列表
        allowed_files_path: list[str] = listdir_with_allowed_type(
            get_abs_path(qdrant_conf["data_path"]),
            tuple(qdrant_conf["allow_knowledge_file_type"]),
        )

        for path in allowed_files_path:
            # 获取文件的md5值
            md5_hex = get_file_md5_hex(path)

            # 检查文件是否已经存储（迁移自 md5.txt：现由 document 表 md5_hash 承担）
            if md5_exists and md5_hex and md5_exists(md5_hex):
                logger.info(f"[加载知识库]{path}内容已经存在知识库内，跳过")
                continue

            try:
                # 获取文档内容列表
                documents: list[Document] = get_file_documents(path)

                # 如果文档无内容
                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本内容，跳过")
                    continue

                # 进行文本分割
                split_document: list[Document] = self.spliter.split_documents(documents)

                # 如果分割后无有效内容
                if not split_document:
                    logger.warning(f"[加载知识库]{path}分割后没有有效文本")
                    continue

                # 将内容存入向量库
                self.vector_store.add_documents(split_document)

                logger.info(f"[加载知识库]{path}内容加载成功")
            except Exception as e:
                # exc_info=True记录详细报错信息
                logger.error(f"[加载知识库]{path}加载失败，报错信息:{str(e)}", exc_info=True)
                continue
