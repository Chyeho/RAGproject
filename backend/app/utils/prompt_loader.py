'''提示词模板加载工具'''
from app.utils.config_handler import prompts_conf
from app.utils.path_tool import get_abs_path
from app.utils.logger_handler import logger


def load_prompt(conf_key: str) -> str:
    '''通用提示词加载：按 prompts_config.yml 中的路径配置项读取对应 txt 文件

    Args:
        conf_key (str): prompts_config.yml 中的路径配置项名（如 system_prompt_path）
    '''
    try:
        prompt_path = get_abs_path(prompts_conf[conf_key])
    except KeyError as e:
        logger.error(f"[load_prompt]在yaml配置项中没有{conf_key}配置项")
        raise e

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"[load_prompt]加载提示词文件出错（{conf_key}），{str(e)}")
        raise e


def load_system_prompt():
    '''加载系统提示词'''
    return load_prompt("system_prompt_path")


def load_rag_prompt():
    '''加载rag总结提示词'''
    return load_prompt("rag_summarize_prompt_path")
