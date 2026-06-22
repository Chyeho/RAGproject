'''向量存储服务'''
import os

from langchain_chroma import Chroma                                                            # Chroma向量库
from langchain_text_splitters import RecursiveCharacterTextSplitter                            # 文本切割器
from langchain_core.documents import Document

from app.utils.path_tool import get_abs_path                                                   # 获取绝对路径
from app.utils.file_handler import (check_md5_hex, get_file_documents, get_file_md5_hex,
                                     listdir_with_allowed_type, save_md5_hex)                  # 文件处理工具
from app.utils.config_handler import chroma_conf                                               # Chroma配置项
from app.utils.logger_handler import logger                                                    # 日志器
from app.modelFactory.factory import embed_model                                               # 文本嵌入模型


class VectorStoreService(object):
    def __init__(self):
        # chroma数据库
        self.vector_store = Chroma(
            collection_name = chroma_conf["collection_name"],     # 要操作的集合名
            embedding_function = embed_model,                     # 文本嵌入模型
            persist_directory = os.path.join(os.path.dirname(get_abs_path("")),chroma_conf["persist_directory"])  # 向量库本地地址
        )

        # 文本分割器
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size = chroma_conf["chunk_size"],        # 分割后每个文本块的大小
            chunk_overlap = chroma_conf["chunk_overlap"], # 相邻文本块之间的重叠字符数
            separators = chroma_conf["separators"],        # 分割凭据符号
            length_function = len,                        # 计算文本长度的函数
        )

    def get_retriever(self):
        """返回检索器"""
        return self.vector_store.as_retriever(search_kwargs={"k":chroma_conf["k"]}) # 获取检索器对象，k为检索的文本块数量
    
    def load_document(self):
        # 获取数据文件列表
        allowed_files_path:list[str] = listdir_with_allowed_type(
            get_abs_path(chroma_conf["data_path"]),
            tuple(chroma_conf["allow_knowledge_file_type"]),
        )

        for path in allowed_files_path:
            # 获取文件的md5值
            md5_hex = get_file_md5_hex(path)

            # 检查文件是否已经存储
            if check_md5_hex(md5_hex):
                logger.info(f"[加载知识库]{path}内容已经存在知识库内，跳过")
                continue
                
            try:
                # 获取文档内容列表
                documents:list[Document] = get_file_documents(path)

                # 如果文档无内容
                if not documents:
                    logger.warning(f"[加载知识库]{path}内没有有效文本内容，跳过")
                    continue
                
                # 进行文本分割
                split_document:list[Document] = self.spliter.split_documents(documents)

                # 如果分割后无有效内容
                if not split_document:
                    logger.warning(f"[加载知识库]{path}分割后没有有效文本")
                    continue
                
                # 将内容存入向量库
                self.vector_store.add_documents(split_document)

                # 记录这个文件的md5值
                save_md5_hex(md5_hex)

                logger.info(f"[加载知识库]{path}内容加载成功")
            except Exception as e:
                # exc_info=True记录详细报错信息
                logger.error(f"[加载知识库]{path}加载失败，报错信息:{str(e)}",exc_info=True)
                continue
        
# if __name__ == '__main__':
#     vs = VectorStoreService()

#     vs.load_document()

#     retriever = vs.get_retriever()

#     res = retriever.invoke("薪酬福利")
#     for r in res:
#         print(r.page_content)
#         print("-"*20)
