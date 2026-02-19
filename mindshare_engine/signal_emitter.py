"""
signal_emitter.py - Delivers virality signals to external bots via webhooks.

Supports any webhook consumer (Telegram bot, Discord bot, custom service).
Handles cooldown per narrative to avoid spam, and formats signals as
structured JSON payloads with human-readable summaries.

Webhook payload schema:
{
    "event":      "virality_signal",
    "timestamp":  "ISO-8601",
    "signals":    [{ narrative_id, virality_score, components, label, domain, ... }],
    "meta":       { window_time, total_scored, signals_emitted }
}
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta
from loguru import logger

from mindshare_engine import config
from mindshare_engine.database import execute

try:
    import urllib.request
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


class SignalEmitter:

    def __init__(self) -> None:
        self._webhook_url = config.BOT_WEBHOOK_URL
        self._webhook_secret = config.BOT_WEBHOOK_SECRET
        self._cooldown_minutes = config.BOT_COOLDOWN_MINUTES
        self._max_per_window = config.BOT_MAX_SIGNALS_PER_WINDOW
        self._signal_threshold = config.VIRALITY_SIGNAL_THRESHOLD
        self._alert_threshold = config.VIRALITY_ALERT_THRESHOLD

    def emit(self, scored: list[dict], window_time: datetime) -> dict:
        """
        Filter scored narratives above threshold, apply cooldown, and emit to webhook.
        Returns stats dict.
        """
        above_threshold = [
            s for s in scored if s["virality_score"] >= self._signal_threshold
        ]

        if not above_threshold:
            return {"emitted": 0, "skipped_cooldown": 0, "skipped_threshold": len(scored)}

        after_cooldown = self._apply_cooldown(above_threshold, window_time)
        to_emit = after_cooldown[:self._max_per_window]

        signals_payload = [self._format_signal(s) for s in to_emit]

        payload = {
            "event": "virality_signal",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals": signals_payload,
            "meta": {
                "window_time": window_time.isoformat(),
                "total_scored": len(scored),
                "signals_emitted": len(signals_payload),
                "threshold": self._signal_threshold,
            },
        }

        webhook_ok = self._send_webhook(payload)

        if webhook_ok:
            self._mark_emitted(to_emit, window_time)

        stats = {
            "emitted": len(to_emit),
            "skipped_cooldown": len(above_threshold) - len(after_cooldown),
            "skipped_threshold": len(scored) - len(above_threshold),
            "webhook_delivered": webhook_ok,
        }
        logger.info(f"Signal emission: {stats}")
        return stats

    def get_latest_signals(self, limit: int = 20, min_score: float = 0.0) -> list[dict]:
        """Query the most recent virality signals (for API/polling consumers)."""
        rows = execute("""
            SELECT narrative_id, window_time, virality_score, components,
                   state, label, primary_domain, tweet_count, unique_authors,
                   top_terms, emitted
            FROM virality_signals
            WHERE virality_score >= %s
            ORDER BY window_time DESC, virality_score DESC
            LIMIT %s
        """, (min_score, limit), fetch=True) or []

        return [
            {
                "narrative_id": str(r[0]),
                "window_time": r[1].isoformat() if r[1] else None,
                "virality_score": r[2],
                "components": r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}"),
                "state": r[4],
                "label": r[5],
                "primary_domain": r[6],
                "tweet_count": r[7],
                "unique_authors": r[8],
                "top_terms": r[9] if isinstance(r[9], list) else json.loads(r[9] or "[]"),
                "emitted": r[10],
            }
            for r in rows
        ]

    def get_narrative_trend(self, narrative_id: str, windows: int = 12) -> list[dict]:
        """Return score history for a specific narrative across recent windows."""
        rows = execute("""
            SELECT window_time, virality_score, components, tweet_count, unique_authors
            FROM virality_signals
            WHERE narrative_id = %s
            ORDER BY window_time DESC
            LIMIT %s
        """, (narrative_id, windows), fetch=True) or []

        return [
            {
                "window_time": r[0].isoformat() if r[0] else None,
                "virality_score": r[1],
                "components": r[2] if isinstance(r[2], dict) else json.loads(r[2] or "{}"),
                "tweet_count": r[3],
                "unique_authors": r[4],
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Cooldown logic
    # ------------------------------------------------------------------

    def _apply_cooldown(self, signals: list[dict], window_time: datetime) -> list[dict]:
        """Filter out narratives that were emitted within the cooldown period."""
        cutoff = window_time - timedelta(minutes=self._cooldown_minutes)

        recently_emitted = execute("""
            SELECT DISTINCT narrative_id FROM virality_signals
            WHERE emitted = TRUE AND emitted_at > %s
        """, (cutoff.isoformat(),), fetch=True) or []

        cooldown_ids = {str(r[0]) for r in recently_emitted}
        return [s for s in signals if s["narrative_id"] not in cooldown_ids]

    # ------------------------------------------------------------------
    # Webhook delivery
    # ------------------------------------------------------------------

    def _send_webhook(self, payload: dict) -> bool:
        """POST payload to configured webhook URL."""
        if not self._webhook_url:
            logger.debug("No webhook URL configured — signals stored but not pushed")
            return False

        if not _HAS_URLLIB:
            logger.error("urllib not available for webhook delivery")
            return False

        body = json.dumps(payload).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        if self._webhook_secret:
            sig = hmac.new(
                self._webhook_secret.encode(),
                body,
                hashlib.sha256,
            ).hexdigest()
            headers["X-Mindshare-Signature"] = sig

        req = urllib.request.Request(
            self._webhook_url,
            data=body,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.getcode()
                if status < 300:
                    logger.info(f"Webhook delivered: HTTP {status}")
                    return True
                else:
                    logger.warning(f"Webhook non-2xx response: HTTP {status}")
                    return False
        except Exception as e:
            logger.error(f"Webhook delivery failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Signal formatting
    # ------------------------------------------------------------------

    def _format_signal(self, signal: dict) -> dict:
        """Build a clean, bot-friendly signal payload."""
        score = signal["virality_score"]
        tier = "ALERT" if score >= self._alert_threshold else "SIGNAL"
        bar = self._score_bar(score)

        summary = (
            f"[{tier}] {signal.get('label', 'unknown')} "
            f"| {signal.get('primary_domain', '?')} "
            f"| Score: {score:.2f} {bar}"
        )

        return {
            "narrative_id": signal["narrative_id"],
            "tier": tier,
            "virality_score": score,
            "components": signal.get("components", {}),
            "label": signal.get("label"),
            "primary_domain": signal.get("primary_domain"),
            "state": signal.get("state"),
            "tweet_count": signal.get("tweet_count", 0),
            "unique_authors": signal.get("unique_authors", 0),
            "top_terms": signal.get("top_terms", []),
            "summary": summary,
        }

    @staticmethod
    def _score_bar(score: float, width: int = 10) -> str:
        """Visual bar representation of score."""
        filled = round(score * width)
        return "[" + "#" * filled + "-" * (width - filled) + "]"

    # ------------------------------------------------------------------
    # Mark emitted
    # ------------------------------------------------------------------

    def _mark_emitted(self, signals: list[dict], window_time: datetime) -> None:
        """Flag signals as emitted in the DB."""
        for s in signals:
            try:
                execute("""
                    UPDATE virality_signals
                    SET emitted = TRUE, emitted_at = NOW()
                    WHERE narrative_id = %s AND window_time = %s
                """, (s["narrative_id"], window_time.isoformat()))
            except Exception as e:
                logger.error(f"Failed to mark signal as emitted: {e}")
