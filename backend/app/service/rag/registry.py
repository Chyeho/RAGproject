# -*- coding: utf-8 -*-
'''RAG 服务注册表（P4 参数热更新）

chat.py 懒加载单例改造为线程安全注册表：
- get_rag_service()：双重检查锁懒加载，聊天/Agent 工具共用同一实例
- rebuild()：settings 保存检索参数后重建链路单例；新实例构建成功后原子替换，
  构建失败保留旧实例继续服务（新配置下次重启生效），服务不中断。
'''
import threading

from app.service.rag.rag_service import RagSummarizeService
from app.utils.logger_handler import logger

_lock = threading.Lock()
_rag_service: RagSummarizeService | None = None


def get_rag_service() -> RagSummarizeService:
    '''线程安全懒加载单例（读路径无锁快查，仅首次构建加锁）'''
    global _rag_service
    if _rag_service is None:
        with _lock:
            if _rag_service is None:
                _rag_service = RagSummarizeService()
    return _rag_service


def rebuild() -> bool:
    '''按当前 retrieval_conf 重建 RAG 链单例（同步阻塞，调用方放线程池）

    新实例在锁外构建（构建期间读请求继续走旧实例），成功后锁内原子替换。

    Returns:
        True 重建成功已生效；False 构建失败（旧实例保留，下次重启生效）
    '''
    global _rag_service
    try:
        new_service = RagSummarizeService()
    except Exception as e:
        logger.error(f"[热更新]RAG 链路重建失败，保留旧实例（新配置下次重启生效）：{e}", exc_info=True)
        return False
    with _lock:
        _rag_service = new_service
    logger.info("[热更新]RAG 链路已按新配置重建生效")
    return True
