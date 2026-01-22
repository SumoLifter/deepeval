from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from deepeval.apps.med_exam_geval.runner import run_evaluation
from deepeval.apps.med_exam_geval.external_llm import ExternalOpenAICompatibleLLM
from deepeval.apps.med_exam_geval.report import write_csv_report, write_json_report
from deepeval.models import DeepEvalBaseLLM


def _parse_json_obj(s: Optional[str]) -> Optional[Dict[str, Any]]:
    if not s:
        return None
    return json.loads(s)


class _OfflineJudgeLLM(DeepEvalBaseLLM):
    def __init__(self):
        super().__init__("offline-judge")

    def load_model(self, *args, **kwargs):
        return self

    def get_model_name(self, *args, **kwargs) -> str:
        return "offline-judge"

    def generate(self, prompt: str, schema=None, **kwargs):
        if schema is not None:
            return schema.model_validate({"score": 10, "reason": "offline smoke test"})
        return '{"score": 10, "reason": "offline smoke test"}'

    async def a_generate(self, prompt: str, schema=None, **kwargs):
        return self.generate(prompt, schema=schema, **kwargs)


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="med_exam_geval",
        description="Use G-Eval to evaluate medical licensing exam item generations.",
    )
    ap.add_argument("--data", required=True, help="Path to JSON/JSONL dataset.")
    ap.add_argument("--out", required=True, help="Output report path (json).")
    ap.add_argument(
        "--out-format",
        default="json",
        choices=["json", "csv"],
        help="Report format.",
    )
    ap.add_argument("--judge-model", default=None, help="Judge model name (optional).")
    ap.add_argument(
        "--offline-judge",
        action="store_true",
        help="Use a built-in deterministic judge for smoke testing (no external API calls).",
    )
    ap.add_argument(
        "--judge-external",
        action="store_true",
        help="Use external OpenAI-compatible API as judge (via env config).",
    )
    ap.add_argument(
        "--judge-external-model",
        default=None,
        help="Model name for external judge (required if --judge-external).",
    )
    ap.add_argument("--threshold", type=float, default=0.7, help="Per-metric threshold.")
    ap.add_argument("--pass-threshold", type=float, default=0.7, help="Total score pass threshold.")
    ap.add_argument("--weights", default=None, help="JSON object mapping metric->weight.")
    ap.add_argument(
        "--predict-external",
        action="store_true",
        help="If model_output missing, call external OpenAI-compatible API to generate it.",
    )
    ap.add_argument(
        "--predict-external-model",
        default=None,
        help="Model name for external predictor (required if --predict-external).",
    )
    ap.add_argument("--no-async", action="store_true", help="Disable async execution.")
    ap.add_argument("--max-concurrent", type=int, default=20, help="Max concurrent evals.")
    ap.add_argument("--use-cache", action="store_true", help="Enable cache usage.")

    args = ap.parse_args()

    weights = _parse_json_obj(args.weights)
    judge_model = args.judge_model
    if args.offline_judge:
        judge_model = _OfflineJudgeLLM()
    if args.judge_external:
        if not args.judge_external_model:
            raise SystemExit("--judge-external-model is required when --judge-external is set")
        judge_model = ExternalOpenAICompatibleLLM(model=args.judge_external_model)

    predict_model = None
    if args.predict_external:
        if not args.predict_external_model:
            raise SystemExit("--predict-external-model is required when --predict-external is set")
        predict_model = ExternalOpenAICompatibleLLM(model=args.predict_external_model)

    if judge_model is None and not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "No judge is configured. Set OPENAI_API_KEY, or use --judge-external, or use --offline-judge for smoke test."
        )

    result = run_evaluation(
        dataset_path=Path(args.data),
        judge_model=judge_model,
        predict_model=predict_model,
        threshold=float(args.threshold),
        pass_threshold=float(args.pass_threshold),
        weights=weights,
        run_async=not bool(args.no_async),
        max_concurrent=int(args.max_concurrent),
        use_cache=bool(args.use_cache),
    )

    out_path = Path(args.out)
    if args.out_format == "csv":
        write_csv_report(result, out_path)
    else:
        write_json_report(result, out_path)


if __name__ == "__main__":
    main()
