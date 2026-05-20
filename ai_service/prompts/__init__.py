"""Prompt 配置加载：把 prompts/*.yaml 合并为一个 dict，供 LLMClient 取用。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_PROMPT_DIR = Path(__file__).parent


@lru_cache
def _load_all() -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for yaml_file in sorted(_PROMPT_DIR.glob("*.yaml")):
        with yaml_file.open("r", encoding="utf-8") as f:
            merged.update(yaml.safe_load(f) or {})
    return merged


def get_prompt(name: str) -> dict[str, str]:
    """取某个 prompt 配置块（含 system / user_template 两个键）。"""
    prompts = _load_all()
    if name not in prompts:
        raise KeyError(f"未找到 prompt 配置: {name}（可用: {list(prompts)}）")
    return prompts[name]


__all__ = ["get_prompt"]
