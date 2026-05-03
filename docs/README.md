### 项目简介

**项目背景**

​	本次项目以“某东商品衣服”为例，以衣服属性构建本地知识。使用者可以自由更新本地知识，用户问题的答案也是基于本地知识生成的。

**基本架构**

```plaintext
project_root/
├── chat_history/
├── chroma_db/
├── data/
│   ├── 尺码推荐.txt
│   ├── 洗涤养护.txt
│   └── 颜色选择.txt
├── app_file_upload.py
├── app_qa.py
├── config_data.py
├── file_history_store.py
├── knowledge_base.py
├── rag.py
└── vector_stores.py
```

**快速开始**

1.创建并激活并激活虚拟环境(Windows)[可选]

```powershell
# 1.创建虚拟环境
python -m venv .venv

# 2.激活虚拟环境
.venv/Scripts/activate
```

2.安装`pyproject.toml`的所有依赖

```powershell
pip install -e .
```

3.退出虚拟环境(Windows)[可选]

```powershell
deactivate
```

4.在线流程代码运行

```powershell
streamlit run app_qa.py
```

5.离线流程代码运行

```python
streamlit run file_app_upload.py
```

**项目期望**

依据课程的代码架构，做企业级迭代