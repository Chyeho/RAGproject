'''
向量检索服务
'''
from langchain_chroma import Chroma
import config_data as config

class VectorStoreService(object):
    def __init__(self,embedding):
        self.embedding = embedding     # 存储导入的嵌入模型

        self.vector_store = Chroma(
            collection_name=config.collection_name,
            embedding_function=self.embedding,
            persist_directory=config.persist_directory,
        )

    def get_retriever(self):
        '''返回向量检索器，方便后续加入链'''
        return self.vector_store.as_retriever(search_kwargs={"k":config.similarity_threshold})

# # 测试代码   
# if __name__ == '__main__':
#     from langchain_community.embeddings import DashScopeEmbeddings
#     retriever = VectorStoreService(DashScopeEmbeddings(model="text-embedding-v4")).get_retriever()

#     res = retriever.invoke("我的体重180斤，尺码推荐")
#     print(res)

        