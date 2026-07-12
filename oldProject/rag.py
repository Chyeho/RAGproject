'''
rag核心服务，构建链
'''
from oldProject.vector_stores import VectorStoreService
from langchain_community.embeddings import DashScopeEmbeddings
import config_data as config
from langchain_core.prompts import ChatPromptTemplate,MessagesPlaceholder
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.runnables import RunnablePassthrough,RunnableLambda   # RunnableLambda函数可以将任意python函数转为Runnable对象，方便入链
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableWithMessageHistory
from file_history_store import get_history
from langchain_core.documents import Document

'''打印提示词用作日志'''
def print_prompt(prompt):
    print("="*23)
    print(prompt.to_string())
    print("="*23)

    return prompt

class RagService(object):
    def __init__(self):
        # 向量检索服务类
        self.vector_service = VectorStoreService(
            embedding=DashScopeEmbeddings(model=config.embedding_model_name)
        )   

        # 聊天模型提示词模板
        self.prompt_template = ChatPromptTemplate(
            [
                ("system","以我提供的已知参考资料为主，简洁和专业的回答用户问题。参考资料：{context}"),
                ("system","并且我提供用户的对话历史记录，如下："),
                MessagesPlaceholder("history"),
                ("user","请回答用户提问：{input}")
            ]
        )

        # 聊天模型
        self.chat_model = ChatTongyi(model=config.chat_model_name)

        # 构建链
        self.chain = self.__get_chain()

    def __get_chain(self):
        '''获得执行链'''
        # 获取检索器
        retriever = self.vector_service.get_retriever()

        # list[Document]转字符串 功能函数
        def format_document(docs:list[Document]):
            if not docs:
                return "无相关资料"
        
            formatted_str = ""
            for doc in docs:
                formatted_str += f"文档片段：\n{doc.page_content}\n文档源数据：{doc.metadata}\n\n"

            return formatted_str
        
        # 解决retriever的输入问题
        # 流程：先打印retriever的初始输入（调试） -> 查看初始输入来进行输入问题处理
        def format_for_retriever(value:dict) -> str:
            return value["input"]
        
        # self.prompt_template的输入问题 
        # 流程：先打印self.prompt_template的初始输入（调试） -> 查看初始输入来进行输入问题处理
        def format_for_prompt_template(value):
            #需要三个：{input,context,history}
            new_value = {}
            new_value["input"] =  value["input"]["input"]
            new_value["history"] = value["input"]["history"]
            new_value["context"] = value["context"]

            return new_value

        chain = (
            {"input":RunnablePassthrough() ,"context": RunnableLambda(format_for_retriever) | retriever | format_document}
              | RunnableLambda(format_for_prompt_template) | self.prompt_template | print_prompt | self.chat_model | StrOutputParser()
        )

        '''构建增强链,增强链要求的输入为dict'''
        conversation_chain = RunnableWithMessageHistory(
            chain,                             # 需要增强的链
            get_history,                       # 获取历史消息函数
            input_messages_key="input",
            history_messages_key="history",
        )

        return conversation_chain
