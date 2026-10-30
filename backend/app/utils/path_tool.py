'''
路径工具
'''
import os
import shutil

def get_root_path() ->str:
    '''获取应用根目录（即 backend/app 目录本身）'''
    current_file = os.path.abspath(__file__)
    current_dir = os.path.dirname(current_file)
    root_dir = os.path.dirname(current_dir)

    return root_dir

def get_abs_path(relative_path:str) ->str:
    '''根据相对路径获取绝对路径'''
    root_dir = get_root_path()
    return os.path.join(root_dir,relative_path)

def get_config_path(config_name:str) ->str:
    '''获取可写配置文件的绝对路径

    - 未设置 RUNTIME_CONFIG_DIR（本地开发）：直接返回 app/config 下的只读默认配置
    - 已设置（容器部署）：首次调用时把默认配置复制到运行时可写目录，之后读写该副本，
      避免只读挂载导致设置页保存失败，也保证容器重建后配置仍在（配合命名卷）
    '''
    default_path = get_abs_path(os.path.join("config", config_name))
    runtime_dir = (os.environ.get("RUNTIME_CONFIG_DIR") or "").strip()
    if not runtime_dir:
        return default_path

    os.makedirs(runtime_dir, exist_ok=True)
    runtime_path = os.path.join(runtime_dir, config_name)
    if not os.path.exists(runtime_path):
        shutil.copyfile(default_path, runtime_path)
    return runtime_path

