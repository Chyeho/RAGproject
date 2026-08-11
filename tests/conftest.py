# -*- coding: utf-8 -*-
"""pytest 共享 fixtures — 将 backend 加入 sys.path 并 mock 外部 API"""
import os
import sys
import json
import tempfile
from pathlib import Path

import pytest

# ========================================
# 将 backend/ 目录加入 sys.path，确保 from app.xxx import ... 正常工作
# ========================================
BACKEND_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "backend")
)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


# ========================================
# DashScope embedding mock fixtures
# ========================================
@pytest.fixture
def mock_dashscope_embeddings():
    """mock DashScope TextEmbedding.call，返回假向量"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # 先创建 app 包内的必要目录结构
        yield tmpdir


@pytest.fixture
def sample_chat_history_dir():
    """创建一个临时聊天历史目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_md5_file():
    """临时 md5 标记文件"""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="md5_test_")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_txt_file():
    """创建一个临时 txt 文件，写入测试内容"""
    fd, path = tempfile.mkstemp(suffix=".txt", prefix="test_")
    os.close(fd)
    content = "这是一段测试文本内容，用于单元测试。\n\n第二段内容，包含更多文字。"
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def temp_pdf_file():
    """创建一个临时 pdf 文件路径（不保证是合法 PDF，仅用于路径测试）"""
    fd, path = tempfile.mkstemp(suffix=".pdf", prefix="test_")
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)
