# -*- coding: utf-8 -*-
'''非业务问题识别：问候 / 自我介绍 / 使用咨询 / 感谢告别

纯规则判断，不依赖模型：
- 命中非业务句式，且不含任何业务关键词、长度不超过阈值 → 非业务，直达回答（跳过检索）
- 混合意图（如“你好，差旅标准是多少”）因含业务关键词 → 仍走 RAG 直调，由提示词处理问候部分
'''
import re

# 出现任一业务关键词即判定为业务问题（含混合意图），避免误跳过检索
_BUSINESS_RE = re.compile(
    r"制度|流程|规定|标准|报销|差旅|出差|住宿|餐补|采购|招标|比价|供应商|合同|付款|发票|"
    r"预算|审批|权限|账号|密码|考勤|请假|休假|加班|薪酬|工资|福利|绩效|入职|离职|培训|"
    r"会议|网络|vpn|安全|数据|客户|项目|产品|文档|知识库|向量|检索|系统|服务器|接口|api|"
    r"部署|备份|年会|抽奖|体检|社保|公积金|假期|工位|设备|电脑|申请|提交",
    re.I,
)

# 非业务句式：整句问候/致谢告别，或包含自我介绍/使用咨询特征
_NON_BUSINESS_PATTERNS = (
    re.compile(
        r"^(你好|您好|嗨|哈喽|哈啰|在吗|在么|早上好|上午好|中午好|下午好|晚上好|hello|hi|hey)"
        r"[呀啊哦呢!！。,.，~～？?\s]*$",
        re.I,
    ),
    re.compile(
        r"你是谁|你叫什么|介绍一下你自己|介绍一下你|自我介绍|你能做什么|你会做什么|"
        r"你有哪些能力|你有什么能力|你是ai|你是不是ai|你是机器人|你是人工智能|"
        r"你是什么助手|你是什么ai",
        re.I,
    ),
    re.compile(
        r"怎么使用你|如何使用你|如何用你|怎么用你|使用说明|使用方式|"
        r"你能帮我做什么|你能帮我干什么|怎么跟你聊|如何跟你聊",
        re.I,
    ),
    re.compile(
        r"^(谢谢|多谢|感谢|thx|thanks|再见|拜拜|bye)[呀啊哦呢!！。,.，~～？?\s]*$",
        re.I,
    ),
)

# 超过该长度的提问通常是完整业务描述，不做直达
_MAX_NON_BUSINESS_LEN = 40


def is_non_business(query: str) -> bool:
    '''判断是否为可直达回答的非业务问题（跳过检索与复杂路由）'''
    text = (query or "").strip()
    if not text or len(text) > _MAX_NON_BUSINESS_LEN:
        return False
    if _BUSINESS_RE.search(text):
        return False
    return any(pattern.search(text) for pattern in _NON_BUSINESS_PATTERNS)
