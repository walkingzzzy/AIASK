

_factor_llm_provider: Optional[FactorLLMProvider] = None


def get_factor_llm_provider() -> FactorLLMProvider:
    """返回全局 provider 单例。"""

    global _factor_llm_provider
    if _factor_llm_provider is None or bool(getattr(_factor_llm_provider, "_closed", False)):
        _factor_llm_provider = FactorLLMProvider()
    return _factor_llm_provider


async def close_factor_llm_provider() -> None:
    global _factor_llm_provider
    provider = _factor_llm_provider
    _factor_llm_provider = None
    if provider is None:
        return
    await provider.close()
