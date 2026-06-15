'''配置信息管理工具'''
import yaml
from app.utils.path_tool import get_abs_path

def load_rag_config(config_path:str = get_abs_path("config/rag_config.yml"),encoding:str = "utf-8"):
    '''加载rag配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,yaml.FullLoader)
    
def load_chroma_config(config_path:str=get_abs_path("config/chroma_config.yml"),encoding:str="utf-8"):
    '''加载chroma配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)
    
def load_prompts_config(config_path:str=get_abs_path("config/prompts_config.yml"),encoding:str="utf-8"):
    '''加载prompts配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)
    
def load_agent_config(config_path:str = get_abs_path("config/agent_config.yml"),encoding:str = "utf-8"):
    '''加载agent配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,yaml.FullLoader)
    
def load_db_config(config_path:str=get_abs_path("config/db_config.yml"),encoding:str="utf-8"):
    '''加载db配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)
    
def load_cache_config(config_path:str = get_abs_path("config/cache_config.yml"),encoding:str = "utf-8"):
    '''加载cache配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,yaml.FullLoader)

    
rag_conf      = load_rag_config()
chroma_conf   = load_chroma_config()
prompts_conf  = load_prompts_config()
agent_conf    = load_agent_config()
db_conf       = load_db_config()
cache_conf    = load_cache_config()
