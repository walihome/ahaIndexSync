# infra/llm.py
# 通用 LLM 调用，模型/endpoint 由 config 传入

import json
import time
from openai import OpenAI
from pipeline.config_loader import PromptConfig


def _safe_temperature(temperature: float, err_str: str) -> float | None:
    """If the model rejects the temperature, fall back to 1.0 (required by some models like kimi-k2.5)."""
    if "invalid temperature" in err_str and temperature != 1.0:
        return 1.0
    return None


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
    temperature = config.temperature

    for attempt in range(config.max_retries):
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=config.model,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            result["model"] = config.model
            time.sleep(config.request_interval)
            return result

        except Exception as e:
            err_str = str(e)

            fallback_temp = _safe_temperature(temperature, err_str)
            if fallback_temp is not None:
                print(f"  ⚠️ 模型不支持 temperature={temperature}，回退到 {fallback_temp}")
                temperature = fallback_temp
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

    for _retry in range(2):
        try:
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                model=model,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            err_str = str(e)
            fallback_temp = _safe_temperature(temperature, err_str)
            if fallback_temp is not None:
                print(f"  ⚠️ 模型不支持 temperature={temperature}，回退到 {fallback_temp}")
                temperature = fallback_temp
                continue
            print(f"⚠️ LLM 调用失败: {e}")
            return None
    return None
