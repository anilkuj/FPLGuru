"""Shared serving-time feature-row assembly for the xP models."""
from __future__ import annotations

from fplguru_ml.features import ADV_EXTRA_FEATURES, feature_row_from_history


def to_adv_row(basic_row: dict) -> dict:
    """Extend a 9-feature Basic row with the 5 expected-goals features (0.0 until
    `player_xg` is FPL id-mapped)."""
    return {**basic_row, **{k: 0.0 for k in ADV_EXTRA_FEATURES}}


def adv_feature_row(history, *, was_home: bool, value: float,
                    opp_conceded_to_pos_5: float) -> dict | None:
    """Advanced (14-feature) row from a player's prior appearances, or None if
    the history is too thin (< 3 appearances). The 5 expected-goals features are
    0.0 until `player_xg` carries an FPL id mapping; the GBRT then predicts from
    the 9 shared FPL features."""
    fr = feature_row_from_history(
        history, was_home=was_home, value=value,
        opp_conceded_to_pos_5=opp_conceded_to_pos_5,
    )
    if fr is None:
        return None
    return to_adv_row(fr)
