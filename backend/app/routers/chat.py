'''会话路由：会话 CRUD、消息收发（非流式）、引用来源 citations'''
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.response import err, ok
from app.database.db import get_session
from app.dependencies import get_current_user
from app.models.chat_conversation import ChatConversation
from app.models.chat_message import ChatMessage
from app.models.documents import Document
from app.models.users import User
from app.service.orchestration import get_orchestrator
from app.utils.config_handler import hybrid_conf
from app.utils.logger_handler import logger

router = APIRouter(prefix="/api/chat", tags=["chat"])


class CreateConversationReq(BaseModel):
    title: str = Field(default="新会话", description="会话标题，可省略")


class SendMessageReq(BaseModel):
    conversationId: int = Field(description="会话ID")
    content: str = Field(description="用户消息内容")


def conv_to_dict(conv: ChatConversation) -> dict:
    """会话对象 → 契约格式"""
    return {
        "id": conv.id,
        "title": conv.title,
        "createdAt": conv.created_at.strftime("%Y-%m-%d %H:%M:%S") if conv.created_at else "",
        "updatedAt": conv.updated_at.strftime("%Y-%m-%d %H:%M:%S") if conv.updated_at else "",
    }


def msg_to_dict(msg: ChatMessage) -> dict:
    """消息对象 → 契约格式"""
    return {
        "id": msg.id,
        "role": msg.role,
        "content": msg.content,
        "citations": msg.citations or [],
        "createdAt": msg.created_at.strftime("%Y-%m-%d %H:%M:%S") if msg.created_at else "",
    }


async def get_owned_conversation(conversation_id: int, user: User, session: AsyncSession) -> ChatConversation | None:
    """按 ID 与归属校验查询会话"""
    conv = await session.get(ChatConversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        return None
    return conv


@router.get("/conversations")
async def get_conversations(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """会话列表（按 updatedAt 降序）"""
    rows = (await session.exec(
        select(ChatConversation)
        .where(ChatConversation.user_id == current_user.id)
        .order_by(ChatConversation.updated_at.desc())
    )).all()
    return ok({"list": [conv_to_dict(c) for c in rows]})


@router.post("/conversations")
async def create_conversation(
    req: CreateConversationReq,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """新建会话"""
    conv = ChatConversation(
        user_id=current_user.id,
        title=req.title or "新会话",
    )
    session.add(conv)
    await session.commit()
    await session.refresh(conv)
    logger.info(f"[会话]用户{current_user.id}新建会话(id={conv.id})")
    return ok(conv_to_dict(conv))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """删除会话（级联删除消息）"""
    conv = await get_owned_conversation(conversation_id, current_user, session)
    if conv is None:
        return err(5001, "会话不存在")
    await session.delete(conv)
    await session.commit()
    logger.info(f"[会话]用户{current_user.id}删除会话(id={conversation_id})")
    return ok(None, "删除成功")


@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """会话消息列表（按创建时间正序）"""
    conv = await get_owned_conversation(conversation_id, current_user, session)
    if conv is None:
        return err(5001, "会话不存在")
    rows = (await session.exec(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at.asc())
    )).all()
    return ok({"list": [msg_to_dict(m) for m in rows]})


@router.delete("/conversations/{conversation_id}/messages")
async def clear_messages(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """清空会话消息"""
    conv = await get_owned_conversation(conversation_id, current_user, session)
    if conv is None:
        return err(5001, "会话不存在")
    rows = (await session.exec(
        select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    )).all()
    for m in rows:
        await session.delete(m)
    await session.commit()
    logger.info(f"[会话]用户{current_user.id}清空会话(id={conversation_id})消息")
    return ok(None, "清空成功")


async def build_citations_from_docs(docs, session: AsyncSession) -> list[dict]:
    """用与回答同一次检索的命中文档拼装引用来源（P4：删除 build_citations 二次检索）

    引用按 document_id 去重（每篇文档取排序最靠前的命中块），携带章节路径与页码。
    """
    citations = []
    seen = set()
    for doc in docs:
        meta = doc.metadata or {}
        doc_id = meta.get("document_id")
        if doc_id is None:
            continue
        try:
            doc_id = int(doc_id)
        except (TypeError, ValueError):
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        try:
            db_doc = await session.get(Document, doc_id)
        except Exception as e:
            logger.warning(f"[会话]引用来源反查文档(id={doc_id})失败：{str(e)}")
            continue
        if db_doc is None:
            continue
        citations.append({
            "documentId": db_doc.id,
            "documentName": db_doc.file_name,
            "sectionPath": meta.get("section_path"),
            "pageStart": meta.get("page_start"),
            "pageEnd": meta.get("page_end"),
            "snippet": (doc.page_content or "")[:200],
        })
    return citations


@router.post("/messages")
async def send_message(
    req: SendMessageReq,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """发送消息（非流式）：入库 user 消息 → RAG 生成回答 → 拼装引用 → 入库 assistant 消息"""
    if not req.content.strip():
        return err(1001, "消息内容不能为空")

    conv = await get_owned_conversation(req.conversationId, current_user, session)
    if conv is None:
        return err(5001, "会话不存在")

    # 1. 入库 user 消息
    user_msg = ChatMessage(
        conversation_id=conv.id,
        role="user",
        content=req.content,
        citations=[],
    )
    session.add(user_msg)
    await session.commit()

    # 2. 首条消息时以用户内容作为会话标题
    if conv.title == "新会话":
        conv.title = req.content.strip()[:20]
    conv.updated_at = datetime.now()
    session.add(conv)
    await session.commit()

    # 3. 调用混合编排（每个会话独立历史：session_id = user_{uid}_conv_{cid}，同步调用放线程池）
    #    开关关闭时行为与改造前一致：RAG 直调返回 (answer, retrieved_docs)
    try:
        rag_session_id = f"user_{current_user.id}_conv_{conv.id}"
        result = await asyncio.to_thread(
            get_orchestrator().answer, req.content, rag_session_id
        )
        answer, retrieved_docs = result.answer, result.documents
    except Exception as e:
        logger.error(f"[会话]RAG 回答生成失败：{str(e)}", exc_info=True)
        return err(5000, f"回答生成失败：{str(e)}")

    # 4. 用同一次检索结果拼装引用来源
    citations = await build_citations_from_docs(retrieved_docs, session)

    # 5. 入库 assistant 消息
    try:
        assistant_msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=answer,
            citations=citations,
        )
        session.add(assistant_msg)
        await session.commit()
        await session.refresh(assistant_msg)
    except Exception as e:
        logger.error(f"[会话]助手消息入库失败：{str(e)}", exc_info=True)
        return err(5000, "回答已生成但保存失败，请重试")

    logger.info(
        f"[会话]用户{current_user.id}会话(id={conv.id})问答完成，引用 {len(citations)} 条，"
        f"route={result.trace.get('route')} source={result.trace.get('answer_source')} "
        f"fallback={result.trace.get('fallback')} total_ms={result.trace.get('total_ms')}"
    )
    data = msg_to_dict(assistant_msg)
    # 可选字段：默认不返回；答辩/调试环境可开启，旧前端忽略未知字段
    if bool(hybrid_conf.get("RETURN_TRACE_TO_CLIENT", False)) and result.trace_id:
        data["traceId"] = result.trace_id
    return ok(data)
