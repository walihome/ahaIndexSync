# infra/llm.py
# 通用 LLM 调用，模型/endpoint 由 config 传入

import json
import time
from openai import OpenAI
from pipeline.config_loader import PromptConfig

_MODEL_TEMP_OVERRIDE: dict[str, float] = {}


def _resolve_temperature(model: str, temperature: float) -> float:
    if model in _MODEL_TEMP_OVERRIDE:
        return _MODEL_TEMP_OVERRIDE[model]
    return temperature


def _handle_invalid_temperature(model: str, temperature: float, err_str: str) -> float | None:
    if "invalid temperature" in err_str and temperature != 1.0:
        _MODEL_TEMP_OVERRIDE[model] = 1.0
        print(f"  ⚠️ 模型 {model} 不支持 temperature={temperature}，已全局回退到 1.0")
        return 1.0
    return None


def _model_extra_body(model: str) -> dict:
    """
    为特定模型注入额外参数。kimi-k2.5 / kimi-k2.6 默认开启 thinking，
    会往输出里掺 reasoning 内容，破坏 response_format=json_object 解析，
    必须显式关闭。
    """
    if model.startswith("kimi-k2.5") or model.startswith("kimi-k2.6"):
        return {"thinking": {"type": "disabled"}}
    return {}


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
    temperature = _resolve_temperature(config.model, config.temperature)
    extra_body = _model_extra_body(config.model)

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
                extra_body=extra_body,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise ValueError("LLM 返回空内容（疑似内容过滤或 thinking 未关闭）")
            result = json.loads(content)
            result["model"] = config.model
            time.sleep(config.request_interval)
            return result

        except Exception as e:
            err_str = str(e)

            fallback_temp = _handle_invalid_temperature(config.model, temperature, err_str)
            if fallback_temp is not None:
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
    temperature = _resolve_temperature(model, temperature)
    extra_body = _model_extra_body(model)

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
                extra_body=extra_body,
            )
            content = response.choices[0].message.content or ""
            if not content.strip():
                raise ValueError("LLM 返回空内容（疑似内容过滤或 thinking 未关闭）")
            return json.loads(content)
        except Exception as e:
            err_str = str(e)
            fallback_temp = _handle_invalid_temperature(model, temperature, err_str)
            if fallback_temp is not None:
                temperature = fallback_temp
                continue
            print(f"⚠️ LLM 调用失败: {e}")
            return None
    return None
