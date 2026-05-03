# 项目开发历史记录

## 一、初期demo阶段

### 1.开发离线流程

#### 文件架构

- `file_app_upload.py`：web文件上传服务，作为离线时的知识库更新的主程序
- `knowladge_base.py`：知识库更新服务，通过md5进行文档内容查重
- `config_data.py`：配置文件，内容为配置参数

#### 主要知识点

1. `streamlit`库快速构建网页
   - `st.title`：网页标题
   - `st.file_uploader`：上传文件的入口
   - `st.session_state`：由于`streamlit`的重置特性，需要通过这个字典来保存状态
   - `st.subheader`：创建相对较小的标题
   - `st.write`：写入文本到网页
   - `with st.spinner(文本):`：该段代码下的代码块在执行过程中会有转圈动画
2. `md5`保存数据和去重
   - md5是一种广泛使用的密码散列函数，可以产生一个16字节的散列值（即哈希值），用于加密存储
   - 因为数据只要有一点不同，`md5`都会不同，所以可以进行数据去重
   - `import hashlib`：自动计算`md5`值的库
   - `hashlib.md5()`：得到`md5`对象
   - `md5_obj.update(str_bytes)`：更新内容，传入即将要转换的字节数组
   - `md5_obj.hexdigest()`：得到`md5`的十六进制字符串
3. `os`
   - `Python`中用于处理文件和目录的库
   - `os.path.exists(file_path)`：判断文件路径是否存在
4. `Chroma`：轻量级向量数据库
5. `embeddings`：文本嵌入模型，可以用`DashScopeEmbeddings(model="text-embedding-v4")`模型
6. `RecursiveCharacterTextSplitter`：递归文本分割器

#### 报错和解决

**报错1：protobuf（谷歌的协议缓冲区）版本不兼容**

-  `protobuf` 版本过高（≥4.x），而 `chromadb`/`langchain-chroma` 依赖的 `opentelemetry` 等库在高版本 `protobuf` 下会触发 `Descriptor`（描述符）创建限制；

- 高版本 `protobuf` 对 `_pb2.py` 生成文件的兼容性做了调整，直接创建` Descriptor` 会被禁止，从而抛出该 `TypeError`

- 简单来说：`chromadb` 依赖的组件与高版本 `protobuf` 存在兼容性冲突

- 解决方案：将 `protobuf`降级到3.20.x 及以下版本

  - ```powershell
    # 卸载现有版本
    pip uninstall -y protobuf
    
    # 安装兼容版本（3.20.3 是稳定兼容版）
    pip install protobuf==3.20.3
    ```

### 2.开发在线流程

#### 文件架构

- `vector_stores.py`：向量检索服务。获取检索器，方便后续入链
- `rag.py`：RAG业务核心代码。构建链
- `file_history_store.py`：历史消息记录服务
- `app_qa.py`：用户聊天界面

#### 主要知识点

**rag.py**

1. 核心知识点：==注意每个组件的输入输出是什么样的，构建链的时候需要兼容每个组件之间的输入输出==

2. `as_retriever()`：获取检索类的方法，用于从向量存储中查找和检索最相关的文档

3. `ChatPromptTemplate()`：聊天模型的提示词模板类

4. `MessagesPlaceholder`：通过占位符的形式，动态给提示词模板注入内容

5. `RunnablePassthrough()`：截获一份`input`的内容，方便构建链中提示词模板的字典输入中的"input"的内容

6. `RunnableWithMessageHistory()`：自动管理对话历史的包装器，可以构建具有历史记录管理功能的增强链

7. `session_config`：每位用户的历史记录的配置信息

   - ```python
     # 参考格式：user_001为一位用户
     session_config = {
         "configurable":{
             "session_id":"user_001",
         }
     }
     ```

**file_history_store.py**

1. `os`
   - `os.path.join()`：文件路径拼接
   - `os.makedirs()`：文件夹不存在就创建，存在就不报错，继续执行
   - `os.path.dirname()`：提取文件路径的文件夹路径
2. `message_to_dict,messages_from_dict`消息列表和字典地转换
3. `json`：用于`json`数据地编码和解码
   - `json.dump(内容,文件)`：将指定内容转成`json`格式存到文件中
   - `json.load(文件)`：从文件中加载`json`数据
4. `@property`：将类中地方法转换为成员属性
5. `BaseChatMessageHistory`：存储聊天消息地的基类
6. `try-catch语句`：由于文件操作容易报错，可以加上这个语句

**app_qa.py**

1. `st.divider()`：分割线

2. `st.chat_input()`：用户输入栏

3. `st.chat_message()`：接收历史会话，构建聊天界面

4. `streamlit`网页流失输出的实现

   - 核心代码：

   - ```python
     # 返回流式输出的生成器
     res_stream = st.session_state["rag"].chain.stream({"input":prompt},config.session_config)
             
     # 流式输出的生成器转换成list，方便转换成字符串并存入历史记录
     def capture(generator,cache_list):
         for chunk in generator:
             cache_list.append(chunk)
             yield chunk
             
     st.chat_message("assistant").write_stream(capture(res_stream,ai_res_list))
     st.session_state["message"].append({"role":"assistant","content":"".join(ai_res_list)})
     ```

     - `chain.stream()`会返回生成器(生成器是被遍历才会每次小段返回内容，并且每次遍历都会让数据消失，所以不能直接将其存入历史消息)
     - `capture()`：每次遍历把一小段数据进行存储(`ai_res_list`)，并返回一小段进行前端显示(`yield`)
     - `yield`：会让函数暂时停止并返回值，下次调用时从上次暂停的地方继续，实现流式输出
     - `write_stream()`： 是 `streamlit` 专门用来渲染生成器的方法，每收到一个 `chunk`，就立刻渲染到网页上
     - `join(ai_res_list)`：拼接字符串列表为字符串，存进历史消息

#### 报错和解决

**报错1：类型识别错误**

- 位置：`rag.py`的`def format_document(docs:list[Document]):`

- 报错：

  - ```powershell
    TypeError: RagService.format_document() takes 1 positional argument but 2 were given
    ```

- 原因：Python识别不出docs的数据类型，导致出现传参问题

- 解决方案：

  1. 给docs参数加上list[Document]类型，即`docs:list[Document]`
  2. 直接用`RunnablePassthrough`的`assign`方法，输出原格式的字典，不用自己写`format`