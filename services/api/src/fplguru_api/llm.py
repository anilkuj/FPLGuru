"""Budget-guarded Gemini calls for the API. Returns None (-> caller uses a template)
whenever the LLM is unconfigured, over the monthly cap, or errors."""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fplguru_core.models import LlmCall
from fplguru_core.settings import get_settings
from fplguru_llm import GeminiClient, LlmError, estimate_cost

logger = logging.getLogger("fplguru.api.llm")


async def _month_spend(db: AsyncSession) -> float:
    start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return float((await db.execute(
        select(func.coalesce(func.sum(LlmCall.est_cost_usd), 0.0))
        .where(LlmCall.created_at >= start)
    )).scalar() or 0.0)


async def generate_within_budget(db: AsyncSession, feature: str, prompt: str, *,
                                 max_output_tokens: int = 200) -> str | None:
    s = get_settings()
    if not s.gemini_api_key:
        return None
    if await _month_spend(db) >= s.llm_monthly_usd_cap:
        db.add(LlmCall(feature=feature, model=s.gemini_model, prompt_tokens=0,
                       completion_tokens=0, est_cost_usd=0.0, status="skipped"))
        await db.commit()
        return None
    client = GeminiClient(s.gemini_api_key, base=s.gemini_base, model=s.gemini_model)
    try:
        text, pt, ct = await client.generate(prompt, max_output_tokens=max_output_tokens)
        db.add(LlmCall(feature=feature, model=s.gemini_model, prompt_tokens=pt,
                       completion_tokens=ct,
                       est_cost_usd=estimate_cost(s.gemini_model, pt, ct), status="ok"))
        await db.commit()
        return text.strip()
    except LlmError:
        logger.warning("llm call failed for %s", feature, exc_info=True)
        db.add(LlmCall(feature=feature, model=s.gemini_model, prompt_tokens=0,
                       completion_tokens=0, est_cost_usd=0.0, status="error"))
        await db.commit()
        return None
    finally:
        await client.aclose()
