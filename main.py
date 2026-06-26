from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import AstrBotConfig, logger
from astrbot.core.provider.entites import LLMResponse


@register(
    "astrbot_plugin_token_logger",
    "Felis Abyssalis & Abyss AI",
    "将每次 LLM 调用的 token 用量记录到日志中",
    "1.1.0",
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
    # Unified token extraction — handles both OpenAI and Anthropic paths
    # ------------------------------------------------------------------

    def _extract_tokens(self, resp: LLMResponse):
        """Return token usage data from whichever source is available.

        Priority:
          1. resp.raw_completion.usage (OpenAI-style — model name lives here)
          2. resp.usage (AstrBot normalized TokenUsage — Anthropic fallback)
          3. None — no usage data available
        """

        # --- Path 1: OpenAI-style raw_completion (model lives on completion obj) ---
        completion = getattr(resp, "raw_completion", None)
        if completion is not None and getattr(completion, "usage", None) is not None:
            raw_usage = completion.usage
            prompt = getattr(raw_usage, "prompt_tokens", 0) or 0
            comp = getattr(raw_usage, "completion_tokens", 0) or 0
            total = getattr(raw_usage, "total_tokens", 0) or (prompt + comp)

            cached = 0
            if self._cache_aware:
                details = getattr(raw_usage, "prompt_tokens_details", None)
                if details is not None:
                    cached = getattr(details, "cached_tokens", 0) or 0

            reasoning = 0
            details = getattr(raw_usage, "completion_tokens_details", None)
            if details is not None:
                reasoning = getattr(details, "reasoning_tokens", 0) or 0

            model = getattr(completion, "model", "unknown")
            finish = "unknown"
            choices = getattr(completion, "choices", None)
            if choices:
                finish = getattr(choices[0], "finish_reason", "unknown") or "unknown"

            normal = prompt - cached

            result = {
                "input": prompt,
                "input_normal": normal,
                "input_cache_read": cached,
                "input_cache_write": 0,  # OpenAI has no cache write concept
                "output": comp,
                "cached": cached,
                "total": total,
                "model": model,
                "finish": finish,
                "source": "raw_completion",
            }
            if reasoning > 0:
                result["reasoning"] = reasoning
            return result

        # --- Path 2: AstrBot normalized TokenUsage (Anthropic fallback) ---
        usage = getattr(resp, "usage", None)
        if usage is not None and hasattr(usage, "output"):
            input_other = getattr(usage, "input_other", 0) or 0
            input_cached = getattr(usage, "input_cached", 0) or 0
            output = getattr(usage, "output", 0) or 0
            input_total = input_other + input_cached
            total = input_total + output

            # Try to get model from the response id or fallback
            model = getattr(resp, "model", None) or "unknown"

            return {
                "input": input_total,
                "input_normal": input_other,
                "input_cache_read": input_cached,
                "input_cache_write": 0,  # AstrBot drops cache_creation_input_tokens
                "output": output,
                "cached": input_cached if self._cache_aware else 0,
                "total": total,
                "model": model,
                "finish": "unknown",
                "source": "normalized",
            }

        # --- No usage data ---
        return None

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_tokens(self, data: dict, has_thinking: bool):
        parts = [f"[Token 用量记录] 🏷️ model = {data['model']}"]

        # Input breakdown
        has_cache = data["input_cache_read"] > 0 or data["input_cache_write"] > 0
        if has_cache:
            in_details = [str(data["input_normal"])]
            if data["input_cache_read"] > 0:
                in_details.append(f"{data['input_cache_read']} cache read")
            if data["input_cache_write"] > 0:
                in_details.append(f"{data['input_cache_write']} cache write")
            parts.append(f"in = {data['input']} ({' + '.join(in_details)})")
        else:
            parts.append(f"in = {data['input']}")

        # Output
        reasoning = data.get("reasoning", 0)
        if reasoning > 0:
            parts.append(f"out = {data['output']} (reasoning = {reasoning})")
        elif has_thinking:
            parts.append(f"out = {data['output']} (thinking = yes)")
        else:
            parts.append(f"out = {data['output']}")

        parts.append(f"total = {data['total']}")

        if data["finish"] != "unknown":
            parts.append(f"finish = {data['finish']}")

        logger.info(" | ".join(parts))

    def _log_cost(self, data: dict):
        normal = data["input_normal"]
        cache_read = data["input_cache_read"]
        cache_write = data["input_cache_write"]

        normal_fee = normal * self._input_cost / 1_000_000
        cache_read_fee = cache_read * self._cached_cost / 1_000_000
        # Cache write costs the same as normal input
        cache_write_fee = cache_write * self._input_cost / 1_000_000
        output_fee = data["output"] * self._output_cost / 1_000_000
        total_fee = normal_fee + cache_read_fee + cache_write_fee + output_fee

        formula_parts = [f"{normal} * ${self._input_cost}/M"]
        if cache_read > 0:
            formula_parts.append(f"{cache_read} * ${self._cached_cost}/M")
        if cache_write > 0:
            formula_parts.append(f"{cache_write} * ${self._input_cost}/M")
        formula_parts.append(f"{data['output']} * ${self._output_cost}/M")

        formula = " + ".join(formula_parts)
        logger.info(f"[Token 用量记录] 💰 cost = ${total_fee:.6f} ({formula} = ${total_fee:.6f})")

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp: LLMResponse):
        if not self._enabled and not self._cost_enabled:
            return

        data = self._extract_tokens(resp)

        if data is None:
            if self._enabled:
                logger.info("[Token 用量记录] ⚠️ 本次调用未返回 token 用量信息")
            return

        has_thinking = bool(getattr(resp, "reasoning_content", None))

        if self._enabled:
            self._log_tokens(data, has_thinking)

        if self._cost_enabled:
            self._log_cost(data)
