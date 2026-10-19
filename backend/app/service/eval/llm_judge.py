'''LLM 裁判生成指标（Faithfulness / AnswerRelevancy）

- 中文 Prompt 固定、temperature=0（通过 bind 绑定，不改共享单例模型）
- 输出严格 JSON：{"score": <0.0~1.0>, "reason": "<简短理由>"}
- 解析失败/调用异常返回 None，不计入均值（另计 judge_error 数），保证评测可跑完
'''
import json
import re

from app.utils.logger_handler import logger

# ---------- 裁判 Prompt（中文，固定不变；跨阶段公平对比的口径） ----------

FAITHFULNESS_PROMPT = """你是一个严谨的评估助手。请评估【待评估回答】中的信息是否被【检索上下文】支持。

评分标准：
- 1.0：回答中的全部关键信息（数字、日期、流程、结论）都能在检索上下文中找到依据
- 0.7：绝大部分关键信息有依据，仅少量细节属于常识补充
- 0.4：约一半关键信息有依据，另一半为上下文外的补充或推测
- 0.0：关键信息基本无上下文依据（编造、与上下文矛盾或答非所问）

说明：
- 忽略上下文与回答中都未涉及的纯常识性表述
- 回答表示"无法回答/资料未提及"且属实（上下文确实无相关信息）时，评 1.0

【用户问题】
{question}

【检索上下文】
{context}

【待评估回答】
{answer}

仅输出一行 JSON（不要输出其他内容）：
{{"score": <0.0~1.0 的一位小数>, "reason": "<不超过30字的理由>"}}"""

RELEVANCY_PROMPT = """你是一个严谨的评估助手。请评估【待评估回答】与【用户问题】的相关程度。

评分标准：
- 1.0：直接回答了问题，切题且信息有效
- 0.7：大体切题，但仅部分回答了问题或明显啰嗦绕远
- 0.4：与问题相关但未正面回答（如仅复述背景、给出泛泛建议）
- 0.0：跑题、答非所问或空泛拒答

【用户问题】
{question}

【待评估回答】
{answer}

仅输出一行 JSON（不要输出其他内容）：
{{"score": <0.0~1.0 的一位小数>, "reason": "<不超过30字的理由>"}}"""


# ---------- 解析与调用 ----------

def parse_score_json(text: str) -> float | None:
    """从裁判输出解析 score；容错处理 markdown 代码块与前后杂文；失败返回 None"""
    if not text:
        return None
    # 去掉可能的 ```json ... ``` 包裹
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    # 截取第一个 {...} 片段
    match = re.search(r"\{[^{}]*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        score = float(data.get("score"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    # 越界钳制
    return max(0.0, min(1.0, score))


def _invoke_judge(bound_model, prompt: str) -> float | None:
    """调用裁判模型并解析分数；任何异常记日志并返回 None（不中断评测）"""
    try:
        response = bound_model.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        return parse_score_json(content)
    except Exception as e:
        logger.error(f"[LLM裁判]调用失败：{str(e)}")
        return None


def faithfulness(chat_model, question: str, answer: str,
                 contexts: list[str]) -> float | None:
    """忠实度：答案中的论断是否被检索上下文支持（0~1）"""
    context_text = "\n\n".join(
        f"【资料{i}】{c}" for i, c in enumerate(contexts, start=1)
    ) or "（无检索上下文）"
    prompt = FAITHFULNESS_PROMPT.format(
        question=question, context=context_text, answer=answer,
    )
    return _invoke_judge(chat_model.bind(temperature=0), prompt)


def answer_relevancy(chat_model, question: str, answer: str) -> float | None:
    """答案相关性：答案与问题的相关程度（0~1）"""
    prompt = RELEVANCY_PROMPT.format(question=question, answer=answer)
    return _invoke_judge(chat_model.bind(temperature=0), prompt)


def aggregate_generation(scores: list[float | None]) -> dict:
    """聚合生成指标：None（裁判失败）不计入均值，单独计数"""
    valid = [s for s in scores if s is not None]
    return {
        "num_judged": len(valid),
        "num_judge_error": len(scores) - len(valid),
        "mean": (sum(valid) / len(valid)) if valid else None,
    }
