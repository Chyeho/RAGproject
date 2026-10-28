'''配置信息管理工具'''
import yaml
from app.utils.env_loader import load_model_env
from app.utils.path_tool import get_abs_path

def load_rag_config(config_path:str = get_abs_path("config/rag_config.yml"),encoding:str = "utf-8"):
    '''加载rag配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,yaml.FullLoader)
    
def load_qdrant_config(config_path:str=get_abs_path("config/qdrant_config.yml"),encoding:str="utf-8"):
    '''加载qdrant配置信息文件'''
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
    
def load_cache_config(config_path:str = get_abs_path("config/cache_config.yml"),encoding:str = "utf-8"):
    '''加载cache配置信息文件'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)

def load_retrieval_config(config_path:str = get_abs_path("config/retrieval_config.yml"),encoding:str = "utf-8"):
    '''加载检索链路配置信息文件（P2 起 chunk/检索参数收敛于此）'''
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)

    
rag_conf        = load_rag_config()
qdrant_conf     = load_qdrant_config()
prompts_conf    = load_prompts_config()
agent_conf      = load_agent_config()
cache_conf      = load_cache_config()
retrieval_conf  = load_retrieval_config()

# 模型相关环境变量兜底加载（本地直跑场景）：必须在模块尾部、先于
# modelFactory.factory 的模块级单例构建执行（factory 导入 rag_conf 时本模块
# 已执行完毕）。Docker Compose / 启动脚本注入的真实环境变量优先，仅注入缺失键
load_model_env()
