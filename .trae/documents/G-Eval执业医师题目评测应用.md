## 你要交付的东西
- 一个可运行的小应用：对“微调模型生成的题目（含答案+解析）”做 G‑Eval 评测，并可用“专家修改版”作为 expected_output 对齐评测。
- 一个“可接入外部 API”的版本：既支持
  - 调外部推理 API 先生成题目（可选），再评测；
  - 也支持把 judge（G‑Eval 的评测模型）切到外部 API（可选）。
- 一份使用说明文档：`use.md`（含数据格式、命令行用法、外部 API 接入配置、输出报告说明）。

## 评测输入（模型输出 + 专家输出）
- 数据文件支持 JSON 或 JSONL。
- 每条样本字段：
  - `id`
  - `model_output`：微调模型生成的题（题目+选项+答案+解析）
  - `expert_output`：专家修改版（题目+选项+答案+解析）
  - 可选：`generation_prompt`、`question_type`、`subject`、`difficulty`
- 评测时构造 `LLMTestCase`：
  - `input` = generation_prompt（缺省用固定说明）
  - `actual_output` = 解析/标准化后的 model_output
  - `expected_output` = 解析/标准化后的 expert_output
  - `context` = 执业医师题目标准（格式规范、唯一正确答案、医学安全等）

## 输出解析与标准化（关键步骤）
- 为了让 judge 稳定评判，会对 model/expert 两边都做“宽松解析”并标准化：
  - 抽取：`question_stem`、`options`、`answer`、`analysis`
  - 支持 JSON 输出与非结构化文本；解析失败则保留原文并在评分中因“不可解析/格式不合规”扣分。

## 指标设计（G‑Eval）
- 采用多指标拆分（更可控、更易解释），并都提供中文 `evaluation_steps` + `rubric(0-10)`：
  1) ItemQuality：题干/选项质量与题目规范
  2) AnswerConsistency：答案唯一性与自洽（单选必须唯一正确）
  3) ExplanationQuality：解析质量与医学正确性/安全性
  4) FormatCompliance：四要素齐全、格式可入库
  5) ExpertAlignment（对齐专家版）：答案是否一致、解析要点是否覆盖、是否引入新错误
- 默认给一个总分（可配置权重）与通过阈值（可配置）。

## 外部 API 接入（两种可选模式）
### 模式A：用外部 API 生成题目（被测模型）
- 当数据里没有 `model_output` 时，CLI 支持 `--predict` 先调用外部 API 生成，再进入评测。
- 会新增一个 HTTP 客户端与一个“生成模型适配器”，把外部 API 包装成 `DeepEvalBaseLLM`（用于生成文本）。
- 配置方式：环境变量或 CLI 参数（不写死任何密钥）：
  - `EXTERNAL_LLM_API_BASE_URL`
  - `EXTERNAL_LLM_API_KEY`（可选）
  - `EXTERNAL_LLM_API_HEADERS`（可选 JSON 字符串）
  - `EXTERNAL_LLM_TIMEOUT_SECONDS`、`EXTERNAL_LLM_MAX_RETRIES`

### 模式B：用外部 API 作为 judge（评测模型）
- `GEval(model=your_external_judge_llm)` 支持传入自定义 `DeepEvalBaseLLM`。
- 这样你可以把评测模型也接到你自己的评测服务或私有模型服务。
- 若外部 judge 不支持 logprobs，G‑Eval 会自动走“无 logprobs”的降级路径（repo 里已实现）。

## 应用代码结构（将要新增）
- `deepeval/apps/med_exam_geval/`
  - `parser.py`：解析/标准化题目四要素
  - `standards.py`：执业医师题目标准与题型约束文本
  - `metrics.py`：构建 5 个 GEval 指标（steps + rubric）
  - `external_api.py`：外部 API 调用（requests/httpx 依赖会先确认仓库已有再选型）
  - `external_llm.py`：`DeepEvalBaseLLM` 适配器（用于被测模型/或 judge）
  - `runner.py`：读取数据→构建 LLMTestCase→evaluate→收集结果
  - `report.py`：导出 JSON/CSV（逐题+汇总+失败样例）
  - `__main__.py`：CLI 入口
- `use.md`：完整使用说明与示例
- `examples/med_exam_geval_sample.jsonl`：最小样例数据

## 测试与验收
- 单测不依赖外部 key：提供一个假的 `DeepEvalBaseLLM` judge，返回固定 JSON（reason+score），跑通解析→评测→报告。
- 验收标准：
  - CLI 能跑通样例数据，产出报告文件
  - 报告包含：每题每指标分数+理由、总分、通过判定、总体统计

## use.md 会包含的内容
- 数据格式说明（model_output/expert_output 示例）
- 仅评测模式（已有 model_output）
- 预测+评测模式（外部 API 生成 model_output）
- 外部 judge 模式（把 GEval 的 model 指向外部 API）
- 输出报告字段解释与常见问题（解析失败、题型不一致、阈值/权重怎么调）

我会按这个方案落地全部代码与文档；确认后我再开始实际创建文件与实现。