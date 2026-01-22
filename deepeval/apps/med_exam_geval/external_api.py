from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class ExternalAPIConfig:
    base_url: str
    api_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    timeout_seconds: float = 60.0
    max_retries: int = 2
    backoff_seconds: float = 1.0


def load_external_api_config_from_env(
    *,
    base_url_env: str = "EXTERNAL_LLM_API_BASE_URL",
    api_key_env: str = "EXTERNAL_LLM_API_KEY",
    headers_env: str = "EXTERNAL_LLM_API_HEADERS",
    timeout_env: str = "EXTERNAL_LLM_TIMEOUT_SECONDS",
    retries_env: str = "EXTERNAL_LLM_MAX_RETRIES",
) -> ExternalAPIConfig:
    base_url = (os.getenv(base_url_env) or "").strip()
    if not base_url:
        raise ValueError(f"Missing {base_url_env}")
    api_key = (os.getenv(api_key_env) or "").strip() or None
    headers_raw = (os.getenv(headers_env) or "").strip() or None
    headers: Optional[Dict[str, str]] = None
    if headers_raw:
        parsed = json.loads(headers_raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"{headers_env} must be a JSON object")
        headers = {str(k): str(v) for k, v in parsed.items()}
    timeout = float((os.getenv(timeout_env) or "60").strip())
    retries = int((os.getenv(retries_env) or "2").strip())
    return ExternalAPIConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        headers=headers,
        timeout_seconds=timeout,
        max_retries=retries,
    )


def build_headers(cfg: ExternalAPIConfig) -> Dict[str, str]:
    headers: Dict[str, str] = {
        "Content-Type": "application/json",
    }
    if cfg.api_key:
        headers["Authorization"] = f"Bearer {cfg.api_key}"
    if cfg.headers:
        headers.update(cfg.headers)
    return headers


def post_json_with_retries(
    *,
    cfg: ExternalAPIConfig,
    url: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    headers = build_headers(cfg)
    last_err: Optional[Exception] = None
    for attempt in range(max(1, cfg.max_retries + 1)):
        try:
            resp = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=cfg.timeout_seconds,
            )
            if 200 <= resp.status_code < 300:
                return resp.json()
            if resp.status_code in (408, 429) or 500 <= resp.status_code < 600:
                raise RuntimeError(
                    f"HTTP {resp.status_code}: {resp.text[:2000]}"
                )
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:2000]}")
        except Exception as e:
            last_err = e
            if attempt >= cfg.max_retries:
                break
            time.sleep(cfg.backoff_seconds * (2**attempt))
    raise RuntimeError(f"External API request failed: {last_err}")

