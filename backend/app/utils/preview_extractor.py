'''文档预览文本提取

预览接口不能把文件按 UTF-8 文本直接读：pdf / docx / xlsx 都是二进制容器，
强行按文本解码只会得到 "%PDF-1.4 / 1 0 obj / xref" 这类乱码。

这里按扩展名走对应解析库提取正文，并且只取前 MAX_CHARS 个字符就停，
避免大文件（几十 MB 的 PDF）把接口拖住。
'''
import os

from app.utils.logger_handler import logger

# 预览返回的最大字符数（与前端展示上限保持一致）
MAX_CHARS = 10000

# 纯文本类：直接读文件
TEXT_EXTS = {"txt", "md", "markdown"}
# 需要解析的二进制格式
PARSED_EXTS = {"pdf", "docx", "xlsx"}
# 支持预览的全部格式
SUPPORTED_EXTS = TEXT_EXTS | PARSED_EXTS


def extract_preview_text(file_path: str, max_chars: int = MAX_CHARS) -> tuple[str, str]:
    '''提取用于预览的纯文本

    Returns:
        (正文, 提示文案)。提示文案为空字符串表示内容完整可读；
        正文为空且提示非空时，前端应展示提示而不是空白。
    '''
    ext = os.path.splitext(file_path)[1].lower().lstrip(".")

    try:
        if ext in TEXT_EXTS:
            text, truncated = _read_text(file_path, max_chars)
        elif ext == "pdf":
            text, truncated = _read_pdf(file_path, max_chars)
        elif ext == "docx":
            text, truncated = _read_docx(file_path, max_chars)
        elif ext == "xlsx":
            text, truncated = _read_xlsx(file_path, max_chars)
        elif ext == "doc":
            # 老版 Word（OLE 二进制）python-docx 读不了，只能提示下载
            return "", "旧版 .doc 格式不支持在线预览，请下载后查看"
        else:
            return "", f"暂不支持 .{ext or '未知'} 格式在线预览，请下载后查看"
    except Exception as e:
        logger.warning(f"[文档预览]解析 {os.path.basename(file_path)} 失败：{e}")
        return "", "预览解析失败，请下载后查看"

    text = (text or "").strip()
    if not text:
        if ext == "pdf":
            return "", "未提取到文本内容（可能是扫描件/图片型 PDF），请下载后查看"
        return "", "该文档未提取到文本内容，请下载后查看"

    return text, (f"内容较长，仅展示前 {max_chars} 字符" if truncated else "")


# ---------------- 各格式读取实现 ----------------
def _read_text(file_path: str, limit: int) -> tuple[str, bool]:
    '''txt / md：按 UTF-8 读，乱码率过高时回退 GB18030'''
    raw = ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            raw = f.read(limit * 4)
    except OSError as e:
        logger.warning(f"[文档预览]读取文本文件失败：{e}")
        return "", False

    if raw and raw.count("\ufffd") > len(raw) * 0.05:
        try:
            with open(file_path, "r", encoding="gb18030", errors="replace") as f:
                raw = f.read(limit * 4)
        except OSError:
            pass
    return raw[:limit], len(raw) > limit


def _read_pdf(file_path: str, limit: int) -> tuple[str, bool]:
    '''PDF：逐页取文本层，够字数就停（扫描件没有文本层，会返回空串）'''
    import pymupdf

    parts: list[str] = []
    total = 0
    with pymupdf.open(file_path) as pdf:
        for page in pdf:
            page_text = page.get_text()
            if not page_text or not page_text.strip():
                continue
            parts.append(page_text.strip())
            total += len(page_text)
            if total >= limit:
                break
    return "\n\n".join(parts)[:limit], total > limit


def _read_docx(file_path: str, limit: int) -> tuple[str, bool]:
    '''docx：段落 + 表格（表格按行拼接，单元格用 | 分隔）'''
    import docx

    document = docx.Document(file_path)
    parts: list[str] = []
    total = 0
    for para in document.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        parts.append(text)
        total += len(text)
        if total >= limit:
            return "\n".join(parts)[:limit], True

    # 正文不够时再补表格内容
    for table in document.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if not any(cells):
                continue
            line = " | ".join(cells)
            parts.append(line)
            total += len(line)
            if total >= limit:
                return "\n".join(parts)[:limit], True
    return "\n".join(parts)[:limit], total > limit


def _read_xlsx(file_path: str, limit: int) -> tuple[str, bool]:
    '''xlsx：按工作表输出，每行单元格用制表符分隔'''
    from openpyxl import load_workbook

    parts: list[str] = []
    total = 0
    workbook = load_workbook(file_path, read_only=True, data_only=True)
    try:
        for sheet in workbook.worksheets:
            header = f"【{sheet.title}】"
            parts.append(header)
            total += len(header)
            for row in sheet.iter_rows(values_only=True):
                cells = ["" if v is None else str(v) for v in row]
                if not any(c.strip() for c in cells):
                    continue
                line = "\t".join(cells).rstrip()
                parts.append(line)
                total += len(line)
                if total >= limit:
                    return "\n".join(parts)[:limit], True
    finally:
        workbook.close()
    return "\n".join(parts)[:limit], total > limit
