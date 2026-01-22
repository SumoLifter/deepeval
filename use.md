# med_exam_geval 使用说明

## 环境
- 使用 conda 环境：`deepeval_env`

```bash
conda activate deepeval_env
pip install -e .
```

## 数据格式
- 支持 `.jsonl` 或 `.json`，每条记录至少需要：
  - `id`
  - `expert_output`：专家修改版（题干+选项+答案+解析）
  - `model_output`：微调模型生成版（题干+选项+答案+解析）
- 可选字段：
  - `generation_prompt`：生成指令（用于记录/或在缺失 model_output 时用于预测）
  - `question_type`：`single_choice` / `multi_choice`
  - `subject`：学科方向
  - `difficulty`：难度

最小示例见：`examples/med_exam_geval_sample.jsonl`

## 快速开始（本地评测）
```bash
python -m deepeval.apps.med_exam_geval ^
  --data examples/med_exam_geval_sample.jsonl ^
  --out out/report.json ^
  --out-format json ^
  --no-async
```

输出为 JSON 时包含：
- `summary`：总体统计（均分、通过率、各指标均分）
- `cases`：逐题结果（每指标 score/reason、总分、metadata）

## 指标说明
默认评测 5 个指标：
- `ItemQuality`：题干/选项质量与题目规范
- `AnswerConsistency`：答案唯一性与自洽
- `ExplanationQuality`：解析质量与医学正确性/安全性
- `FormatCompliance`：四要素齐全与可入库性
- `ExpertAlignment`：与专家修改版对齐程度

## 权重与阈值
- `--threshold`：每个指标内部的通过阈值（G‑Eval 的 success 判断用）
- `--pass-threshold`：总分通过阈值（本应用的最终 pass/fail）
- `--weights`：JSON 对象，指定各指标权重（会自动归一化）
示例：强调对齐专家版
```bash
python -m deepeval.apps.med_exam_geval ^
  --data examples/med_exam_geval_sample.jsonl ^
  --out out/report.json ^
  --weights "{\"ExpertAlignment\": 0.6, \"ExplanationQuality\": 0.2, \"AnswerConsistency\": 0.2}"
```

## 接入外部 API（OpenAI 兼容）
外部 API 采用 OpenAI 兼容的 `POST /v1/chat/completions` 协议（即返回 `choices[0].message.content`）。

### 1) 用外部 API 作为 judge（评测模型）
设置环境变量：
```bash
set EXTERNAL_LLM_API_BASE_URL=https://your-openai-compatible-host
set EXTERNAL_LLM_API_KEY=YOUR_KEY
```

运行：
```bash
python -m deepeval.apps.med_exam_geval ^
  --data examples/med_exam_geval_sample.jsonl ^
  --out out/report.json ^
  --judge-external ^
  --judge-external-model gpt-4.1
```

可选配置：
- `EXTERNAL_LLM_API_HEADERS`：额外请求头（JSON 对象字符串，例如 `{\"X-Org\":\"xxx\"}`）
- `EXTERNAL_LLM_TIMEOUT_SECONDS`：超时秒数（默认 60）
- `EXTERNAL_LLM_MAX_RETRIES`：重试次数（默认 2）

### 2) 用外部 API 先生成 model_output（被测模型），再评测
当数据里某些样本缺少 `model_output` 时，可开启预测模式：
```bash
set EXTERNAL_LLM_API_BASE_URL=https://your-openai-compatible-host
set EXTERNAL_LLM_API_KEY=YOUR_KEY

python -m deepeval.apps.med_exam_geval ^
  --data your_dataset_missing_model_output.jsonl ^
  --out out/report.json ^
  --predict-external ^
  --predict-external-model your-finetuned-model-name
```

## 输出 CSV
```bash
python -m deepeval.apps.med_exam_geval ^
  --data examples/med_exam_geval_sample.jsonl ^
  --out out/report.csv ^
  --out-format csv ^
  --no-async
```

## 常见问题
1) 输出无法解析怎么办？
- 应用会做宽松解析并标准化；若仍缺失关键要素，`FormatCompliance`/相关指标会自动扣分。

2) 为什么建议提供专家修改版？
- `ExpertAlignment` 会以专家输出为金标准，能更稳定定位“关键差距”（答案不一致、解析要点缺失、引入新错误等）。
