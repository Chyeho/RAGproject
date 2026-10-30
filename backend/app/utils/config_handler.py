'''配置信息管理工具'''
import os

import yaml
from app.utils.env_loader import load_model_env
from app.utils.path_tool import get_abs_path, get_config_path

HYBRID_DEFAULTS = {
    "ENABLE_HYBRID_ROUTER": False,   # 代码兜底：配置缺失时安全回退纯 RAG 直调
    "REACT_MAX_STEPS": 3,
    "REACT_TIMEOUT_MS": 30000,
    "TOOL_TIMEOUT_MS": 10000,
    "ENABLE_REACT_FALLBACK": True,
    "ROUTER_RULES_PATH": "config/router_rules.yml",
    "LOG_TRACE_LEVEL": "summary",
    "OBS_TRACE_DIR": "logs/traces",
    "OBS_TEXT_MAX_CHARS": 200,
    "ENABLE_TRACE_API": False,
    "RETURN_TRACE_TO_CLIENT": False,
    "COMPARE_CALC_MAX_ITEMS": 20,
}

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

def load_retrieval_config(config_path:str | None = None,encoding:str = "utf-8"):
    '''加载检索链路配置信息文件（P2 起 chunk/检索参数收敛于此）

    config_path 为空时走 get_config_path：容器部署下优先读运行时可写副本。
    '''
    config_path = config_path or get_config_path("retrieval_config.yml")
    with open(config_path,"r",encoding=encoding) as f:
        return yaml.load(f,Loader=yaml.FullLoader)


def _coerce_env(value: str, default):
    '''按默认值类型转换环境变量，转换失败时保留默认值'''
    try:
        if isinstance(default, bool):
            return value.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            return int(value)
        return value
    except (TypeError, ValueError):
        return default


def load_hybrid_config(config_path: str | None = None, encoding: str = "utf-8") -> dict:
    '''加载 RAG+ReAct 混合架构配置：代码默认值 ← YAML ← 同名环境变量

    YAML 缺失或格式异常时仅使用代码默认值（ENABLE_HYBRID_ROUTER=False 安全回退），
    不阻断应用启动。
    '''
    conf = dict(HYBRID_DEFAULTS)
    path = config_path or get_abs_path("config/hybrid_config.yml")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding=encoding) as f:
                loaded = yaml.load(f, Loader=yaml.FullLoader) or {}
            if isinstance(loaded, dict):
                conf.update({k: loaded[k] for k in HYBRID_DEFAULTS if k in loaded})
        except Exception:
            # 配置错误不阻断启动：保留代码默认值（默认关闭混合路由）
            pass
    for key, default in HYBRID_DEFAULTS.items():
        if key in os.environ:
            conf[key] = _coerce_env(os.environ[key], default)
    return conf

    
rag_conf        = load_rag_config()
qdrant_conf     = load_qdrant_config()
prompts_conf    = load_prompts_config()
agent_conf      = load_agent_config()
cache_conf      = load_cache_config()
retrieval_conf  = load_retrieval_config()
hybrid_conf     = load_hybrid_config()

# 模型相关环境变量兜底加载（本地直跑场景）：必须在模块尾部、先于
# modelFactory.factory 的模块级单例构建执行（factory 导入 rag_conf 时本模块
# 已执行完毕）。Docker Compose / 启动脚本注入的真实环境变量优先，仅注入缺失键
load_model_env()
