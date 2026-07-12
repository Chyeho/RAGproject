'''
基于streamlit库开发web文件上传服务网页
'''
# 导包
import streamlit as st
from knowledge_base import KnowledgeBaseService
import time

# 标题
st.title("知识库更新服务")

# 上传文件
uploader_file = st.file_uploader(
    label="请上传文件",
    type=["txt"],
    accept_multiple_files=False   # False表示只支持一个文件的上传
)

# 通过session_state字典保存状态
if "service" not in st.session_state:
    st.session_state["service"] = KnowledgeBaseService()

# 展示文件
if uploader_file is not None:
    # 获取文件基本信息
    file_name = uploader_file.name
    file_type = uploader_file.type
    file_size = uploader_file.size / 1024

    # 展示文件信息在网页中
    st.subheader(f"文件名：{file_name}")            #用于创建相对较小的标题
    st.write(f"格式：{file_type} | 大小：{file_size:.2f} KB")

    # 获取文件内容 get_value -> bytes -> decode('utf-8')
    text = uploader_file.getvalue().decode('utf-8')

    # 在spinner内的代码执行过程中，会有一个表示加载的圈转动
    with st.spinner("载入知识库中。。。"):
        time.sleep(1)
        res = st.session_state["service"].upload_by_str(text,file_name)
        st.write(res)