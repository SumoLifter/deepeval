import json
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Any


@dataclass(frozen=True)
class ParsedExamItem:
    question_stem: Optional[str]
    options: Dict[str, str]
    answer: Optional[str]
    analysis: Optional[str]
    raw_text: str
    parse_success: bool
    parse_warning: Optional[str] = None


_OPTION_RE = re.compile(
    r"(?m)^\s*([A-H])\s*[\.\、\)\:]\s*(.+?)\s*$"
)


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^\s*```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _collapse_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _maybe_json(text: str) -> bool:
    s = text.lstrip()
    return s.startswith("{") and s.rstrip().endswith("}")


def _load_json_best_effort(text: str) -> Optional[Any]:
    s = _strip_code_fences(text)
    try:
        return json.loads(s)
    except Exception:
        pass
    s2 = re.sub(r",\s*([}\]])", r"\1", s)
    try:
        return json.loads(s2)
    except Exception:
        return None


def _as_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip() or None
    return str(v).strip() or None


def _parse_from_json_obj(obj: Any) -> Optional[ParsedExamItem]:
    if not isinstance(obj, dict):
        return None

    stem = (
        _as_str(obj.get("question"))
        or _as_str(obj.get("stem"))
        or _as_str(obj.get("题目"))
        or _as_str(obj.get("题干"))
    )

    options: Dict[str, str] = {}
    raw_options = obj.get("options") or obj.get("选项")
    if isinstance(raw_options, dict):
        for k, v in raw_options.items():
            key = _as_str(k)
            val = _as_str(v)
            if key and val:
                options[key.upper()] = val
    elif isinstance(raw_options, list):
        for idx, item in enumerate(raw_options):
            if isinstance(item, dict):
                k = _as_str(item.get("key") or item.get("option") or item.get("label"))
                v = _as_str(item.get("value") or item.get("text") or item.get("content"))
                if k and v:
                    options[k.upper()] = v
            else:
                val = _as_str(item)
                if val:
                    options[chr(ord("A") + idx)] = val

    answer = (
        _as_str(obj.get("answer"))
        or _as_str(obj.get("答案"))
        or _as_str(obj.get("correct_answer"))
        or _as_str(obj.get("correctAnswer"))
    )

    analysis = (
        _as_str(obj.get("analysis"))
        or _as_str(obj.get("explanation"))
        or _as_str(obj.get("解析"))
        or _as_str(obj.get("题目解析"))
    )

    parse_success = any([stem, options, answer, analysis])
    if not parse_success:
        return None

    warning = None
    if not stem:
        warning = "缺少题干字段"
    elif not answer:
        warning = "缺少答案字段"
    elif not analysis:
        warning = "缺少解析字段"
    elif not options:
        warning = "缺少选项字段"

    return ParsedExamItem(
        question_stem=stem,
        options=options,
        answer=answer,
        analysis=analysis,
        raw_text="",
        parse_success=True,
        parse_warning=warning,
    )


def _extract_sections(text: str) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    s = _collapse_whitespace(_strip_code_fences(text))
    patterns = {
        "stem": r"(?:题干|题目)\s*[:：]\s*",
        "options": r"(?:选项)\s*[:：]\s*",
        "answer": r"(?:答案|参考答案|正确答案)\s*[:：]\s*",
        "analysis": r"(?:解析|答案解析|题目解析)\s*[:：]\s*",
    }
    idxs = {}
    for k, p in patterns.items():
        m = re.search(p, s)
        idxs[k] = m.start() if m else None

    present = {k: v for k, v in idxs.items() if v is not None}
    if not present:
        return None, None, None, None

    ordered = sorted(present.items(), key=lambda kv: kv[1])
    spans = {}
    for i, (k, start) in enumerate(ordered):
        end = ordered[i + 1][1] if i + 1 < len(ordered) else len(s)
        spans[k] = (start, end)

    def cut(k: str) -> Optional[str]:
        if k not in spans:
            return None
        start, end = spans[k]
        prefix = re.search(patterns[k], s[start:end])
        if not prefix:
            return None
        sub = s[start + prefix.end() : end].strip()
        return sub or None

    return cut("stem"), cut("options"), cut("answer"), cut("analysis")


def _parse_options_from_block(block: str) -> Dict[str, str]:
    options: Dict[str, str] = {}
    if not block:
        return options
    for m in _OPTION_RE.finditer(block):
        key = m.group(1).upper()
        val = m.group(2).strip()
        if val:
            options[key] = val
    if options:
        return options

    lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
    for i, ln in enumerate(lines[:8]):
        options[chr(ord("A") + i)] = ln
    return options


def _extract_answer(text: str) -> Optional[str]:
    if not text:
        return None
    s = _collapse_whitespace(text)
    m = re.search(r"(?:答案|参考答案|正确答案)\s*[:：]?\s*([A-H](?:\s*[、,/]\s*[A-H])*)", s, flags=re.I)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    m2 = re.search(r"^\s*([A-H](?:\s*[、,/]\s*[A-H])*)\s*$", s, flags=re.I)
    if m2:
        return re.sub(r"\s+", "", m2.group(1)).upper()
    return None


def parse_exam_item(raw_text: str) -> ParsedExamItem:
    raw_text = raw_text or ""
    cleaned = _collapse_whitespace(_strip_code_fences(raw_text))

    if _maybe_json(cleaned):
        obj = _load_json_best_effort(cleaned)
        parsed = _parse_from_json_obj(obj)
        if parsed is not None:
            return ParsedExamItem(
                question_stem=parsed.question_stem,
                options=parsed.options,
                answer=parsed.answer,
                analysis=parsed.analysis,
                raw_text=cleaned,
                parse_success=True,
                parse_warning=parsed.parse_warning,
            )

    stem, options_block, answer_block, analysis_block = _extract_sections(cleaned)
    options = _parse_options_from_block(options_block or "")
    answer = _extract_answer(answer_block or "") or _extract_answer(cleaned)
    analysis = analysis_block.strip() if analysis_block else None

    parse_success = any([stem, options, answer, analysis])
    warning = None
    if parse_success:
        if not stem:
            warning = "缺少题干字段"
        elif not answer:
            warning = "缺少答案字段"
        elif not analysis:
            warning = "缺少解析字段"
        elif not options:
            warning = "缺少选项字段"

    return ParsedExamItem(
        question_stem=stem,
        options=options,
        answer=answer,
        analysis=analysis,
        raw_text=cleaned,
        parse_success=parse_success,
        parse_warning=warning if parse_success else "未能可靠解析四要素",
    )


def format_exam_item_for_judge(item: ParsedExamItem) -> str:
    parts = []
    if item.question_stem:
        parts.append("【题干】\n" + item.question_stem.strip())
    if item.options:
        opts = "\n".join(
            f"{k}. {v}".strip() for k, v in sorted(item.options.items())
        )
        parts.append("【选项】\n" + opts)
    if item.answer:
        parts.append("【答案】\n" + item.answer.strip())
    if item.analysis:
        parts.append("【解析】\n" + item.analysis.strip())
    if not parts:
        return item.raw_text
    return "\n\n".join(parts).strip()

