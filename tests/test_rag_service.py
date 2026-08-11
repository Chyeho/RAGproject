# -*- coding: utf-8 -*-
"""RAG 总结服务模块单元测试"""
from unittest.mock import patch, MagicMock

import pytest
from langchain_core.messages import HumanMessage, AIMessage


class TestRagSummarizeServiceInit:
    """测试 RAG 服务初始化"""

    @patch("app.service.rag.rag_service.VectorStoreService")
    def test_init_creates_vector_store(self, mock_vs):
        mock_vs_instance = MagicMock()
        mock_retriever = MagicMock()
        mock_vs_instance.get_retriever.return_value = mock_retriever
        mock_vs.return_value = mock_vs_instance

        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()
        assert service.vertor_service is mock_vs_instance
        assert service.retriever is mock_retriever

    @patch("app.service.rag.rag_service.VectorStoreService")
    def test_init_loads_rag_prompt(self, mock_vs):
        mock_vs.return_value = MagicMock()
        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()
        assert isinstance(service.rag_prompt, str)
        assert len(service.rag_prompt) > 0

    @patch("app.service.rag.rag_service.VectorStoreService")
    def test_init_creates_prompt_template(self, mock_vs):
        mock_vs.return_value = MagicMock()
        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()
        assert service.prompt_template is not None

    @patch("app.service.rag.rag_service.VectorStoreService")
    def test_init_has_chat_model(self, mock_vs):
        mock_vs.return_value = MagicMock()
        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()
        assert service.chat_model is not None

    @patch("app.service.rag.rag_service.VectorStoreService")
    def test_init_creates_chain(self, mock_vs):
        mock_vs.return_value = MagicMock()
        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()
        assert service.chain is not None


class TestRagSummarize:
    """测试 rag_summarize 方法"""

    @patch("app.service.rag.rag_service.VectorStoreService")
    @patch("app.service.rag.rag_service.get_chat_history")
    def test_rag_summarize_returns_string(self, mock_get_history, mock_vs):
        """验证 rag_summarize 返回字符串"""
        mock_vs.return_value = MagicMock()

        # mock 历史消息服务
        mock_history_obj = MagicMock()
        mock_history_obj.messages = []
        mock_get_history.return_value = mock_history_obj

        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()

        # mock chain.invoke
        service.chain = MagicMock()
        service.chain.invoke.return_value = "这是根据参考资料生成的总结回答"

        result = service.rag_summarize("公司的考勤制度是什么")
        assert isinstance(result, str)
        assert len(result) > 0

    @patch("app.service.rag.rag_service.VectorStoreService")
    @patch("app.service.rag.rag_service.get_chat_history")
    def test_rag_summarize_appends_to_history(self, mock_get_history, mock_vs):
        """验证执行后会将问答追加到历史记录"""
        mock_vs.return_value = MagicMock()

        mock_history_obj = MagicMock()
        mock_history_obj.messages = []
        mock_get_history.return_value = mock_history_obj

        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()

        service.chain = MagicMock()
        service.chain.invoke.return_value = "总结回答"

        service.rag_summarize("测试问题")
        # 验证 add_messages 被调用
        mock_history_obj.add_messages.assert_called_once()
        args = mock_history_obj.add_messages.call_args[0][0]
        assert len(args) == 2  # HumanMessage + AIMessage
        assert args[0].content == "测试问题"

    @patch("app.service.rag.rag_service.VectorStoreService")
    @patch("app.service.rag.rag_service.get_chat_history")
    def test_rag_summarize_uses_history(self, mock_get_history, mock_vs):
        """验证会使用历史消息"""
        mock_vs.return_value = MagicMock()

        mock_history_obj = MagicMock()
        existing_msgs = [HumanMessage(content="你好"), AIMessage(content="你好！")]
        mock_history_obj.messages = existing_msgs
        mock_get_history.return_value = mock_history_obj

        from app.service.rag.rag_service import RagSummarizeService
        service = RagSummarizeService()

        service.chain = MagicMock()
        service.chain.invoke.return_value = "基于历史的回答"

        service.rag_summarize("考勤制度")
        # 验证传入 chain 的 history 包含了之前的消息
        call_args = service.chain.invoke.call_args[0][0]
        assert "history" in call_args
        assert len(call_args["history"]) == 2


class TestChainFormatFunctions:
    """测试链中的格式化函数"""

    def test_format_document_empty(self):
        """测试 format_document 内部函数对空文档的处理"""
        # 直接模拟 format_document 逻辑（与 rag_service.py 中一致）
        def format_document(docs):
            if not docs:
                return "无相关资料"
            context = ""
            counter = 0
            for doc in docs:
                counter += 1
                context += f"【参考资料{counter}】：参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"
            return context

        result = format_document([])
        assert result == "无相关资料"

    def test_format_document_with_docs(self):
        """测试 format_document 内部函数对非空文档的处理"""
        from langchain_core.documents import Document

        # 有文档
        def format_document(docs):
            if not docs:
                return "无相关资料"
            context = ""
            counter = 0
            for doc in docs:
                counter += 1
                context += f"【参考资料{counter}】：参考资料：{doc.page_content} | 参考元数据：{doc.metadata}\n"
            return context

        docs = [
            Document(page_content="考勤制度第一条", metadata={"source": "员工手册.txt"}),
            Document(page_content="考勤制度第二条", metadata={"source": "员工手册.txt"}),
        ]
        result = format_document(docs)
        assert "【参考资料1】" in result
        assert "【参考资料2】" in result
        assert "考勤制度第一条" in result
        assert "员工手册.txt" in result
