'''
路径工具
'''
import os

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

