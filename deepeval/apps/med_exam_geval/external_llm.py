from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel

from deepeval.models import DeepEvalBaseLLM

from deepeval.apps.med_exam_geval.external_api import (
    ExternalAPIConfig,
    load_external_api_config_from_env,
    post_json_with_retries,
)


@dataclass(frozen=True)
class ExternalOpenAICompatibleConfig:
    model: str
    endpoint_path: str = "/v1/chat/completions"
    temperature: float = 0.0
    extra_body: Optional[Dict[str, Any]] = None


class ExternalOpenAICompatibleLLM(DeepEvalBaseLLM):
    def __init__(
        self,
        *,
        model: str,
        api_cfg: Optional[ExternalAPIConfig] = None,
        oa_cfg: Optional[ExternalOpenAICompatibleConfig] = None,
    ):
        self.api_cfg = api_cfg or load_external_api_config_from_env()
        self.oa_cfg = oa_cfg or ExternalOpenAICompatibleConfig(model=model)
        super().__init__(model)

    def load_model(self, *args, **kwargs) -> "ExternalOpenAICompatibleLLM":
        return self

    def get_model_name(self, *args, **kwargs) -> str:
        return self.name

    def supports_log_probs(self) -> Union[bool, None]:
        return None

    def supports_json_mode(self) -> Union[bool, None]:
        return None

    def generate(
        self, prompt: str, schema: Optional[BaseModel] = None, **kwargs
    ):
        content = self._call_openai_chat(prompt)
        if schema is not None:
            parsed = _trim_and_load_json(content)
            return schema.model_validate(parsed)
        return content

    async def a_generate(
        self, prompt: str, schema: Optional[BaseModel] = None, **kwargs
    ):
        return self.generate(prompt, schema=schema, **kwargs)

    def _call_openai_chat(self, prompt: str) -> str:
        url = self.api_cfg.base_url.rstrip("/") + self.oa_cfg.endpoint_path
        body: Dict[str, Any] = {
            "model": self.oa_cfg.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.oa_cfg.temperature,
        }
        if self.oa_cfg.extra_body:
            body.update(self.oa_cfg.extra_body)
        data = post_json_with_retries(cfg=self.api_cfg, url=url, payload=body)
        try:
            return str(data["choices"][0]["message"]["content"])
        except Exception:
            raise RuntimeError(
                "Invalid OpenAI-compatible response; expected choices[0].message.content"
            )


def _trim_and_load_json(s: str) -> Any:
    s = (s or "").strip()
    s = s.replace("\r\n", "\n").replace("\r", "\n").strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1].strip() if "```" in s[3:] else s
    try:
        return json.loads(s)
    except Exception:
        start = s.find("{")
        end = s.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(s[start : end + 1])
        raise
