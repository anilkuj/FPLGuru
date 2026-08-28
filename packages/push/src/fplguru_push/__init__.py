"""Pure Web Push helpers — no DB, no network, no crypto."""
from __future__ import annotations

from typing import Any

__all__ = ["pending_push_targets", "notification_payload"]


def notification_payload(alert: dict[str, Any]) -> dict:
    return {
        "title": alert["title"],
        "body": alert.get("body", ""),
        "tag": f"fplguru-{alert['id']}",
        "url": "/alerts",
    }


def pending_push_targets(alerts: list[dict[str, Any]], subscriptions: list[dict[str, Any]],
                         *, min_priority: int = 0) -> list[dict]:
    if not subscriptions:
        return []
    out: list[dict] = []
    for a in alerts:
        if a.get("suppressed") or a.get("seen") or a.get("pushed"):
            continue
        if a.get("priority", 0) < min_priority:
            continue
        for s in subscriptions:
            out.append({"subscription": s, "alert": a, "payload": notification_payload(a)})
    return out
