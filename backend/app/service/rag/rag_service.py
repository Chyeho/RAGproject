'''RAG总结服务类（P4：rag_summarize 返回 (answer, retrieved_docs)，检索与引用同源）'''
from langchain_core.retrievers import BaseRetriever

from app.service.rag.retrieval import build_retriever
from app.service.rag.vector_store import VectorStoreService
from app.utils.prompt_loader import load_rag_prompt
from app.modelFactory.factory import chat_model
from app.service.history.history_store import get_chat_history
from app.utils.config_handler import rag_conf

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage


def format_document(docs: list[Document]) -> str:
    '''检索文档列表 → 提示词上下文字符串（聊天模型需要字符串输入）'''
    if not docs:
        return "无相关资料"
    context = ""
    counter = 0
    for doc in docs:
        counter += 1
        context += f"【参考资料{counter}】：参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"
    return context


class RagSummarizeService(object):
    def __init__(self, retriever: BaseRetriever | None = None):
        """初始化rag总结服务类

        Args:
            retriever: 外部注入的检索器（评测 preset / 单测用）；缺省按
                       retrieval_config.yml 开关组装 P2 检索链路（全关等价旧链路）
        """
        self.vertor_service = VectorStoreService()                # 获取向量存储服务类
        self.retriever = retriever if retriever is not None else build_retriever(self.vertor_service)  # 检索链路（P2）
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
        # 生成链（P4：检索显式分离到 rag_summarize，链只负责 上下文+历史 → 回答）
        self.chain = self.prompt_template | self.chat_model | StrOutputParser()

    def retrieve(self, query: str, top_k: int | None = None) -> list[Document]:
        '''只检索不生成：供 ReAct 工具复用现有混合检索 + 精排链路

        Args:
            query: 检索问题
            top_k: 可选截断条数；不超过当前链路有效输出条数（当前默认 5）
        '''
        docs = self.retriever.invoke(query)
        if top_k is not None and top_k > 0:
            docs = docs[:top_k]
        return docs

    def _generate(self, query: str, docs: list[Document], history_messages: list) -> str:
        '''基于已检索文档与历史生成回答（检索与生成分离）'''
        return self.chain.invoke(
            {"input": query, "history": history_messages, "context": format_document(docs)}
        )

    def summarize(self, query: str, docs: list[Document], session_id: str | None = None,
                  write_history: bool = False) -> str:
        '''对给定文档生成总结回答（ReAct 工具调用默认不写会话历史）

        Args:
            query: 用户/子查询问题
            docs: 已检索文档
            session_id: 可选会话标识；提供时读取该会话历史
            write_history: 是否把本次问答写回会话历史（默认 False）
        '''
        history_obj = get_chat_history(session_id) if session_id else None
        history_messages = history_obj.messages if history_obj else []
        response = self._generate(query, docs, history_messages)
        if write_history and history_obj is not None:
            history_obj.add_messages([HumanMessage(content=query), AIMessage(content=response)])
        return response

    def rag_summarize(self, query: str, session_id: str | None = None,
                      write_history: bool = True) -> tuple[str, list[Document]]:
        """
        手动管理对话历史：从文件读取 -> 检索 -> 生成 -> 写回文件

        Args:
            query (str): 用户提问
            session_id (str|None): 会话隔离标识，不同会话使用独立的历史文件；
                                   为 None 时回退到 rag_conf 配置的 session_id（默认 user_001）
            write_history (bool): 是否写回会话历史；ReAct 内部工具调用传 False，
                                  避免子查询污染多轮对话历史（外部默认行为不变）

        Returns:
            (answer, retrieved_docs)：回答与本次命中的文档列表（引用来源同源拼装，P4）
        """
        if not session_id:
            session_id = rag_conf["session_config"]["configurable"]["session_id"]
        history_obj = get_chat_history(session_id)
        history_messages = history_obj.messages

        # 检索（单独执行，结果同时用于生成上下文与引用拼装）
        docs = self.retrieve(query)

        # 执行生成链
        response = self._generate(query, docs, history_messages)

        # 将本次对话追加到历史记录（工具调用可显式关闭）
        if write_history:
            history_obj.add_messages([HumanMessage(content=query), AIMessage(content=response)])

        return response, docs


# if __name__ == '__main__':
#     rag = RagSummarizeService()
#     print(rag.rag_summarize("公司的考勤制度是什么"))
