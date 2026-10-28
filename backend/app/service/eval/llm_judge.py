'''LLM 裁判生成指标（Faithfulness / AnswerRelevancy）

- 中文 Prompt 存放于 app/prompts/*.txt（经 prompt_loader 加载），内容固定、temperature=0
  （通过 bind 绑定，不改共享单例模型），保证跨阶段公平对比的口径
- 输出严格 JSON：{"score": <0.0~1.0>, "reason": "<简短理由>"}
- 解析失败/调用异常返回 None，不计入均值（另计 judge_error 数），保证评测可跑完
'''
import json
import re

from app.utils.logger_handler import logger
from app.utils.prompt_loader import load_prompt

# ---------- 裁判 Prompt（app/prompts/ 下的 txt 文件，加载后保持模块常量名） ----------

FAITHFULNESS_PROMPT = load_prompt("faithfulness_judge_prompt_path")
RELEVANCY_PROMPT = load_prompt("relevancy_judge_prompt_path")
CORRECTNESS_PROMPT = load_prompt("correctness_judge_prompt_path")


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


def correctness(chat_model, question: str, reference: str, answer: str) -> float | None:
    """答案正确率（A/B 专用）：对比标准答案，输出 0 / 0.5 / 1 三档

    - 空回答直接记 0（无需调用裁判）
    - 裁判输出非标准档位时，就近吸附到 0/0.5/1，保证报告口径统一
    - 调用/解析失败返回 None，不计入均值（沿用现有裁判口径）
    """
    if not str(answer or "").strip():
        return 0.0
    prompt = CORRECTNESS_PROMPT.format(question=question, reference=reference, answer=answer)
    score = _invoke_judge(chat_model.bind(temperature=0), prompt)
    if score is None:
        return None
    return min((0.0, 0.5, 1.0), key=lambda level: abs(level - score))


def aggregate_correctness(scores: list[float | None]) -> dict:
    """聚合正确率：None（裁判失败）不计入均值，单独计数"""
    valid = [s for s in scores if s is not None]
    return {
        "num_judged": len(valid),
        "num_judge_error": len(scores) - len(valid),
        "mean": (sum(valid) / len(valid)) if valid else None,
    }


def aggregate_generation(scores: list[float | None]) -> dict:
    """聚合生成指标：None（裁判失败）不计入均值，单独计数"""
    valid = [s for s in scores if s is not None]
    return {
        "num_judged": len(valid),
        "num_judge_error": len(scores) - len(valid),
        "mean": (sum(valid) / len(valid)) if valid else None,
    }
