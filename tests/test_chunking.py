# -*- coding: utf-8 -*-
"""格式感知解析与智能分块（P1）单元测试

全部离线运行：pdf/docx/xlsx 样例文件分别用 pymupdf / python-docx / openpyxl 动态生成
（PDF 内置字体不含中文，测试文本统一用 ASCII）。
"""
import docx
import pymupdf
import pytest
from openpyxl import Workbook

from app.utils.config_handler import qdrant_conf
from app.service.rag.chunking import apply_smart_rules, chunk_file
from app.service.rag.chunking.docx_chunker import chunk_docx
from app.service.rag.chunking.excel_chunker import chunk_excel
from app.service.rag.chunking.markdown_chunker import chunk_markdown
from app.service.rag.chunking.pdf_chunker import chunk_pdf
from app.service.rag.chunking.text_chunker import chunk_text


# ========================================
# 样例文件生成
# ========================================
def _make_txt(path, content):
    path.write_text(content, encoding="utf-8")


MD_CONTENT = """# 标题一

前言内容。

## 小节甲

小节甲内容。

### 子小节

子小节内容。

## 小节乙

小节乙内容。
"""


def _make_md(path):
    path.write_text(MD_CONTENT, encoding="utf-8")


def _make_docx(path):
    d = docx.Document()
    d.add_heading("Chapter One", level=1)
    d.add_paragraph("intro text")
    d.add_heading("Section A", level=2)
    d.add_paragraph("detail text")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "name"
    table.cell(0, 1).text = "qty"
    table.cell(1, 0).text = "Alice"
    table.cell(1, 1).text = "3"
    d.add_paragraph("Tail paragraph")
    d.save(str(path))


def _make_xlsx(path, header_only_sheet=True):
    wb = Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["name", "qty"])
    ws.append(["Alice", 3])
    ws.append(["Bob", None])  # 空单元格应被过滤
    ws.append(["Carol", 5])
    ws.append(["Dave", 2])
    ws.append(["Eve", 9])
    if header_only_sheet:
        ws2 = wb.create_sheet("Empty")
        ws2.append(["a", "b"])
    wb.save(str(path))


def _make_pdf_toc(path):
    """3 页 PDF + 章节书签：General/Usage/Others"""
    with pymupdf.open() as pdf:
        for i in range(3):
            page = pdf.new_page()
            page.insert_textbox(
                pymupdf.Rect(72, 72, 523, 400),
                f"Body of page {i + 1} " + "x" * 100,
                fontsize=11,
            )
        pdf.set_toc([[1, "General", 1], [1, "Usage", 2], [1, "Others", 3]])
        pdf.save(str(path))


def _make_pdf_font_titles(path):
    """单页 PDF 无书签：两个大字号标题 + 正文字号内容"""
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 523, 120), "Alpha Section", fontsize=18)
        page.insert_textbox(pymupdf.Rect(72, 130, 523, 390), "body line one " * 5, fontsize=10)
        page.insert_textbox(pymupdf.Rect(72, 410, 523, 460), "Beta Section", fontsize=18)
        page.insert_textbox(pymupdf.Rect(72, 470, 523, 700), "body line two " * 5, fontsize=10)
        pdf.save(str(path))


def _make_pdf_plain(path):
    """单页 PDF 无书签、字号统一：走按页兜底"""
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_textbox(pymupdf.Rect(72, 72, 523, 400), "plain body text " * 5, fontsize=10)
        pdf.save(str(path))


# ========================================
# chunk_file 路由
# ========================================
class TestChunkFileRouting:
    def test_unsupported_extension_raises(self, tmp_path):
        with pytest.raises(ValueError, match="不支持的文件格式"):
            chunk_file(str(tmp_path / "a.xyz"))

    def test_md_route_applies_embedding_enhancement(self, tmp_path):
        """md 走完整链路：智能规则 + 嵌入增强（正文前拼接章节路径）"""
        f = tmp_path / "a.md"
        _make_md(f)
        docs = chunk_file(str(f))
        assert len(docs) > 0
        # h1 后的前言归属 h1 节，带章节的块有 "[章节路径]\n" 前缀
        assert docs[0].metadata.get("section_path") == "标题一"
        assert docs[0].page_content.startswith("[标题一]\n")
        assert "前言内容" in docs[0].page_content
        assert any(d.page_content.startswith("[标题一 > 小节甲]\n") for d in docs)

    def test_txt_route(self, tmp_path):
        f = tmp_path / "a.txt"
        _make_txt(f, "第一段内容。\n\n第二段内容。")
        docs = chunk_file(str(f))
        assert len(docs) >= 1

    def test_xlsx_route(self, tmp_path):
        f = tmp_path / "a.xlsx"
        _make_xlsx(f, header_only_sheet=False)
        docs = chunk_file(str(f))
        assert len(docs) >= 1
        assert all("sheet_name" in d.metadata for d in docs)


# ========================================
# 智能切分规则
# ========================================
class TestApplySmartRules:
    def test_merges_small_sibling_sections(self, monkeypatch):
        """同父章节的相邻小单元合并，章节路径退化为父路径"""
        monkeypatch.setitem(qdrant_conf, "max_chunk_size", 800)
        monkeypatch.setitem(qdrant_conf, "min_chunk_size", 100)
        from langchain_core.documents import Document

        docs = [
            Document(page_content="甲" * 50, metadata={"section_path": "章一 > 节A"}),
            Document(page_content="乙" * 50, metadata={"section_path": "章一 > 节B"}),
        ]
        result = apply_smart_rules(docs)
        assert len(result) == 1
        assert result[0].metadata["section_path"] == "章一"
        assert "甲" * 50 in result[0].page_content
        assert "乙" * 50 in result[0].page_content

    def test_no_merge_across_parents(self, monkeypatch):
        monkeypatch.setitem(qdrant_conf, "max_chunk_size", 800)
        monkeypatch.setitem(qdrant_conf, "min_chunk_size", 100)
        from langchain_core.documents import Document

        docs = [
            Document(page_content="甲" * 50, metadata={"section_path": "章一 > 节A"}),
            Document(page_content="乙" * 50, metadata={"section_path": "章二 > 节A"}),
        ]
        result = apply_smart_rules(docs)
        assert len(result) == 2

    def test_no_merge_when_both_large(self, monkeypatch):
        """两单元均 >= min_chunk_size 时不合并"""
        monkeypatch.setitem(qdrant_conf, "max_chunk_size", 800)
        monkeypatch.setitem(qdrant_conf, "min_chunk_size", 100)
        from langchain_core.documents import Document

        docs = [
            Document(page_content="甲" * 150, metadata={"section_path": "章一 > 节A"}),
            Document(page_content="乙" * 150, metadata={"section_path": "章一 > 节B"}),
        ]
        result = apply_smart_rules(docs)
        assert len(result) == 2

    def test_splits_oversized_at_paragraph_boundary(self, monkeypatch):
        """超长单元（> max_chunk_size）按段落边界再分并标记 split_index/split_total"""
        monkeypatch.setitem(qdrant_conf, "max_chunk_size", 800)
        monkeypatch.setitem(qdrant_conf, "min_chunk_size", 100)
        monkeypatch.setitem(qdrant_conf, "chunk_overlap", 50)
        from langchain_core.documents import Document

        paragraphs = "\n\n".join("段" * 350 for _ in range(3))  # 共 1052 字
        docs = [Document(page_content=paragraphs, metadata={"section_path": "章一"})]
        result = apply_smart_rules(docs)
        assert len(result) == 2
        assert all(len(d.page_content) <= 800 for d in result)
        assert {d.metadata["split_index"] for d in result} == {0, 1}
        assert all(d.metadata["split_total"] == 2 for d in result)


# ========================================
# txt 分块器
# ========================================
class TestTextChunker:
    def test_packs_paragraphs_to_chunk_size(self, tmp_path, monkeypatch):
        """相邻段落贪心打包至 chunk_size，只在段落边界切分"""
        monkeypatch.setitem(qdrant_conf, "chunk_size", 100)
        f = tmp_path / "a.txt"
        _make_txt(f, "\n\n".join(c * 40 for c in "甲乙丙丁戊"))
        docs = chunk_text(str(f))
        assert len(docs) == 3  # 40+40=80<=100，三个段落一组
        assert docs[0].metadata["paragraph_range"] == "1~2"
        assert docs[1].metadata["paragraph_range"] == "3~4"
        assert docs[2].metadata["paragraph_range"] == "5~5"
        assert docs[0].page_content == "甲" * 40 + "\n" + "乙" * 40

    def test_oversized_paragraph_split(self, tmp_path, monkeypatch):
        """超长段落按句级分隔符再分，每片不超过 chunk_size"""
        monkeypatch.setitem(qdrant_conf, "chunk_size", 500)
        f = tmp_path / "a.txt"
        _make_txt(f, ("字" * 49 + "。") * 20)  # 1000 字无空行
        docs = chunk_text(str(f))
        assert len(docs) >= 2
        assert all(len(d.page_content) <= 500 for d in docs)

    def test_empty_file_returns_empty(self, tmp_path):
        f = tmp_path / "a.txt"
        _make_txt(f, "")
        assert chunk_text(str(f)) == []

    def test_single_newline_fallback(self, tmp_path):
        """整篇无空行但有单换行时，退化为按单换行分段"""
        f = tmp_path / "a.txt"
        _make_txt(f, "第一行\n第二行")
        docs = chunk_text(str(f))
        assert len(docs) == 1
        assert "第一行" in docs[0].page_content
        assert "第二行" in docs[0].page_content


# ========================================
# markdown 分块器
# ========================================
class TestMarkdownChunker:
    def test_section_paths_and_headers_kept(self, tmp_path):
        f = tmp_path / "a.md"
        _make_md(f)
        docs = chunk_markdown(str(f))
        paths = [d.metadata.get("section_path") for d in docs]
        # h1 标题后的正文归属 h1 节，不存在独立的无标题前言块
        assert paths == [
            "标题一",
            "标题一 > 小节甲",
            "标题一 > 小节甲 > 子小节",
            "标题一 > 小节乙",
        ]
        # 标题保留在正文（strip_headers=False）
        assert docs[2].page_content.startswith("### 子小节")

    def test_preamble_belongs_to_h1_section(self, tmp_path):
        """h1 标题后的前言内容归属 h1 节，正文保留标题原文"""
        f = tmp_path / "a.md"
        _make_md(f)
        docs = chunk_markdown(str(f))
        assert docs[0].metadata["section_path"] == "标题一"
        assert "前言内容" in docs[0].page_content
        assert "# 标题一" in docs[0].page_content


# ========================================
# excel 分块器
# ========================================
class TestExcelChunker:
    def test_groups_rows_with_header(self, tmp_path, monkeypatch):
        """按 excel_rows_per_chunk 分组，每组携带 Sheet 信息与表头，数据行带原始行号"""
        monkeypatch.setitem(qdrant_conf, "excel_rows_per_chunk", 2)
        f = tmp_path / "a.xlsx"
        _make_xlsx(f, header_only_sheet=False)
        docs = [d for d in chunk_excel(str(f)) if d.metadata["sheet_name"] == "Data"]
        assert len(docs) == 3  # 5 个数据行按 2 行一组
        assert docs[0].metadata["row_start"] == 2
        assert docs[0].metadata["row_end"] == 3
        assert docs[2].metadata["row_start"] == 6
        assert docs[2].metadata["row_end"] == 6
        assert docs[0].page_content.startswith("【Sheet：Data｜第2~3行】")
        assert "表头：name | qty" in docs[0].page_content
        assert "第2行 name：Alice；qty：3" in docs[0].page_content

    def test_skips_empty_cells(self, tmp_path, monkeypatch):
        monkeypatch.setitem(qdrant_conf, "excel_rows_per_chunk", 5)
        f = tmp_path / "a.xlsx"
        _make_xlsx(f, header_only_sheet=False)
        docs = [d for d in chunk_excel(str(f)) if d.metadata["sheet_name"] == "Data"]
        assert len(docs) == 1
        assert "第3行 name：Bob" in docs[0].page_content
        assert "qty" not in docs[0].page_content.split("第3行")[1].split("第4行")[0]

    def test_header_only_sheet(self, tmp_path):
        f = tmp_path / "a.xlsx"
        _make_xlsx(f, header_only_sheet=True)
        docs = [d for d in chunk_excel(str(f)) if d.metadata["sheet_name"] == "Empty"]
        assert len(docs) == 1
        assert docs[0].metadata["row_start"] == docs[0].metadata["row_end"] == 1
        assert "表头：a | b" in docs[0].page_content


# ========================================
# docx 分块器
# ========================================
class TestDocxChunker:
    def test_heading_sections_and_table(self, tmp_path):
        f = tmp_path / "a.docx"
        _make_docx(f)
        docs = chunk_docx(str(f))
        assert len(docs) == 4
        assert docs[0].metadata["section_path"] == "Chapter One"
        assert "intro text" in docs[0].page_content
        assert docs[1].metadata["section_path"] == "Chapter One > Section A"
        # 表格独立成块并序列化
        assert docs[2].metadata["table_index"] == 1
        assert docs[2].page_content.startswith("表格字段：name | qty")
        assert "name：Alice；qty：3" in docs[2].page_content
        assert docs[3].page_content == "Tail paragraph"

    def test_invalid_docx_raises_value_error(self, tmp_path):
        f = tmp_path / "bad.docx"
        f.write_bytes(b"not a real docx file")
        with pytest.raises(ValueError, match="旧版 .doc"):
            chunk_docx(str(f))


# ========================================
# pdf 分块器（三级策略）
# ========================================
class TestPdfChunker:
    def test_sections_from_toc(self, tmp_path):
        f = tmp_path / "toc.pdf"
        _make_pdf_toc(f)
        docs = chunk_pdf(str(f))
        assert [d.metadata["section_path"] for d in docs] == ["General", "Usage", "Others"]
        assert [(d.metadata["page_start"], d.metadata["page_end"]) for d in docs] == [
            (1, 1), (2, 2), (3, 3),
        ]
        assert "Body of page 1" in docs[0].page_content

    def test_sections_from_font_heuristic(self, tmp_path):
        f = tmp_path / "font.pdf"
        _make_pdf_font_titles(f)
        docs = chunk_pdf(str(f))
        assert len(docs) == 2
        assert [d.metadata["section_path"] for d in docs] == ["Alpha Section", "Beta Section"]
        assert docs[0].metadata["page_start"] == docs[0].metadata["page_end"] == 1
        assert "body line one" in docs[0].page_content

    def test_pages_fallback(self, tmp_path):
        f = tmp_path / "plain.pdf"
        _make_pdf_plain(f)
        docs = chunk_pdf(str(f))
        assert len(docs) == 1
        assert docs[0].metadata == {"page_start": 1, "page_end": 1}
        assert "plain body text" in docs[0].page_content
