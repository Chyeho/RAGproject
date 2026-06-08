'''提示词模板加载工具'''
from config_handler import prompts_conf
from path_tool import get_abs_path
from logger_handler import logger


def load_system_prompt():
    '''加载系统提示词'''
    try:
        system_prompt_path = get_abs_path(prompts_conf["system_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_system_prompt]在yaml配置项中没有system_prompt_path配置项")
        raise e
    
    try:
        return open(system_prompt_path,"r",encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_system_prompts]解析系统提示词出错，{str(e)}")
        raise e
    
def load_rag_prompt():
    '''加载rag总结提示词'''
    try:
        rag_prompt_path = get_abs_path(prompts_conf["rag_summarize_prompt_path"])
    except KeyError as e:
        logger.error(f"[load_rag_prompt]在yaml配置项中没有rag_summarize_prompt_path配置项")
        raise e
    
    try:
        return open(rag_prompt_path,"r",encoding="utf-8").read()
    except Exception as e:
        logger.error(f"[load_rag_prompt]解析rag总结提示词出错，{str(e)}")
        raise e
