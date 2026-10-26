'''PDF 解析分块器（P1）

三级策略：
1. 章节书签（TOC）：每页归属文档顺序中最后一个 start <= 页码 的条目，按章节聚合
2. 字体启发式：无书签时，按字号显著大于正文或加粗的短行识别标题，字号降序映射 h1/h2/h3
3. 按页兜底：无任何结构信息时按页切块
'''
import logging

import pymupdf
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

# fitz span flags 第 5 位（值 16）表示粗体
_BOLD_FLAG = 16
# 标题行长度上限（超出更可能是正文长句）
_TITLE_MAX_LEN = 60
# 标题不应以句读结尾
_SENTENCE_ENDINGS = ("。", "！", "？", "；", "，", ".", "!", "?", ";", ",")


def chunk_pdf(file_path: str) -> list[Document]:
    '''三级策略解析 PDF：TOC 书签 > 字体启发式 > 按页兜底'''
    with pymupdf.open(file_path) as pdf:
        if pdf.page_count == 0:
            return []
        toc = pdf.get_toc()
        if toc:
            docs = _sections_from_toc(pdf, toc)
            if docs:
                return docs
        docs = _sections_from_font(pdf)
        if docs:
            return docs
        return _pages_fallback(pdf)


def _sections_from_toc(pdf, toc) -> list[Document]:
    '''按书签切章节：每页归属文档顺序中最后一个 start <= 页码 的条目（最内层）'''
    # 条目格式 [level, title, page(1-based)]，过滤无效条目
    entries = [
        (str(t[1]).strip(), int(t[2]))
        for t in toc
        if len(t) >= 3 and t[1] and str(t[1]).strip() and int(t[2]) >= 1
    ]
    if not entries:
        return []
    total = pdf.page_count
    page_texts = [pdf[p].get_text("text").strip() for p in range(total)]

    # 每页归属章节索引（-1 表示首个书签开始页之前，如封面/目录）
    page_owner = []
    for p in range(1, total + 1):
        owner = -1
        for idx, (_, start) in enumerate(entries):
            if start <= p:
                owner = idx
        page_owner.append(owner)

    # 归属随页码单调不减，连续同归属的页聚合成一个章节单元
    ranges: list[list[int]] = []  # [owner, start_page, end_page]
    for p in range(total):
        owner = page_owner[p]
        if ranges and ranges[-1][0] == owner:
            ranges[-1][2] = p + 1
        else:
            ranges.append([owner, p + 1, p + 1])

    docs: list[Document] = []
    for owner, start_p, end_p in ranges:
        body = "\n".join(t for t in page_texts[start_p - 1:end_p] if t)
        if not body:
            continue
        meta = {"page_start": start_p, "page_end": end_p}
        if owner >= 0:
            meta["section_path"] = entries[owner][0]
        docs.append(Document(page_content=body, metadata=meta))
    return docs


def _sections_from_font(pdf) -> list[Document]:
    '''无书签时按字体启发式识别标题切章节'''
    # 1. 收集所有文本行与字号权重（按文本长度加权，用于统计正文字号）
    lines = []  # {"page","text","font","bold"}
    font_weights = {}  # 字号 -> 文本长度累计
    for p in range(pdf.page_count):
        d = pdf[p].get_text("dict")
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                text = "".join(s.get("text", "") for s in spans).strip()
                if not text:
                    continue
                max_font = max(s.get("size", 0) for s in spans)
                bold = any(bool(s.get("flags", 0) & _BOLD_FLAG) for s in spans)
                lines.append({"page": p + 1, "text": text, "font": max_font, "bold": bold})
                for s in spans:
                    size = round(s.get("size", 0), 1)
                    font_weights[size] = font_weights.get(size, 0) + len(s.get("text", ""))
    if not lines:
        return []

    # 2. 正文字号 = 按文本长度加权的众数
    body_font = max(font_weights.items(), key=lambda kv: kv[1])[0]

    # 3. 标题判定；识别出的标题过少说明启发式不可靠，交由兜底策略
    titles = [ln for ln in lines if _is_title(ln, body_font)]
    if len(titles) < 2:
        return []

    # 4. 标题字号降序取前 3 档映射 h1/h2/h3
    sizes = sorted({round(ln["font"], 1) for ln in titles}, reverse=True)
    level_map = {size: min(i + 1, 3) for i, size in enumerate(sizes)}

    # 5. 构建章节单元：标题入栈弹栈维护层级路径，标题作为单元正文开头
    docs: list[Document] = []
    stack: list[tuple[int, str]] = []  # [(level, title)]
    buf: list[tuple[str, int]] = []  # [(text, page)]

    def flush():
        if not buf:
            return
        meta = {"page_start": buf[0][1], "page_end": buf[-1][1]}
        if stack:
            meta["section_path"] = " > ".join(t for _, t in stack)
        docs.append(Document(page_content="\n".join(t for t, _ in buf), metadata=meta))
        buf.clear()

    for ln in lines:
        if _is_title(ln, body_font):
            flush()  # 先落盘当前章节内容（归属旧栈）
            level = level_map[round(ln["font"], 1)]
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, ln["text"]))
            buf.append((ln["text"], ln["page"]))
        else:
            buf.append((ln["text"], ln["page"]))
    flush()
    return docs


def _is_title(line: dict, body_font: float) -> bool:
    '''标题判定：字号 >= 正文 1.3 倍或（加粗且 >= 正文），且行长受限、不以句读结尾'''
    text = line["text"]
    if len(text) > _TITLE_MAX_LEN:
        return False
    if text.endswith(_SENTENCE_ENDINGS):
        return False
    if line["font"] >= body_font * 1.3:
        return True
    if line["bold"] and line["font"] >= body_font:
        return True
    return False


def _pages_fallback(pdf) -> list[Document]:
    '''兜底：无任何结构信息时按页切块'''
    docs = []
    for p in range(pdf.page_count):
        text = pdf[p].get_text("text").strip()
        if text:
            docs.append(Document(page_content=text, metadata={"page_start": p + 1, "page_end": p + 1}))
    return docs
