'''文件处理工具'''
import os
import hashlib

from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path
from app.utils.config_handler import chroma_conf

# langchain
from langchain_core.documents import Document
from langchain_community.document_loaders import PyPDFLoader,TextLoader


def pdf_loader(file_path:str,password = None) -> list[Document]:
    '''加载pdf文件'''
    return PyPDFLoader(file_path,password).load()

def txt_loader(file_path:str) -> list[Document]:
    '''加载txt文件'''
    return TextLoader(file_path,encoding = "utf-8").load()

def get_file_md5_hex(file_path:str):
    '''获取文件的md5的十六进制字符串'''
    # 文件不存在
    if not os.path.exists(file_path):
        logger.error(f"[md5计算]文件{file_path}不存在")
        return

    # 路径不是文件
    if not os.path.isfile(file_path):
        logger.error(f"[md5计算]路径{file_path}不是文件")

    # 计算文件md5
    md5_obj = hashlib.md5()
    chunk_size = 4096
    try:
        # 二进制读取文件
        with open(file_path,"rb") as f:
            while chunk:= f.read(chunk_size):
                md5_obj.update(chunk)
        md5_hex = md5_obj.hexdigest()
        return md5_hex
    except Exception as e:
        logger.error(f"[md5计算]文件{file_path}计算md5失败，错误信息：{str(e)}")
        return None

def check_md5_hex(md5_for_check:str):
    """用md5检查文件是否已经存储
    Args:
        md5_for_check (str): 需要检查的文件md5
    Returns:
        _boolean_: 返回False说明没存，反之则已存
    """
    if not os.path.exists(get_abs_path(chroma_conf["md5_hex_store"])): # 当存储md5值的文件不存在
        open(get_abs_path(chroma_conf["md5_hex_store"]),"w",encoding="utf-8").close()
        return False
    else: # 检查
        with open(get_abs_path(chroma_conf["md5_hex_store"]),"r",encoding="utf-8") as f:
            for line in f.readlines():
                line = line.strip()
                if line == md5_for_check:
                    return True
                return False

def save_md5_hex(md5_for_check:str):
    """存放新的md5值
    Args:
        md5_for_check (str): 需要存放的md值
    """
    with open(get_abs_path(chroma_conf["md5_hex_store"]),"a",encoding="utf-8") as f:
        f.write(md5_for_check + '\n')

def get_file_documents(read_path:str):
    """
    返回包含传入文件内容的文档对象列表。
    Args:
        read_path (str): 文件路径

    Returns:
        _type_: 返回对应的文件加载器
    """
    if read_path.endswith("txt"):
        return txt_loader(read_path)
    
    if read_path.endswith("pdf"):
        return pdf_loader(read_path)
    
    return []


def listdir_with_allowed_type(path:str,allowed_type:tuple[str]):
    '''获取文件夹内的文件列表（附带允许的文件后缀）'''
    files = []

    # 路径不是文件夹
    if not os.path.isdir(path):
        logger.error(f"[listed_with_allowed_type]{path}不是文件夹")
        return allowed_type
    
    # 获取文件列表
    for f in os.listdir(path):
        if f.endswith(allowed_type):
            files.append(os.path.join(path,f))
    return tuple(files)


        