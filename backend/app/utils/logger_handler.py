'''
日志管理工具
'''
import logging
from app.utils.path_tool import get_abs_path
import os
from datetime import datetime

# 获取日志保存的根目录
LOG_ROOT = get_abs_path("logs")

# 确保根目录存在
os.makedirs(LOG_ROOT,exist_ok=True)

# 日志格式配置
DEFAULT_LOG_FORMAT = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
)

def get_logger(
        name:str          = "agent",
        console_level:int = logging.INFO,
        file_level:int    = logging.DEBUG,
        log_file          = None
) ->logging.Logger:
    '''获取日志器'''
    # 创建日志对象
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # 防止反复创建日志处理器
    if logger.handlers:
        return logger
    
    # 创建控制台日志处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(console_handler)

    # 创建文件日志处理器
    if not log_file:
        log_file = os.path.join(LOG_ROOT,f"{name}_{datetime.now().strftime('%Y%m%d')}.log")

    file_handler = logging.FileHandler(log_file,encoding='utf-8')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(DEFAULT_LOG_FORMAT)
    logger.addHandler(file_handler)

    return logger

logger = get_logger()

