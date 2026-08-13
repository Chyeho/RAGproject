'''RAG总结服务类'''
from app.service.rag.vector_store import VectorStoreService
from app.utils.prompt_loader import load_rag_prompt
from app.modelFactory.factory import chat_model
from app.service.history.history_store import get_chat_history
from app.utils.config_handler import rag_conf

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.runnables import RunnableLambda, RunnablePassthrough


class RagSummarizeService(object):
    def __init__(self):
        """初始化rag总结服务类"""
        self.vertor_service = VectorStoreService()                # 获取向量存储服务类
        self.retriever = self.vertor_service.get_retriever()      # 获取检索器
        self.rag_prompt = load_rag_prompt()                       # 加载rag提示词模板
        self.prompt_template = ChatPromptTemplate(
            [
                ("system", self.rag_prompt),
                ("system", "并且我提供用户的对话历史记录，如下："),
                MessagesPlaceholder("history"),
                ("user", "请回答用户提问：{input}")
            ]
        )                                                         # 聊天模型提示词模板（涉及多轮对话）
        self.chat_model = chat_model                              # 聊天模型
        self.chain = self.__get_chain()                           # 链

    def __get_chain(self):
        """初始化执行链（手动管理对话历史，替代已弃用的 RunnableWithMessageHistory）"""

        # list[Document] 转字符串功能函数（检索器返回的是文档列表，而聊天模型需要的是字符串）
        def format_document(docs: list[Document]):
            if not docs:
                return "无相关资料"
            context = ""
            counter = 0
            for doc in docs:
                counter += 1
                context += f"【参考资料{counter}】：参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"
            return context

        # 解决 retriever 的输入问题（需要字符串输入，而用户提问是字典）
        def format_for_retriever(value: dict) -> str:
            return value["input"]

        # 格式化 self.prompt_template 的输入（提示词模板需要三个参数：input, context, history）
        def format_for_prompt_template(value):
            new_value = {}
            new_value["input"] = value["input"]["input"]
            new_value["history"] = value["input"]["history"]
            new_value["context"] = value["context"]
            return new_value

        # 构建基础链
        chain = (
            {"input": RunnablePassthrough(), "context": RunnableLambda(format_for_retriever) | self.retriever | format_document}
            | RunnableLambda(format_for_prompt_template) | self.prompt_template | self.chat_model | StrOutputParser()
        )
        return chain

    def rag_summarize(self, query: str, session_id: str | None = None) -> str:
        """
        手动管理对话历史：从文件读取 -> 传入链 -> 写回文件

        Args:
            query (str): 用户提问
            session_id (str|None): 会话隔离标识，不同会话使用独立的历史文件；
                                   为 None 时回退到 rag_conf 配置的 session_id（默认 user_001）
        """
        if not session_id:
            session_id = rag_conf["session_config"]["configurable"]["session_id"]
        history_obj = get_chat_history(session_id)
        history_messages = history_obj.messages

        # 执行链
        response = self.chain.invoke(
            {"input": query, "history": history_messages}
        )

        # 将本次对话追加到历史记录
        history_obj.add_messages([HumanMessage(content=query), AIMessage(content=response)])

        return response


# if __name__ == '__main__':
#     rag = RagSummarizeService()
#     print(rag.rag_summarize("公司的考勤制度是什么"))