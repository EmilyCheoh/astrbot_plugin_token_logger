from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.core.provider.entites import LLMResponse


@register(
    "astrbot_plugin_token_logger",
    "Felis Abyssalis & Abyss AI",
    "将每次 LLM 调用的 token 用量记录到日志中",
    "1.0.0",
    "https://github.com/EmilyCheoh/astrbot_plugin_token_logger",
)
class TokenLogger(Star):

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)

        self._enabled = bool(config.get("enabled", True))
        self._cost_enabled = bool(config.get("cost_enabled", False))
        self._cache_aware = bool(config.get("cache_aware", False))

        self._input_cost = float(config.get("input_cost_per_million", 2.50))
        self._output_cost = float(config.get("output_cost_per_million", 10.00))
        self._cached_cost = float(config.get("cached_input_cost_per_million", 1.25))

        self._show_temperature = bool(config.get("show_temperature", False))
        self._show_top_p = bool(config.get("show_top_p", False))

        logger.info(
            f"[Token 用量记录] 💜 初始化完成 "
            f"(enabled={self._enabled}, cost={self._cost_enabled}, "
            f"cache_aware={self._cache_aware}, "
            f"input=${self._input_cost}/M, output=${self._output_cost}/M, "
            f"cached=${self._cached_cost}/M)"
        )

    # ------------------------------------------------------------------

    def _get_cached_tokens(self, usage) -> int:
        if not self._cache_aware:
            return 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is None:
            return 0
        return getattr(details, "cached_tokens", 0) or 0

    def _get_reasoning_tokens(self, usage) -> int:
        details = getattr(usage, "completion_tokens_details", None)
        if details is None:
            return 0
        return getattr(details, "reasoning_tokens", 0) or 0

    def _get_finish_reason(self, completion) -> str:
        if not completion.choices:
            return "unknown"
        return getattr(completion.choices[0], "finish_reason", "unknown")

    # ------------------------------------------------------------------

    def _log_tokens(self, completion, usage, cached: int, reasoning: int, finish: str, has_thinking: bool):
        model = getattr(completion, "model", "unknown")
        parts = [f"[Token 用量记录] 🏷️ model = {model}"]

        if cached > 0:
            parts.append(f"input = {usage.prompt_tokens} (cached = {cached})")
        else:
            parts.append(f"input = {usage.prompt_tokens}")

        if reasoning > 0:
            parts.append(f"output = {usage.completion_tokens} (reasoning = {reasoning})")
        elif has_thinking:
            parts.append(f"output = {usage.completion_tokens} (thinking = yes)")
        else:
            parts.append(f"output = {usage.completion_tokens}")

        parts.append(f"total = {usage.total_tokens}")
        parts.append(f"finish reason = {finish}")

        if self._show_temperature:
            temp = getattr(completion, "temperature", None)
            if temp is not None:
                parts.append(f"temperature = {temp}")

        if self._show_top_p:
            top_p = getattr(completion, "top_p", None)
            if top_p is not None:
                parts.append(f"top_p = {top_p}")

        logger.info(" | ".join(parts))

    def _log_cost(self, usage, cached: int):
        uncached = usage.prompt_tokens - cached

        uncached_fee = uncached * self._input_cost / 1_000_000
        cached_fee = cached * self._cached_cost / 1_000_000
        output_fee = usage.completion_tokens * self._output_cost / 1_000_000
        total_fee = uncached_fee + cached_fee + output_fee

        formula_parts = [f"{uncached} * ${self._input_cost}/M"]
        if cached > 0:
            formula_parts.append(f"{cached} * ${self._cached_cost}/M")
        formula_parts.append(f"{usage.completion_tokens} * ${self._output_cost}/M")

        formula = " + ".join(formula_parts)
        logger.info(f"[Token 用量记录] 💰 cost = ${total_fee:.6f} ({formula} = ${total_fee:.6f})")

    # ------------------------------------------------------------------

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        if not self._enabled and not self._cost_enabled:
            return

        completion = resp.raw_completion
        if completion is None or completion.usage is None:
            if self._enabled:
                logger.info("[Token 用量记录] ⚠️ 本次调用未返回 token 用量信息")
            return

        usage = completion.usage
        finish = self._get_finish_reason(completion)
        cached = self._get_cached_tokens(usage)
        reasoning = self._get_reasoning_tokens(usage)
        has_thinking = bool(getattr(resp, "reasoning_content", None))

        if self._enabled:
            self._log_tokens(completion, usage, cached, reasoning, finish, has_thinking)

        if self._cost_enabled:
            self._log_cost(usage, cached)
