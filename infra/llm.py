# infra/llm.py
# 通用 LLM 调用，模型/endpoint 由 config 传入

import json
import time
from openai import OpenAI
from pipeline.config_loader import PromptConfig

THINKING_MODELS = {"kimi-k2.5", "kimi-k2-thinking", "kimi-k2-thinking-turbo"}


def _is_thinking_model(model: str) -> bool:
    return model in THINKING_MODELS


def _build_params(model: str, temperature: float) -> dict:
    """Thinking models (kimi-k2.5 etc.) don't accept custom temperature; disable thinking for pure JSON output."""
    if _is_thinking_model(model):
        return {"thinking": {"type": "disabled"}}
    return {"temperature": temperature}


def call_llm(
    prompt: str,
    config: PromptConfig,
    system_prompt: str = "You only output JSON.",
    api_key: str = "",
) -> dict | None:
    if not api_key:
        print("⚠️ LLM API key 未设置")
        return None

    client = OpenAI(base_url=config.model_base_url, api_key=api_key)
    extra_params = _build_params(config.model, config.temperature)

    for attempt in range(config.max_retries):
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=config.model,
                response_format={"type": "json_object"},
                **extra_params,
            )
            result = json.loads(response.choices[0].message.content)
            result["model"] = config.model
            time.sleep(config.request_interval)
            return result

        except Exception as e:
            err_str = str(e)

            if "invalid temperature" in err_str and "temperature" in extra_params:
                print(f"  ⚠️ 模型不支持自定义 temperature，切换为 thinking model 模式重试")
                extra_params = {"thinking": {"type": "disabled"}}
                continue

            is_rate_limit = "429" in err_str or "overloaded" in err_str
            if is_rate_limit and attempt < config.max_retries - 1:
                wait = 2 ** (attempt + 2)
                print(f"  ⏳ 限流，{wait}s 后重试 ({attempt + 1}/{config.max_retries})")
                time.sleep(wait)
                continue

            print(f"⚠️ LLM 调用失败: {e}")
            return None

    return None


def call_llm_raw(
    prompt: str,
    model: str,
    base_url: str,
    api_key: str,
    system_prompt: str = "You only output JSON.",
    temperature: float = 0.1,
    timeout: int = 30,
) -> dict | None:
    """不依赖 PromptConfig 的简化调用，用于 archive 等场景。"""
    if not api_key:
        return None

    client = OpenAI(base_url=base_url, api_key=api_key)
    extra_params = _build_params(model, temperature)

    for _retry in range(2):
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                response_format={"type": "json_object"},
                **extra_params,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            err_str = str(e)
            if "invalid temperature" in err_str and "temperature" in extra_params:
                print(f"  ⚠️ 模型不支持自定义 temperature，切换为 thinking model 模式重试")
                extra_params = {"thinking": {"type": "disabled"}}
                continue
            print(f"⚠️ LLM 调用失败: {e}")
            return None
    return None
