'''
知识库更新

md5：md5是一种广泛使用的密码散列函数，可以产生一个16字节的散列值（即哈希值），用于加密存储
'''
import os
import config_data as config                                          # 配置文件
import hashlib                                                        # 自动计算md5值
from langchain_chroma import Chroma                                   # 向量数据库
from langchain_community.embeddings import DashScopeEmbeddings        # 文本嵌入模型
from langchain_text_splitters import RecursiveCharacterTextSplitter   # 递归文本切割器
from datetime import datetime

def check_md5(md5_str:str):
    '''
    检查传入的md5字符串是否已经被处理过了
    False：未处理过；True：已经处理过
    '''
    if not os.path.exists(config.md5_path):
        # 进入if代码块说明不存在这个文件，那更不可能被处理过，就需要创建文件
        open(config.md5_path,"w",encoding='utf-8')     # 创建文件
        return False
    else:
        # 存在文件，就进行判断
        for line in open(config.md5_path,"r",encoding='utf-8').readlines():
            line = line.strip()                        # 处理字符串前后的空白字符
            if line == md5_str:
                return True                            # 已处理过
        return False

def save_md5(md5_str:str):
    '''将传入的md5字符串，记录到文件内保存'''
    with open(config.md5_path,"a",encoding='utf-8') as f:
        f.write(md5_str + '\n')

def get_string_md5(input_str:str,encoding='utf-8'):
    '''将传入的字符串转换为md5字符串'''
    
    # 将字符串转换为bytes字节数组
    str_bytes = input_str.encode(encoding=encoding)

    # 创建md5对象
    md5_obj = hashlib.md5()                            # 得到md5对象
    md5_obj.update(str_bytes)                          # 更新内容，传入即将要转换的字节数组
    md5_hex = md5_obj.hexdigest()                      # 得到md5的十六进制字符串

    return md5_hex

class KnowledgeBaseService(object):
    def __init__(self):
        self.chroma = Chroma(
            collection_name=config.collection_name,
            embedding_function=DashScopeEmbeddings(model="text-embedding-v4"),
            persist_directory=config.persist_directory,
        )           # 向量存储的实例对象
        self.spliter = RecursiveCharacterTextSplitter(
            chunk_size = config.chunk_size,
            chunk_overlap = config.chunk_overlap,
            separators = config.separators,
            length_function = len,
        )          # 文本分割器的对象
        
    def upload_by_str(self,data,filename):
        '''将传入的字符串，进行向量化，存入向量数据库'''
        # 先得到传入字符串data的md5值
        md5_hex = get_string_md5(data)

        # 检查字符串已处理
        if check_md5(md5_hex):
            return "[跳过]内容已经存在知识库中"
        
        # 查看文档是否需要进行分割
        if len(data) > config.max_split_char_number:
            knowledge_chunks:list[str] = self.spliter.split_text(data)
        else:
            knowledge_chunks = [data]
        
        # 定义数据来源
        metadata = {
            "source":filename,
            "create_time":datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "operator":"c",
        }

        # 添加数据到向量存储库
        self.chroma.add_texts(
            knowledge_chunks,
            metadatas=[metadata for _ in knowledge_chunks],
        )

        # 保存到md5文件
        save_md5(md5_hex)

        return "[成功]内容已经成功载入向量库"

# # 测试代码
# if __name__ == '__main__':
#     service = KnowledgeBaseService()
#     r = service.upload_by_str("winwinwin","textfile")
#     print(r)

   