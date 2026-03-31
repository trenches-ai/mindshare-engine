"""
signal_emitter.py - Delivers virality signals via Discord webhooks and generic webhooks.

Posts rich Discord embeds for narrative breakout alerts, with per-narrative
cooldown to avoid spam and tiered filtering (HIGH CONVICTION / MODERATE / LOW).

Also retains the generic webhook path for non-Discord consumers (Telegram, custom).
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from loguru import logger

from mindshare_engine import config
from mindshare_engine.database import execute
from mindshare_engine.discord_formatter import DiscordFormatter

try:
    import urllib.request
    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False


class SignalEmitter:

    def __init__(self) -> None:
        self._webhook_url = config.BOT_WEBHOOK_URL
        self._webhook_secret = config.BOT_WEBHOOK_SECRET
        self._discord_webhook_url = config.DISCORD_WEBHOOK_URL
        self._cooldown_minutes = config.BOT_COOLDOWN_MINUTES
        self._max_per_window = config.BOT_MAX_SIGNALS_PER_WINDOW
        self._signal_threshold = config.VIRALITY_SIGNAL_THRESHOLD
        self._alert_threshold = config.VIRALITY_ALERT_THRESHOLD
        self._formatter = DiscordFormatter()

    def emit(self, scored: list[dict], window_time: datetime) -> dict:
        """
        v2 filter chain: threshold → visual guard → cooldown → top-N by score.
        """
        above_threshold = [
            s for s in scored if s["virality_score"] >= self._signal_threshold
        ]

        min_visual = config.MIN_VISUAL_RATIO_TO_EMIT
        if min_visual > 0:
            before = len(above_threshold)
            above_threshold = [
                s for s in above_threshold
                if s.get("media_ratio", 1.0) >= min_visual
            ]
            skipped_visual = before - len(above_threshold)
        else:
            skipped_visual = 0

        if not above_threshold:
            return {
                "emitted": 0,
                "skipped_cooldown": 0,
                "skipped_visual": skipped_visual,
                "skipped_threshold": len(scored) - len(above_threshold) - skipped_visual,
            }

        after_cooldown = self._apply_cooldown(above_threshold, window_time)
        to_emit = after_cooldown[:self._max_per_window]

        discord_ok = self._emit_discord(to_emit, scored, window_time)
        webhook_ok = self._emit_generic_webhook(to_emit, scored, window_time)

        delivered = discord_ok or webhook_ok
        if delivered:
            self._mark_emitted(to_emit, window_time)

        stats = {
            "emitted": len(to_emit),
            "skipped_cooldown": len(above_threshold) - len(after_cooldown),
            "skipped_visual": skipped_visual,
            "skipped_threshold": len(scored) - len(above_threshold) - skipped_visual,
            "discord_delivered": discord_ok,
            "webhook_delivered": webhook_ok,
        }
        logger.info(f"Signal emission: {stats}")
        return stats

    # ------------------------------------------------------------------
    # Discord delivery
    # ------------------------------------------------------------------

    def _emit_discord(
        self,
        signals: list[dict],
        all_scored: list[dict],
        window_time: datetime,
    ) -> bool:
        """Post Discord embeds: optional summary + individual signal embeds."""
        if not self._discord_webhook_url:
            logger.debug("No Discord webhook URL configured")
            return False

        ok = True

        if config.DISCORD_POST_SUMMARY:
            summary_payload = self._formatter.format_batch_summary(
                signals, window_time, total_scored=len(all_scored),
            )
            if not self._post_discord(summary_payload):
                ok = False

        for signal in signals:
            if not self._formatter.should_post(signal):
                continue
            embed_payload = self._formatter.format_signal(signal)
            if not self._post_discord(embed_payload):
                ok = False

        return ok

    def _post_discord(self, payload: dict) -> bool:
        """POST a Discord webhook payload (with embeds)."""
        if not _HAS_URLLIB:
            logger.error("urllib not available for Discord webhook delivery")
            return False

        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self._discord_webhook_url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "MindshareEngine/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.getcode()
                if status < 300:
                    logger.debug(f"Discord webhook delivered: HTTP {status}")
                    return True
                logger.warning(f"Discord webhook non-2xx: HTTP {status}")
                return False
        except Exception as e:
            logger.error(f"Discord webhook failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Generic webhook delivery (Telegram, custom services)
    # ------------------------------------------------------------------

    def _emit_generic_webhook(
        self,
        signals: list[dict],
        all_scored: list[dict],
        window_time: datetime,
    ) -> bool:
        """POST structured JSON to the generic webhook endpoint."""
        if not self._webhook_url:
            return False

        signals_payload = [self._format_generic_signal(s) for s in signals]

        payload = {
            "event": "virality_signal",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "signals": signals_payload,
            "meta": {
                "window_time": window_time.isoformat(),
                "total_scored": len(all_scored),
                "signals_emitted": len(signals_payload),
                "threshold": self._signal_threshold,
            },
        }
        return self._post_generic_webhook(payload)

    def _post_generic_webhook(self, payload: dict) -> bool:
        """POST payload to the generic webhook URL with HMAC signing."""
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
                    logger.info(f"Generic webhook delivered: HTTP {status}")
                    return True
                logger.warning(f"Generic webhook non-2xx: HTTP {status}")
                return False
        except Exception as e:
            logger.error(f"Generic webhook failed: {e}")
            return False

    # ------------------------------------------------------------------
    # Query helpers (unchanged)
    # ------------------------------------------------------------------

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
    # Generic signal formatting (for non-Discord webhooks)
    # ------------------------------------------------------------------

    @staticmethod
    def _format_generic_signal(signal: dict) -> dict:
        """Build a clean, bot-friendly signal payload for generic webhooks."""
        score = signal["virality_score"]
        display = round(score * 100)
        tier = "HIGH_CONVICTION" if display >= 70 else ("MODERATE" if display >= 50 else "LOW")

        return {
            "narrative_id": signal["narrative_id"],
            "tier": tier,
            "virality_score": score,
            "display_score": display,
            "components": signal.get("components", {}),
            "multipliers": signal.get("multipliers", {}),
            "why": signal.get("why", ""),
            "media_ratio": signal.get("media_ratio", 0.0),
            "label": signal.get("label"),
            "primary_domain": signal.get("primary_domain"),
            "state": signal.get("state"),
            "tweet_count": signal.get("tweet_count", 0),
            "unique_authors": signal.get("unique_authors", 0),
            "top_terms": signal.get("top_terms", []),
        }

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
