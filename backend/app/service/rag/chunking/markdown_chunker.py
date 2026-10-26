'''Markdown 解析分块器（P1）：按 h1~h3 标题层级切分'''
from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter

_HEADERS = [("#", "h1"), ("##", "h2"), ("###", "h3")]


def chunk_markdown(file_path: str) -> list[Document]:
    '''按标题层级切分；保留标题原文，h1>h2>h3 拼接为 section_path'''
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS, strip_headers=False)
    with open(file_path, "r", encoding="utf-8") as f:
        md_docs = splitter.split_text(f.read())
    docs = []
    for md in md_docs:
        section_parts = [md.metadata[h] for h in ("h1", "h2", "h3") if md.metadata.get(h)]
        meta = {}
        if section_parts:
            meta["section_path"] = " > ".join(section_parts)
        docs.append(Document(page_content=md.page_content, metadata=meta))
    return docs
