"""
discord_bot.py - Discord bot that posts virality signals as rich embeds.

Runs as a standalone async service. Polls the virality_signals table for
un-emitted signals and posts them to the configured Discord channel with
colour-coded embeds, score bars, component breakdowns, and trend sparklines.

Usage:
    python run.py --discord-bot
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from loguru import logger

import discord
from discord.ext import tasks

from mindshare_engine import config
from mindshare_engine.database import execute


# Domain → emoji mapping for visual channel scanning
DOMAIN_EMOJI = {
    "institutional_politics": "\U0001F3DB",   # 🏛
    "geopolitical_conflict":  "\U00002694",    # ⚔
    "markets_economy":        "\U0001F4C8",    # 📈
    "corporate_brand":        "\U0001F3E2",    # 🏢
    "crypto_defi":            "\U000026D3",    # ⛓
    "tech_innovation":        "\U0001F916",    # 🤖
    "science_knowledge":      "\U0001F52C",    # 🔬
    "health_biomedical":      "\U0001F3E5",    # 🏥
    "environment_climate":    "\U0001F30D",    # 🌍
    "legal_justice":          "\U00002696",    # ⚖
    "cultural_identity":      "\U0001F91D",    # 🤝
    "celebrity_prestige":     "\U00002B50",    # ⭐
    "sports_esports":         "\U000026BD",    # ⚽
    "creator_economy":        "\U0001F3AC",    # 🎬
    "nature_animals":         "\U0001F43E",    # 🐾
    "meme_platform":          "\U0001F921",    # 🤡
}

# Score thresholds → embed colour
TIER_COLOURS = {
    "alert":  discord.Colour.red(),
    "high":   discord.Colour.orange(),
    "signal": discord.Colour.gold(),
    "watch":  discord.Colour.blue(),
}


class MindshareBot(discord.Client):

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)

        self._channel_id = config.DISCORD_CHANNEL_ID
        self._poll_interval = config.DISCORD_POLL_INTERVAL
        self._signal_threshold = config.VIRALITY_SIGNAL_THRESHOLD
        self._alert_threshold = config.VIRALITY_ALERT_THRESHOLD
        self._channel: discord.TextChannel | None = None

    async def on_ready(self) -> None:
        logger.info(f"Discord bot connected as {self.user} (id={self.user.id})")

        self._channel = self.get_channel(self._channel_id)
        if self._channel is None:
            try:
                self._channel = await self.fetch_channel(self._channel_id)
            except discord.NotFound:
                logger.error(f"Channel {self._channel_id} not found — check DISCORD_CHANNEL_ID")
                return
            except discord.Forbidden:
                logger.error(f"Bot lacks access to channel {self._channel_id}")
                return

        logger.info(f"Posting to #{self._channel.name} (id={self._channel_id})")

        if not self.signal_poll_loop.is_running():
            self.signal_poll_loop.start()

        await self._post_startup_embed()

    async def _post_startup_embed(self) -> None:
        """Send a startup confirmation message."""
        embed = discord.Embed(
            title="Mindshare Engine Online",
            description=(
                f"Virality signal bot is live.\n"
                f"Polling every **{self._poll_interval}s** for signals above **{self._signal_threshold}** threshold.\n"
                f"Alert tier at **{self._alert_threshold}**."
            ),
            colour=discord.Colour.green(),
            timestamp=datetime.now(tz=timezone.utc),
        )
        embed.set_footer(text="Clawbot Mindshare Engine")
        try:
            await self._channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to send startup embed: {e}")

    # ------------------------------------------------------------------
    # Signal polling loop
    # ------------------------------------------------------------------

    @tasks.loop(seconds=30)
    async def signal_poll_loop(self) -> None:
        """Poll DB for un-emitted signals above threshold and post them."""
        self.signal_poll_loop.change_interval(seconds=self._poll_interval)
        try:
            signals = self._fetch_pending_signals()
            if not signals:
                return

            logger.info(f"Found {len(signals)} pending signals to post")
            for sig in signals:
                await self._post_signal(sig)
                self._mark_emitted(sig["narrative_id"], sig["window_time"])
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Signal poll error: {e}", exc_info=True)

    @signal_poll_loop.before_loop
    async def _before_poll(self) -> None:
        await self.wait_until_ready()

    # ------------------------------------------------------------------
    # Embed construction
    # ------------------------------------------------------------------

    async def _post_signal(self, sig: dict) -> None:
        """Build and send a rich embed for a virality signal."""
        if self._channel is None:
            return

        score = sig["virality_score"]
        tier = self._classify_tier(score)
        colour = TIER_COLOURS.get(tier, discord.Colour.greyple())
        domain = sig.get("primary_domain", "unknown")
        emoji = DOMAIN_EMOJI.get(domain, "\U0001F4E1")
        label = sig.get("label") or "unnamed"
        state = sig.get("state", "?")

        embed = discord.Embed(
            title=f"{emoji}  {label}",
            colour=colour,
            timestamp=datetime.now(tz=timezone.utc),
        )

        # Score bar
        bar = self._score_bar(score)
        tier_label = tier.upper()
        embed.description = f"**{tier_label}** — Virality Score: **{score:.3f}**\n`{bar}`"

        # Main stats
        embed.add_field(
            name="Domain",
            value=f"`{domain}`",
            inline=True,
        )
        embed.add_field(
            name="State",
            value=f"`{state}`",
            inline=True,
        )
        embed.add_field(
            name="Window",
            value=f"<t:{self._to_unix(sig.get('window_time'))}:R>",
            inline=True,
        )

        # Volume
        embed.add_field(
            name="Tweets",
            value=f"**{sig.get('tweet_count', 0):,}**",
            inline=True,
        )
        embed.add_field(
            name="Authors",
            value=f"**{sig.get('unique_authors', 0):,}**",
            inline=True,
        )

        # Top terms
        terms = sig.get("top_terms", [])
        if terms:
            terms_str = "  ".join(f"`{t}`" for t in terms[:5])
            embed.add_field(name="Top Terms", value=terms_str, inline=False)

        # Component breakdown
        components = sig.get("components", {})
        if components:
            breakdown = self._format_components(components)
            embed.add_field(name="Score Breakdown", value=breakdown, inline=False)

        # Trend sparkline (last few windows)
        trend = self._fetch_trend(sig["narrative_id"], limit=8)
        if len(trend) > 1:
            sparkline = self._sparkline(trend)
            embed.add_field(name="Trend", value=f"`{sparkline}`", inline=False)

        embed.set_footer(text=f"Narrative {sig['narrative_id'][:8]}… | Clawbot Mindshare Engine")

        try:
            await self._channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to post signal embed: {e}")

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_bar(score: float, width: int = 20) -> str:
        filled = round(score * width)
        empty = width - filled
        pct = score * 100
        return f"{'█' * filled}{'░' * empty} {pct:.1f}%"

    @staticmethod
    def _classify_tier(score: float) -> str:
        if score >= config.VIRALITY_ALERT_THRESHOLD:
            return "alert"
        elif score >= 0.65:
            return "high"
        elif score >= config.VIRALITY_SIGNAL_THRESHOLD:
            return "signal"
        return "watch"

    @staticmethod
    def _format_components(components: dict) -> str:
        labels = {
            "velocity": "Velocity",
            "acceleration": "Accel",
            "spread": "Spread",
            "engagement": "Engage",
            "influencer": "Influencer",
            "freshness": "Fresh",
        }
        lines = []
        for key, display in labels.items():
            val = components.get(key, 0.0)
            weight = config.VIRALITY_WEIGHTS.get(key, 0.0)
            mini_bar = "▓" * round(val * 8) + "░" * (8 - round(val * 8))
            lines.append(f"`{mini_bar}` **{display}** {val:.2f} (×{weight:.0%})")
        return "\n".join(lines)

    @staticmethod
    def _sparkline(scores: list[float]) -> str:
        if not scores:
            return ""
        blocks = " ▁▂▃▄▅▆▇█"
        mn, mx = min(scores), max(scores)
        spread = mx - mn if mx != mn else 1.0
        return "".join(blocks[min(8, int((s - mn) / spread * 8))] for s in scores)

    @staticmethod
    def _to_unix(ts) -> int:
        if ts is None:
            return 0
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except (ValueError, TypeError):
                return 0
        if hasattr(ts, "timestamp"):
            return int(ts.timestamp())
        return 0

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    def _fetch_pending_signals(self) -> list[dict]:
        """Fetch un-emitted signals above threshold, newest first."""
        rows = execute("""
            SELECT narrative_id, window_time, virality_score, components,
                   state, label, primary_domain, tweet_count, unique_authors, top_terms
            FROM virality_signals
            WHERE emitted = FALSE AND virality_score >= %s
            ORDER BY virality_score DESC
            LIMIT %s
        """, (self._signal_threshold, config.BOT_MAX_SIGNALS_PER_WINDOW), fetch=True) or []

        return [
            {
                "narrative_id": str(r[0]),
                "window_time": r[1],
                "virality_score": r[2],
                "components": r[3] if isinstance(r[3], dict) else json.loads(r[3] or "{}"),
                "state": r[4],
                "label": r[5],
                "primary_domain": r[6],
                "tweet_count": r[7] or 0,
                "unique_authors": r[8] or 0,
                "top_terms": r[9] if isinstance(r[9], list) else json.loads(r[9] or "[]"),
            }
            for r in rows
        ]

    @staticmethod
    def _mark_emitted(narrative_id: str, window_time) -> None:
        wt = window_time.isoformat() if hasattr(window_time, "isoformat") else str(window_time)
        try:
            execute("""
                UPDATE virality_signals
                SET emitted = TRUE, emitted_at = NOW()
                WHERE narrative_id = %s AND window_time = %s
            """, (narrative_id, wt))
        except Exception as e:
            logger.error(f"Failed to mark signal emitted: {e}")

    @staticmethod
    def _fetch_trend(narrative_id: str, limit: int = 8) -> list[float]:
        rows = execute("""
            SELECT virality_score FROM virality_signals
            WHERE narrative_id = %s
            ORDER BY window_time DESC
            LIMIT %s
        """, (narrative_id, limit), fetch=True) or []
        return [r[0] for r in reversed(rows)]


def run_bot() -> None:
    """Entry point — start the Discord bot."""
    token = config.DISCORD_BOT_TOKEN
    if not token:
        logger.error("DISCORD_BOT_TOKEN not set — cannot start Discord bot")
        return

    if not config.DISCORD_CHANNEL_ID:
        logger.error("DISCORD_CHANNEL_ID not set — cannot start Discord bot")
        return

    logger.info("Starting Mindshare Discord bot...")
    bot = MindshareBot()
    bot.run(token, log_handler=None)
