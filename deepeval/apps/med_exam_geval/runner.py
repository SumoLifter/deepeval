from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from deepeval import evaluate
from deepeval.evaluate.configs import AsyncConfig, DisplayConfig, CacheConfig, ErrorConfig
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

from deepeval.apps.med_exam_geval.metrics import (
    DEFAULT_METRIC_NAMES,
    build_metrics,
    compute_weighted_total,
    normalize_weights,
)
from deepeval.apps.med_exam_geval.parser import parse_exam_item, format_exam_item_for_judge
from deepeval.apps.med_exam_geval.standards import build_context


@dataclass(frozen=True)
class DatasetRecord:
    id: str
    model_output: Optional[str]
    expert_output: str
    generation_prompt: Optional[str] = None
    question_type: Optional[str] = None
    subject: Optional[str] = None
    difficulty: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None


def _read_json_or_jsonl(path: Union[str, Path]) -> List[Dict[str, Any]]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() == ".jsonl":
        rows = []
        for ln in text.splitlines():
            ln = ln.strip()
            if not ln:
                continue
            rows.append(json.loads(ln))
        return rows
    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
        return data["data"]
    raise ValueError("Unsupported JSON format; expected list or {data:[...]}")


def load_dataset(path: Union[str, Path]) -> List[DatasetRecord]:
    rows = _read_json_or_jsonl(path)
    out: List[DatasetRecord] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"Row {i} must be an object")
        rid = str(row.get("id") or row.get("_id") or i)
        model_output = row.get("model_output") or row.get("actual_output") or row.get("output")
        expert_output = row.get("expert_output") or row.get("expected_output") or row.get("expert")
        if expert_output is None:
            raise ValueError(f"Row {rid} missing expert_output")
        extra = dict(row)
        for k in [
            "id",
            "_id",
            "model_output",
            "actual_output",
            "output",
            "expert_output",
            "expected_output",
            "expert",
            "generation_prompt",
            "question_type",
            "subject",
            "difficulty",
        ]:
            extra.pop(k, None)
        out.append(
            DatasetRecord(
                id=rid,
                model_output=str(model_output) if model_output is not None else None,
                expert_output=str(expert_output),
                generation_prompt=row.get("generation_prompt"),
                question_type=row.get("question_type"),
                subject=row.get("subject"),
                difficulty=row.get("difficulty"),
                extra=extra or None,
            )
        )
    return out


def build_test_cases(
    records: Sequence[DatasetRecord],
    *,
    predict_model: Optional[DeepEvalBaseLLM] = None,
) -> List[LLMTestCase]:
    test_cases: List[LLMTestCase] = []
    for r in records:
        actual_raw = r.model_output
        if actual_raw is None:
            if predict_model is None:
                raise ValueError(f"Record {r.id} missing model_output and predict_model is not set")
            prompt = r.generation_prompt or "生成1道执业医师考试题目（含选项、答案与解析）。"
            generated = predict_model.generate(prompt)
            if isinstance(generated, tuple) and len(generated) == 2:
                actual_raw = str(generated[0])
            else:
                actual_raw = str(generated)
        parsed_actual = parse_exam_item(actual_raw)
        parsed_expected = parse_exam_item(r.expert_output)
        actual_norm = format_exam_item_for_judge(parsed_actual)
        expected_norm = format_exam_item_for_judge(parsed_expected)
        ctx = build_context(question_type=r.question_type, subject=r.subject)
        prompt = r.generation_prompt or "请评估以下模型生成的执业医师考试题目（含答案与解析）。"
        additional_metadata: Dict[str, Any] = {
            "id": r.id,
            "question_type": r.question_type,
            "subject": r.subject,
            "difficulty": r.difficulty,
            "actual_parse_success": parsed_actual.parse_success,
            "actual_parse_warning": parsed_actual.parse_warning,
            "expert_parse_success": parsed_expected.parse_success,
            "expert_parse_warning": parsed_expected.parse_warning,
        }
        if r.extra:
            additional_metadata.update(r.extra)
        test_cases.append(
            LLMTestCase(
                input=prompt,
                actual_output=actual_norm,
                expected_output=expected_norm,
                context=[ctx],
                additional_metadata=additional_metadata,
                name=r.id,
            )
        )
    return test_cases


@dataclass(frozen=True)
class PerCaseMetric:
    name: str
    score: Optional[float]
    success: bool
    reason: Optional[str]
    threshold: float
    evaluation_model: Optional[str]


@dataclass(frozen=True)
class PerCaseResult:
    id: str
    success: bool
    total_score: float
    metrics: List[PerCaseMetric]
    input: Optional[str]
    actual_output: Optional[str]
    expected_output: Optional[str]
    metadata: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class RunSummary:
    total: int
    pass_count: int
    pass_rate: float
    mean_total_score: float
    metric_means: Dict[str, float]


@dataclass(frozen=True)
class RunResult:
    summary: RunSummary
    cases: List[PerCaseResult]


def run_evaluation(
    *,
    dataset_path: Union[str, Path],
    judge_model: Optional[Union[str, DeepEvalBaseLLM]] = None,
    predict_model: Optional[DeepEvalBaseLLM] = None,
    threshold: float = 0.7,
    pass_threshold: float = 0.7,
    metric_names: Sequence[str] = DEFAULT_METRIC_NAMES,
    weights: Optional[Dict[str, float]] = None,
    run_async: bool = True,
    max_concurrent: int = 20,
    use_cache: bool = False,
) -> RunResult:
    records = load_dataset(dataset_path)
    test_cases = build_test_cases(records, predict_model=predict_model)

    metrics = build_metrics(
        judge_model=judge_model,
        threshold=threshold,
        async_mode=run_async,
        verbose_mode=False,
        metric_names=metric_names,
    )
    weight_map = normalize_weights(weights, metric_names)

    res = evaluate(
        test_cases=test_cases,
        metrics=metrics,
        async_config=AsyncConfig(run_async=run_async, max_concurrent=max_concurrent),
        display_config=DisplayConfig(show_indicator=False, print_results=False),
        cache_config=CacheConfig(write_cache=True, use_cache=use_cache),
        error_config=ErrorConfig(ignore_errors=False, skip_on_missing_params=False),
    )

    cases: List[PerCaseResult] = []
    metric_sums: Dict[str, float] = {k: 0.0 for k in metric_names}
    metric_counts: Dict[str, int] = {k: 0 for k in metric_names}
    total_sum = 0.0
    pass_count = 0

    for tr in res.test_results:
        meta = tr.additional_metadata or {}
        case_id = str(meta.get("id") or tr.name)
        metrics_out: List[PerCaseMetric] = []
        score_map: Dict[str, Optional[float]] = {}
        if tr.metrics_data:
            for md in tr.metrics_data:
                metrics_out.append(
                    PerCaseMetric(
                        name=md.name,
                        score=md.score,
                        success=md.success,
                        reason=md.reason,
                        threshold=md.threshold,
                        evaluation_model=md.evaluation_model,
                    )
                )
                score_map[md.name] = md.score
        total_score = compute_weighted_total(score_map, weight_map)
        success = total_score >= pass_threshold
        if success:
            pass_count += 1
        total_sum += total_score

        for k in metric_names:
            s = score_map.get(k)
            if s is None:
                continue
            metric_sums[k] += float(s)
            metric_counts[k] += 1

        cases.append(
            PerCaseResult(
                id=case_id,
                success=success,
                total_score=total_score,
                metrics=metrics_out,
                input=tr.input if isinstance(tr.input, str) else None,
                actual_output=tr.actual_output if isinstance(tr.actual_output, str) else None,
                expected_output=tr.expected_output,
                metadata=meta or None,
            )
        )

    metric_means = {
        k: (metric_sums[k] / metric_counts[k] if metric_counts[k] else 0.0)
        for k in metric_names
    }
    mean_total = total_sum / len(cases) if cases else 0.0
    summary = RunSummary(
        total=len(cases),
        pass_count=pass_count,
        pass_rate=(pass_count / len(cases) if cases else 0.0),
        mean_total_score=mean_total,
        metric_means=metric_means,
    )
    return RunResult(summary=summary, cases=cases)
