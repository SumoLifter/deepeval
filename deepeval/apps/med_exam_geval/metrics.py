from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from deepeval.metrics import GEval
from deepeval.metrics.g_eval import Rubric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCaseParams


DEFAULT_METRIC_NAMES = (
    "ItemQuality",
    "AnswerConsistency",
    "ExplanationQuality",
    "FormatCompliance",
    "ExpertAlignment",
)


@dataclass(frozen=True)
class MetricSpec:
    name: str
    evaluation_steps: List[str]
    evaluation_params: List[LLMTestCaseParams]
    rubric: List[Rubric]


def _default_rubric() -> List[Rubric]:
    return [
        Rubric(score_range=(0, 2), expected_outcome="严重不符合标准或存在重大错误。"),
        Rubric(score_range=(3, 5), expected_outcome="存在明显缺陷，整体不合格。"),
        Rubric(score_range=(6, 7), expected_outcome="基本合格，但仍有较多可改进点。"),
        Rubric(score_range=(8, 9), expected_outcome="质量较好，只有少量瑕疵。"),
        Rubric(score_range=(10, 10), expected_outcome="完全符合标准，可直接入库使用。"),
    ]


def build_metric_specs() -> List[MetricSpec]:
    common_params = [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
        LLMTestCaseParams.CONTEXT,
    ]
    with_expected = common_params + [LLMTestCaseParams.EXPECTED_OUTPUT]

    return [
        MetricSpec(
            name="ItemQuality",
            evaluation_params=common_params,
            rubric=_default_rubric(),
            evaluation_steps=[
                "读取【题干】与【选项】（如存在），评估题干是否清晰、信息充分、无明显歧义。",
                "评估选项是否同一维度、互斥且覆盖合理；是否存在重复、无意义、明显提示正确项的选项。",
                "若题干无法独立作答、选项不成题或严重歧义，给低分。",
                "输出一个0-10整数分和中文理由，理由需指出具体问题或优点。",
            ],
        ),
        MetricSpec(
            name="AnswerConsistency",
            evaluation_params=common_params,
            rubric=_default_rubric(),
            evaluation_steps=[
                "检查【答案】是否存在、是否能在【选项】中定位到对应选项。",
                "若为单选题，答案必须且只能是一个选项字母；若出现多个字母或超出选项范围，强惩罚。",
                "检查【答案】与题干、选项内容是否自洽，是否存在自相矛盾或明显不可能正确的情况。",
                "若无法判定答案或答案格式不合规，给低分。",
                "输出一个0-10整数分和中文理由。",
            ],
        ),
        MetricSpec(
            name="ExplanationQuality",
            evaluation_params=common_params,
            rubric=_default_rubric(),
            evaluation_steps=[
                "阅读【解析】，评估是否解释了正确选项为什么正确，并能反驳其他选项的常见错误点（如存在选项）。",
                "检查医学事实是否符合通用临床知识与常见诊疗原则；若出现危险或严重错误建议，分数封顶为2分以内。",
                "若解析空泛、只重复答案、或与题干不相关，扣分。",
                "输出一个0-10整数分和中文理由，明确指出关键错误或缺失的得分点。",
            ],
        ),
        MetricSpec(
            name="FormatCompliance",
            evaluation_params=common_params,
            rubric=_default_rubric(),
            evaluation_steps=[
                "检查是否包含四要素：题干、选项（若题型需要）、答案、解析。",
                "检查结构是否清晰、可读、可直接录入题库；答案格式是否规范（例如：单选题为单个字母）。",
                "若缺少关键要素导致无法入库或无法判分，强惩罚。",
                "输出一个0-10整数分和中文理由。",
            ],
        ),
        MetricSpec(
            name="ExpertAlignment",
            evaluation_params=with_expected,
            rubric=_default_rubric(),
            evaluation_steps=[
                "将【实际输出】与【专家输出】逐项对比：题干核心考点、选项设置、标准答案、解析要点。",
                "答案对齐：若标准答案与专家答案不一致，强惩罚（通常≤2分），除非专家输出明显自相矛盾。",
                "解析对齐：检查是否覆盖专家解析的关键得分点，是否引入专家版本没有的新错误或歧义。",
                "在不影响正确性的前提下，允许文字表述差异，但不允许关键医学结论差异。",
                "输出一个0-10整数分和中文理由，指出与专家版的关键差距。",
            ],
        ),
    ]


def build_metrics(
    *,
    judge_model: Optional[Union[str, DeepEvalBaseLLM]] = None,
    threshold: float = 0.7,
    async_mode: bool = True,
    verbose_mode: bool = False,
    metric_names: Sequence[str] = DEFAULT_METRIC_NAMES,
) -> List[GEval]:
    specs = {spec.name: spec for spec in build_metric_specs()}
    metrics: List[GEval] = []
    for name in metric_names:
        spec = specs.get(name)
        if spec is None:
            raise ValueError(f"Unknown metric name: {name}")
        metrics.append(
            GEval(
                name=name,
                evaluation_params=spec.evaluation_params,
                evaluation_steps=spec.evaluation_steps,
                rubric=spec.rubric,
                threshold=threshold,
                async_mode=async_mode,
                verbose_mode=verbose_mode,
                model=judge_model,
                _include_g_eval_suffix=False,
            )
        )
    return metrics


def normalize_weights(
    weights: Optional[Dict[str, float]],
    metric_names: Sequence[str],
) -> Dict[str, float]:
    if not weights:
        w = 1.0 / max(1, len(metric_names))
        return {name: w for name in metric_names}
    filtered = {k: float(v) for k, v in weights.items() if k in metric_names}
    if not filtered:
        w = 1.0 / max(1, len(metric_names))
        return {name: w for name in metric_names}
    s = sum(max(0.0, v) for v in filtered.values())
    if s <= 0:
        w = 1.0 / max(1, len(metric_names))
        return {name: w for name in metric_names}
    return {k: max(0.0, v) / s for k, v in filtered.items()}


def compute_weighted_total(
    metric_scores: Dict[str, Optional[float]],
    weights: Dict[str, float],
) -> float:
    total = 0.0
    for k, w in weights.items():
        s = metric_scores.get(k)
        if s is None:
            continue
        total += float(s) * float(w)
    return total

