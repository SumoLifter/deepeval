from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Sequence

from deepeval.apps.med_exam_geval.metrics import DEFAULT_METRIC_NAMES
from deepeval.apps.med_exam_geval.runner import RunResult


def to_json_dict(result: RunResult) -> Dict[str, Any]:
    return {
        "summary": asdict(result.summary),
        "cases": [
            {
                "id": c.id,
                "success": c.success,
                "total_score": c.total_score,
                "metrics": [asdict(m) for m in c.metrics],
                "metadata": c.metadata,
            }
            for c in result.cases
        ],
    }


def write_json_report(result: RunResult, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(to_json_dict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_csv_report(
    result: RunResult,
    out_path: Path,
    *,
    metric_names: Sequence[str] = DEFAULT_METRIC_NAMES,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "id",
                "success",
                "total_score",
                *[f"{m}_score" for m in metric_names],
                *[f"{m}_reason" for m in metric_names],
            ],
        )
        w.writeheader()
        for c in result.cases:
            metric_map = {m.name: m for m in c.metrics}
            row: Dict[str, Any] = {
                "id": c.id,
                "success": int(bool(c.success)),
                "total_score": c.total_score,
            }
            for m in metric_names:
                md = metric_map.get(m)
                row[f"{m}_score"] = None if md is None else md.score
                row[f"{m}_reason"] = None if md is None else md.reason
            w.writerow(row)

