## 先说明两点（已按占位符处理）
- 我不会再使用或记录你之前发来的真实 `api_key`，下面所有命令均用占位符 `YOUR_MOONSHOT_API_KEY`。
- 你的 base_url 不要写成带 `/v1` 的形式；因为应用会拼接 `/v1/chat/completions`。正确应为：`https://api.moonshot.cn`。

## 验证目标
- 在 `deepeval_env` 中：自动补齐缺失包 → 安装本仓库 → 跑通单测 → 跑通 CLI（样例数据）
- 再用 Moonshot 作为 judge 跑一次（可选，但推荐）

## 我将执行的步骤（每步都有可见输出）
### 1) 确认环境与关键依赖
- 运行：
  - `python -V`
  - `python -c "import sys; print(sys.executable)"`
  - `python -c "import pytest, pydantic_settings; print('deps_ok')"`
- 若缺包：
  - `pip install -U pytest pydantic-settings`

### 2) 安装本仓库（可编辑模式）
- 运行：
  - `pip install -e .`

### 3) 跑单测（不需要任何外部 key）
- 运行：
  - `python -m pytest -q tests/test_apps/test_med_exam_geval.py`

### 4) 跑 CLI（样例数据，不依赖外部 API）
- 运行：
  - `python -m deepeval.apps.med_exam_geval --data examples/med_exam_geval_sample.jsonl --out out/report.json --out-format json --no-async`

### 5) 配置 Moonshot 外部 API（占位符）并用其作为 judge 跑一遍
- PowerShell 环境变量（当前终端会话内设置，不写入文件）：
  - `$env:EXTERNAL_LLM_API_BASE_URL = "https://api.moonshot.cn"`
  - `$env:EXTERNAL_LLM_API_KEY = "YOUR_MOONSHOT_API_KEY"`
- 运行：
  - `python -m deepeval.apps.med_exam_geval --data examples/med_exam_geval_sample.jsonl --out out/report.moonshot.json --out-format json --no-async --judge-external --judge-external-model moonshot-v1-8k`

## 若出现失败，我会怎么处理
- 若仍提示缺包：继续按报错补装（优先 pip，其次 conda-forge）
- 若 Moonshot 返回结构不兼容：调整外部适配器解析 `choices[0].message.content` 的路径并重跑第 5 步
- 若请求超时/429：提高 `EXTERNAL_LLM_TIMEOUT_SECONDS` 或降低并发（我们已 `--no-async`）

你同意后，我就直接在当前终端里按以上步骤依次执行并把结果贴出来。