'''文件处理工具'''
import os
import hashlib

from app.utils.logger_handler import logger
from app.utils.path_tool import get_abs_path


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


        