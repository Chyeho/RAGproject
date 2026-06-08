'''
用户聊天界面
'''
import streamlit as st
import time
from oldProject.rag import RagService
import config_data as config

# 标题
st.title("智能聊天客服")

# 分割线
st.divider()

# 保存状态：历史消息,RagService对象
if "message" not in st.session_state:
    st.session_state["message"] = [{"role":"assistant","content":"你好，有什么可以帮你的吗？"}]

if "rag" not in st.session_state:
    st.session_state["rag"] = RagService()

for message in st.session_state["message"]:
    st.chat_message(message["role"]).write(message["content"])

# 在页面最下方提供用户输入栏
prompt = st.chat_input()

if prompt:
    st.chat_message("user").write(prompt)
    st.session_state["message"].append({"role":"user","content":prompt})

    ai_res_list = []
    with st.spinner("AI思考中。。。"):
        # 返回流失输出的迭代器
        res_stream = st.session_state["rag"].chain.stream({"input":prompt},config.session_config)
        
        # 流式输出的迭代器转换成list，方便转换成字符串并存入历史记录
        def capture(generator,cache_list):
            for chunk in generator:
                cache_list.append(chunk)
                yield chunk
        
        st.chat_message("assistant").write_stream(capture(res_stream,ai_res_list))
        st.session_state["message"].append({"role":"assistant","content":"".join(ai_res_list)})  # join(ai_res_list)把列表拼接成字符串