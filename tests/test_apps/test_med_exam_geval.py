from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from deepeval.models import DeepEvalBaseLLM

from deepeval.apps.med_exam_geval.runner import run_evaluation


class FakeJudgeLLM(DeepEvalBaseLLM):
    def __init__(self):
        super().__init__("fake-judge")

    def load_model(self, *args, **kwargs):
        return self

    def get_model_name(self, *args, **kwargs) -> str:
        return "fake-judge"

    def generate(self, prompt: str, schema: Optional[BaseModel] = None, **kwargs):
        if schema is not None:
            return schema.model_validate({"score": 10, "reason": "OK"})
        return '{"score": 10, "reason": "OK"}'

    async def a_generate(
        self, prompt: str, schema: Optional[BaseModel] = None, **kwargs
    ):
        return self.generate(prompt, schema=schema, **kwargs)


def test_med_exam_geval_runs_sample_dataset():
    root = Path(__file__).resolve().parents[2]
    dataset_path = root / "examples" / "med_exam_geval_sample.jsonl"
    res = run_evaluation(
        dataset_path=dataset_path,
        judge_model=FakeJudgeLLM(),
        run_async=False,
        use_cache=False,
    )
    assert res.summary.total == 2
    assert res.summary.pass_count == 2
    assert len(res.cases) == 2
    assert all(c.total_score >= 0.99 for c in res.cases)

