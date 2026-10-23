'''纯文本解析分块器（P1）：段落边界贪心打包，超长段落句级再分'''
import re

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.utils.config_handler import retrieval_conf

_DEFAULT_CHUNK_SIZE = 500
_DEFAULT_MAX_CHUNK_SIZE = 800
_DEFAULT_CHUNK_OVERLAP = 50
_DEFAULT_SEPARATORS = ["\n\n", "\n", "。", "！", "？", " ", ""]


def chunk_text(file_path: str) -> list[Document]:
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return []

    chunking_conf = retrieval_conf.get("chunking", {})
    chunk_size = int(chunking_conf.get("chunk_size", _DEFAULT_CHUNK_SIZE))
    max_size = int(chunking_conf.get("max_chunk_size", _DEFAULT_MAX_CHUNK_SIZE))

    # 1. 超长段落（> max_size）按句级分隔符再分
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=int(chunking_conf.get("chunk_overlap", _DEFAULT_CHUNK_OVERLAP)),
        separators=chunking_conf.get("separators", _DEFAULT_SEPARATORS),
    )
    units: list[tuple[str, int]] = []  # (text, 段落序号)
    for no, para in enumerate(paragraphs, start=1):
        if len(para) <= max_size:
            units.append((para, no))
        else:
            for piece in splitter.split_text(para):
                units.append((piece, no))

    # 2. 相邻单元贪心打包至 chunk_size（只在段落边界切，不截断段落）
    docs: list[Document] = []
    buf: list[str] = []
    buf_start, buf_end = None, None
    total = 0
    for piece, no in units:
        if buf and total + len(piece) > chunk_size:
            docs.append(_make_doc(buf, buf_start, buf_end))
            buf, total, buf_start, buf_end = [], 0, None, None
        buf.append(piece)
        total += len(piece)
        if buf_start is None:
            buf_start = no
        buf_end = no
    if buf:
        docs.append(_make_doc(buf, buf_start, buf_end))
    return docs


def _make_doc(buf: list[str], start: int, end: int) -> Document:
    content = "\n".join(buf)
    return Document(page_content=content, metadata={"paragraph_range": f"{start}~{end}"})


def _split_paragraphs(text: str) -> list[str]:
    '''按空行分段；整篇无空行但有换行时退化为按单换行分段'''
    text = text.strip()
    if not text:
        return []
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(parts) == 1 and "\n" in parts[0]:
        parts = [p.strip() for p in parts[0].split("\n") if p.strip()]
    return parts
