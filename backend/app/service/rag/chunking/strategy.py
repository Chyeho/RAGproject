'''分块策略路由与智能切分规则（P1）

- chunk_file：按扩展名路由到对应格式解析器；
  结构化格式（pdf/docx/doc/md）额外应用智能切分规则与嵌入增强（正文前拼接章节路径）
- apply_smart_rules：先超长再分（>800 字按段落边界切分，不句中截断），
  后小单元合并（<100 字且同父章节的相邻单元合并）
'''
import os

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.utils.config_handler import qdrant_conf
from app.service.rag.chunking.pdf_chunker import chunk_pdf
from app.service.rag.chunking.docx_chunker import chunk_docx
from app.service.rag.chunking.markdown_chunker import chunk_markdown
from app.service.rag.chunking.excel_chunker import chunk_excel
from app.service.rag.chunking.text_chunker import chunk_text

# 结构化格式：应用智能切分规则后做嵌入增强（xlsx 按行组、txt 按段落，均不做章节合并）
STRUCTURED_EXTS = {"pdf", "docx", "doc", "md", "markdown"}

# 智能切分规则默认参数（实际以 qdrant_config.yml 为准，调用时读取以便运行时更新生效）
_DEFAULT_MAX_CHUNK_SIZE = 800
_DEFAULT_MIN_CHUNK_SIZE = 100
_DEFAULT_CHUNK_OVERLAP = 50
_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", " ", ""]


def chunk_file(file_path: str) -> list[Document]:
    '''按文件扩展名路由到对应格式的解析分块器'''
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")
    if ext == "pdf":
        docs = chunk_pdf(file_path)
    elif ext in ("docx", "doc"):
        docs = chunk_docx(file_path)
    elif ext in ("md", "markdown"):
        docs = chunk_markdown(file_path)
    elif ext == "xlsx":
        docs = chunk_excel(file_path)
    elif ext == "txt":
        docs = chunk_text(file_path)
    else:
        raise ValueError(f"不支持的文件格式：.{ext}，当前支持 pdf/docx/doc/md/xlsx/txt")

    if ext in STRUCTURED_EXTS:
        docs = apply_smart_rules(docs)
        docs = _enhance_for_embedding(docs)
    return docs


def _enhance_for_embedding(docs: list[Document]) -> list[Document]:
    '''嵌入增强：正文前拼接章节路径，提升检索命中率'''
    for doc in docs:
        section = doc.metadata.get("section_path")
        if section:
            doc.page_content = f"[{section}]\n{doc.page_content}"
    return docs


def apply_smart_rules(docs: list[Document]) -> list[Document]:
    '''智能切分规则：先超长再分，后小单元合并（合并不跨父章节）'''
    if not docs:
        return docs
    max_size = int(qdrant_conf.get("max_chunk_size", _DEFAULT_MAX_CHUNK_SIZE))
    min_size = int(qdrant_conf.get("min_chunk_size", _DEFAULT_MIN_CHUNK_SIZE))
    docs = _split_oversized(docs, max_size)
    docs = _merge_small(docs, min_size, max_size)
    return docs


def _split_oversized(docs: list[Document], max_size: int) -> list[Document]:
    '''超长单元（> max_size）按分隔符再分，优先段落边界、不句中截断'''
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=max_size,
        chunk_overlap=int(qdrant_conf.get("chunk_overlap", _DEFAULT_CHUNK_OVERLAP)),
        separators=qdrant_conf.get("separators", _DEFAULT_SEPARATORS),
    )
    result = []
    for doc in docs:
        if len(doc.page_content) <= max_size:
            result.append(doc)
            continue
        pieces = splitter.split_text(doc.page_content)
        for i, piece in enumerate(pieces):
            meta = dict(doc.metadata)
            if len(pieces) > 1:
                meta["split_index"] = i
                meta["split_total"] = len(pieces)
            result.append(Document(page_content=piece, metadata=meta))
    return result


def _merge_small(docs: list[Document], min_size: int, max_size: int) -> list[Document]:
    '''相邻小单元合并：同父章节、任一方 < min_size、合并后不超 max_size'''
    result: list[Document] = []
    for doc in docs:
        prev = result[-1] if result else None
        if prev is not None:
            prev_parent = _parent_of(prev.metadata.get("section_path"))
            cur_parent = _parent_of(doc.metadata.get("section_path"))
            merged_len = len(prev.page_content) + len(doc.page_content)
            can_merge = (
                prev_parent is not None
                and prev_parent == cur_parent
                and (len(prev.page_content) < min_size or len(doc.page_content) < min_size)
                and merged_len <= max_size
            )
            if can_merge:
                prev.page_content = prev.page_content + "\n" + doc.page_content
                # 合并的是兄弟小节时，章节路径退化为父路径
                if prev.metadata.get("section_path") != doc.metadata.get("section_path"):
                    prev.metadata["section_path"] = prev_parent
                # 页码取并集
                starts = [v for v in (prev.metadata.get("page_start"), doc.metadata.get("page_start")) if v is not None]
                ends = [v for v in (prev.metadata.get("page_end"), doc.metadata.get("page_end")) if v is not None]
                if starts:
                    prev.metadata["page_start"] = min(starts)
                if ends:
                    prev.metadata["page_end"] = max(ends)
                continue
        result.append(doc)
    return result


def _parent_of(section_path) -> str | None:
    '''取章节父路径：顶级章节父路径为空串，无章节信息返回 None'''
    if section_path is None:
        return None
    parts = section_path.split(" > ")
    if len(parts) <= 1:
        return ""
    return " > ".join(parts[:-1])
