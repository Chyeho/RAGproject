'''RAG 评测体系（P0，执行文档第 4 章）

模块一览：
- dataset     评测集构建（LLM 从自造样例生成 QA）与加载校验
- metrics     确定性检索指标（文档级/片段级 HitRate、MRR、Precision、内容召回）
- llm_judge   LLM 裁判生成指标（Faithfulness / AnswerRelevancy）
- runner      评测编排 CLI（直接实例化现有链路对象，不动链路代码）
- report      报告生成（json+md）与多版本对比
- make_samples 自造样例文档生成器（5 格式）
- datasets/   自造样例（samples/）与评测集（eval_dataset.json）

注意：本包不 eager 导入子模块，避免 import 即触发模型工厂实例化与向量库连接。
'''
