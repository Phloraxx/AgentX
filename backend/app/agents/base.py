"""LLM factory — one function, three models, single OpenCode Go endpoint."""

from langchain_openai import ChatOpenAI
from app.config import settings
# Cache is naturally bounded: at most one entry per (model_key, temperature, max_tokens) combo.
# In practice, only 3 agent keys (host, saboteur, evaluator) are used, so this stays tiny.
_llm_cache: dict[str, ChatOpenAI] = {}


def make_llm(
    model_key: str,
    *,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> ChatOpenAI:
    """Create or return cached ChatOpenAI instance pointed at OpenCode Go.

    Args:
        model_key: One of "host", "saboteur", "evaluator".
        temperature: Override config default.
        max_tokens: Override config default.
    """
    cache_key = f"{model_key}:{temperature}:{max_tokens}"
    if cache_key in _llm_cache:
        return _llm_cache[cache_key]

    model_id = settings.models[model_key]
    temp_map = {
        "host": settings.host_temperature,
        "saboteur": settings.saboteur_temperature,
        "evaluator": settings.evaluator_temperature,
    }
    tokens_map = {
        "host": settings.host_max_tokens,
        "saboteur": settings.saboteur_max_tokens,
        "evaluator": settings.evaluator_max_tokens,
    }

    llm = ChatOpenAI(
        model=model_id,
        api_key=settings.opencode_api_key,
        base_url=settings.opencode_base_url,
        temperature=temperature if temperature is not None else temp_map.get(model_key, 0.4),
        max_tokens=max_tokens if max_tokens is not None else tokens_map.get(model_key, 1500),
        timeout=60,
        max_retries=2,
    )
    _llm_cache[cache_key] = llm
    return llm


def get_host_llm() -> ChatOpenAI:
    return make_llm("host")


def get_saboteur_llm() -> ChatOpenAI:
    return make_llm("saboteur")


def get_evaluator_llm() -> ChatOpenAI:
    return make_llm("evaluator")
