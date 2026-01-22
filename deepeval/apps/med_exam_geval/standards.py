from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExamStandard:
    name: str
    text: str


DEFAULT_STANDARD = ExamStandard(
    name="执业医师试题标准（通用）",
    text="\n".join(
        [
            "你是执业医师考试命题与阅卷专家，负责评审一份“题目+答案+解析”的质量。",
            "判定标准：",
            "1. 题干：信息充分、表述清晰、无明显歧义；不引入与作答无关的噪声信息。",
            "2. 选项：同一维度、互斥、覆盖合理；干扰项具有迷惑性但不靠语病或陷阱；不出现明显重复或无意义选项。",
            "3. 答案：单选题必须且只能有一个最佳答案；答案必须与题干和选项一致；不得出现“答案不存在/超出选项”。",
            "4. 解析：应说明为什么正确选项正确、其他选项为什么错；医学事实应符合通用临床知识与常见指南原则；不得出现危险或严重错误建议。",
            "5. 可用性：四要素齐全（题干/选项/答案/解析），结构清晰，能够直接进入题库使用。",
            "扣分规则：",
            "- 若出现可能导致严重不良后果的医学错误或禁忌处理，给予强惩罚（低分封顶）。",
            "- 若格式缺失导致无法判定答案或无法入库，给予强惩罚。",
            "输出要求：评估时只根据提供的内容判断，不要臆测缺失信息。",
        ]
    ),
)


def build_context(
    standard: ExamStandard = DEFAULT_STANDARD,
    *,
    question_type: Optional[str] = None,
    subject: Optional[str] = None,
) -> str:
    extra = []
    if question_type:
        extra.append(f"题型：{question_type}")
        if question_type.lower() in {"single_choice", "single", "sc"}:
            extra.append("题型约束：单选题答案只能是一个选项字母。")
        if question_type.lower() in {"multi_choice", "multi", "mc"}:
            extra.append("题型约束：多选题答案由多个选项字母组成。")
    if subject:
        extra.append(f"学科方向：{subject}")
    if extra:
        return standard.text + "\n\n" + "\n".join(extra)
    return standard.text

