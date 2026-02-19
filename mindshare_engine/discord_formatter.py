"""
discord_formatter.py - Discord embed builder for narrative breakout signals.

Transforms virality signals into rich Discord webhook embed payloads with
tiered color coding, component breakdowns, and domain-aware formatting.

Tier thresholds (mapped from 0.0-1.0 to 0-100 display scale):
  GREEN  70+  HIGH CONVICTION  - Strong breakout signal
  YELLOW 50-69  MODERATE       - Worth watching
  RED    <50   LOW             - Logged only, not posted
"""
from __future__ import annotations

from datetime import datetime

from mindshare_engine import config

# Discord embed color integers (decimal RGB)
COLOR_HIGH = 0x00FF88      # green
COLOR_MODERATE = 0xFFAA00  # amber
COLOR_LOW = 0xFF4444       # red (used in summaries only)
COLOR_SUMMARY = 0x5865F2   # blurple (Discord brand)

# Score tier boundaries on the 0-100 display scale
TIER_HIGH = 70
TIER_MODERATE = 50

DOMAIN_ICONS: dict[str, str] = {
    "institutional_politics": "\U0001f3db\ufe0f",   # classical building
    "geopolitical_conflict":  "\U0001f30d",          # globe
    "markets_economy":        "\U0001f4c8",          # chart increasing
    "corporate_brand":        "\U0001f3e2",          # office building
    "crypto_defi":            "\U000026d3\ufe0f",    # chains
    "tech_innovation":        "\U0001f916",          # robot
    "science_knowledge":      "\U0001f52c",          # microscope
    "health_biomedical":      "\U0001f3e5",          # hospital
    "environment_climate":    "\U0001f30e",          # globe americas
    "legal_justice":          "\u2696\ufe0f",        # scales
    "cultural_identity":      "\U0001f5e3\ufe0f",   # speaking head
    "celebrity_prestige":     "\u2b50",              # star
    "sports_esports":         "\U0001f3c6",          # trophy
    "creator_economy":        "\U0001f3ac",          # clapperboard
    "nature_animals":         "\U0001f43e",          # paw prints
    "meme_platform":          "\U0001f921",          # clown
}

STATE_LABELS: dict[str, str] = {
    "incubating": "\U0001f95a Incubating",
    "emerging":   "\U0001f331 Emerging",
    "breaking":   "\U0001f525 Breaking",
    "dominant":   "\U0001f451 Dominant",
    "declining":  "\U0001f4c9 Declining",
    "dormant":    "\U0001f4a4 Dormant",
}

COMPONENT_META: dict[str, tuple[str, str, int]] = {
    "velocity":     ("\U0001f4e8", "Tweet Volume",        18),
    "acceleration": ("\U0001f680", "Growth Rate",         20),
    "spread":       ("\U0001f465", "Author Spread",       20),
    "engagement":   ("\U0001f4e3", "Amplification",       17),
    "influencer":   ("\U0001f451", "Influencer Signal",   10),
    "freshness":    ("\u23f0",     "Freshness",            5),
    "emotional":    ("\U0001f525", "Emotional Intensity",  10),
}


class DiscordFormatter:
    """Builds Discord webhook embed payloads from scored virality signals."""

    def __init__(self) -> None:
        self._weights = config.VIRALITY_WEIGHTS
        self._bot_name = config.DISCORD_BOT_NAME
        self._bot_avatar = config.DISCORD_BOT_AVATAR_URL

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def format_signal(self, signal: dict) -> dict:
        """
        Build a full Discord webhook payload for a single signal.

        Returns a dict ready to POST to a Discord webhook URL:
        { "username", "avatar_url", "embeds": [embed] }
        """
        raw_score = signal.get("virality_score", 0.0)
        display_score = round(raw_score * 100)
        tier, color = self._tier_info(display_score)
        domain = signal.get("primary_domain", "unknown")
        domain_icon = DOMAIN_ICONS.get(domain, "\U0001f4e1")
        state = signal.get("state", "unknown")
        state_label = STATE_LABELS.get(state, state)
        label = signal.get("label", "unnamed")
        components = signal.get("components", {})
        multipliers = signal.get("multipliers", {})
        why = signal.get("why", "")
        media_ratio = signal.get("media_ratio", 0.0)

        title = f"{self._tier_emoji(tier)} {tier} NARRATIVE BREAKOUT DETECTED"
        top_terms = signal.get("top_terms", [])
        search_url = self._build_search_url(top_terms)

        desc_lines = [
            f"**{label}**",
            (
                f"{domain_icon} {self._domain_display(domain)} | "
                f"{state_label} | "
                f"Score: **{display_score}/100** {self._score_bar(display_score)}"
            ),
        ]

        if why:
            desc_lines.append(f"\U0001f4a1 *{why}*")

        multiplier_badges = self._build_multiplier_badges(multipliers, media_ratio)
        if multiplier_badges:
            desc_lines.append(multiplier_badges)

        description = "\n".join(desc_lines)

        metrics_lines = self._build_metrics_block(components)
        context_lines = self._build_context_block(signal, domain_icon)

        viral_tweets_block = self._build_viral_tweets_block(signal)

        fields = [
            {
                "name": "\U0001f4ca BREAKOUT METRICS (v2 \u2014 7 signals)",
                "value": metrics_lines,
                "inline": False,
            },
            {
                "name": "\U0001f4c4 CONTEXT",
                "value": context_lines,
                "inline": False,
            },
        ]

        if viral_tweets_block:
            fields.append({
                "name": "\U0001f4f9 TOP VIRAL TWEETS",
                "value": viral_tweets_block,
                "inline": False,
            })

        component_fields = self._build_component_fields(components)
        fields.extend(component_fields)

        embed = {
            "title": title,
            "url": search_url,
            "description": description,
            "color": color,
            "fields": fields,
            "footer": {
                "text": (
                    f"Mindshare Engine v2 | "
                    f"Window: {self._format_window_time(signal.get('window_time'))} | "
                    f"{config.WINDOW_MINUTES}-min cycle"
                ),
            },
        }

        ts = signal.get("window_time")
        if ts:
            embed["timestamp"] = ts if isinstance(ts, str) else ts.isoformat()

        return {
            "username": self._bot_name,
            "avatar_url": self._bot_avatar or None,
            "embeds": [embed],
        }

    def format_batch_summary(
        self,
        signals: list[dict],
        window_time: datetime,
        total_scored: int,
    ) -> dict:
        """
        Build a compact window summary embed showing all emitted signals at a glance.
        Posted once per window before the individual signal embeds.
        """
        high = [s for s in signals if round(s.get("virality_score", 0) * 100) >= TIER_HIGH]
        moderate = [s for s in signals if TIER_MODERATE <= round(s.get("virality_score", 0) * 100) < TIER_HIGH]

        lines = [f"**{total_scored}** narratives scored this window\n"]

        if high:
            lines.append(f"\U0001f7e2 **HIGH CONVICTION** ({len(high)})")
            for s in high[:5]:
                sc = round(s["virality_score"] * 100)
                dom = DOMAIN_ICONS.get(s.get("primary_domain", ""), "\U0001f4e1")
                lines.append(f"  {dom} **{s.get('label', '?')}** \u2014 {sc}/100")

        if moderate:
            lines.append(f"\n\U0001f7e1 **MODERATE** ({len(moderate)})")
            for s in moderate[:5]:
                sc = round(s["virality_score"] * 100)
                dom = DOMAIN_ICONS.get(s.get("primary_domain", ""), "\U0001f4e1")
                lines.append(f"  {dom} {s.get('label', '?')} \u2014 {sc}/100")

        if not high and not moderate:
            lines.append("No signals above threshold this window.")

        embed = {
            "title": "\U0001f4e1 NARRATIVE SCAN COMPLETE",
            "description": "\n".join(lines),
            "color": COLOR_SUMMARY,
            "footer": {
                "text": (
                    f"Mindshare Engine | "
                    f"Window: {self._format_window_time(window_time)} | "
                    f"Next scan in {config.WINDOW_MINUTES}m"
                ),
            },
        }

        if window_time:
            embed["timestamp"] = (
                window_time if isinstance(window_time, str) else window_time.isoformat()
            )

        return {
            "username": self._bot_name,
            "avatar_url": self._bot_avatar or None,
            "embeds": [embed],
        }

    def should_post(self, signal: dict) -> bool:
        """Check whether a signal meets the tier threshold for Discord posting."""
        score = round(signal.get("virality_score", 0.0) * 100)
        if score >= TIER_HIGH and config.DISCORD_ALERT_HIGH_CONVICTION:
            return True
        if TIER_MODERATE <= score < TIER_HIGH and config.DISCORD_ALERT_MODERATE:
            return True
        return False

    # ------------------------------------------------------------------
    # Metrics formatting
    # ------------------------------------------------------------------

    def _build_metrics_block(self, components: dict) -> str:
        """Formatted multi-line metrics block for all 7 v2 signals."""
        lines = []
        for key, (icon, label, max_pts) in COMPONENT_META.items():
            raw = components.get(key, 0.0)
            pts = round(raw * max_pts)
            arrow = self._trend_arrow(raw)
            bar = self._mini_bar(raw)
            lines.append(f"{icon} {arrow} **{label}:** {pts}/{max_pts} pts {bar}")
        return "\n".join(lines)

    def _build_context_block(self, signal: dict, domain_icon: str) -> str:
        """Context section with domain, tweets, authors, top terms."""
        parts = []

        tweet_count = signal.get("tweet_count", 0)
        unique_authors = signal.get("unique_authors", 0)
        parts.append(f"{domain_icon} **Tweets:** {tweet_count} | **Authors:** {unique_authors}")

        top_terms = signal.get("top_terms", [])
        if top_terms:
            from urllib.parse import quote
            linked = []
            for t in top_terms[:6]:
                url = f"https://x.com/search?q={quote(t)}&src=typed_query&f=live"
                linked.append(f"[`{t}`]({url})")
            parts.append(f"\U0001f50d **Top Terms:** {', '.join(linked)}")

        search_url = self._build_search_url(top_terms)
        parts.append(f"\U0001f517 [**View on X**]({search_url})")

        return "\n".join(parts)

    @staticmethod
    def _build_viral_tweets_block(signal: dict) -> str:
        """
        Format the top viral tweets with direct X links and engagement stats.

        Expects signal["top_tweets"]: list of dicts with keys:
            tweet_id, author_username, content, retweet_count, like_count,
            reply_count, quote_count
        """
        top_tweets = signal.get("top_tweets", [])
        if not top_tweets:
            return ""

        lines = []
        for i, tw in enumerate(top_tweets[:3], 1):
            tid = tw.get("tweet_id", "")
            username = tw.get("author_username", "")
            content = tw.get("content", "")

            # Truncate tweet text for embed readability
            text = content.replace("\n", " ").strip()
            if len(text) > 120:
                text = text[:117] + "..."

            rts = tw.get("retweet_count", 0)
            likes = tw.get("like_count", 0)
            replies = tw.get("reply_count", 0)

            # Direct link to the tweet
            if username and tid:
                tweet_url = f"https://x.com/{username}/status/{tid}"
            elif tid:
                tweet_url = f"https://x.com/i/status/{tid}"
            else:
                tweet_url = ""

            # Format: numbered tweet with stats and link
            handle = f"@{username}" if username else "unknown"
            stats = f"\u2764\ufe0f {likes}  \U0001f501 {rts}  \U0001f4ac {replies}"

            if tweet_url:
                lines.append(f"**{i}.** [{handle}]({tweet_url})")
            else:
                lines.append(f"**{i}.** {handle}")
            lines.append(f"> {text}")
            lines.append(f"{stats}")
            if i < min(len(top_tweets), 3):
                lines.append("")

        return "\n".join(lines)

    def _build_component_fields(self, components: dict) -> list[dict]:
        """Inline fields for the top 3 components (compact view)."""
        scored = []
        for key, (icon, label, max_pts) in COMPONENT_META.items():
            raw = components.get(key, 0.0)
            pts = round(raw * max_pts)
            scored.append((icon, label, pts, max_pts, raw))

        scored.sort(key=lambda x: -x[2])
        fields = []
        for icon, label, pts, max_pts, raw in scored[:3]:
            arrow = self._trend_arrow(raw)
            fields.append({
                "name": f"{icon} {arrow} {label}",
                "value": f"**{pts}**/{max_pts} pts",
                "inline": True,
            })
        return fields

    @staticmethod
    def _build_multiplier_badges(multipliers: dict, media_ratio: float) -> str:
        """Render applied post-scoring multipliers as inline badges."""
        badges = []
        if "visual" in multipliers:
            pct = round(media_ratio * 100)
            badges.append(f"\U0001f3ac Visual x{multipliers['visual']:.2f} ({pct}% media)")
        if "category_boost" in multipliers:
            badges.append(f"\U0001f30d Category +{(multipliers['category_boost'] - 1):.0%}")
        if "age_demotion" in multipliers:
            badges.append(f"\u23f3 Stale -{multipliers['age_demotion']:.0%}")
        if not badges:
            return ""
        return "\U0001f3f7\ufe0f " + " \u2022 ".join(badges)

    # ------------------------------------------------------------------
    # Visual helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tier_info(display_score: int) -> tuple[str, int]:
        """Return (tier_name, color_int) for a 0-100 score."""
        if display_score >= TIER_HIGH:
            return "HIGH CONVICTION", COLOR_HIGH
        if display_score >= TIER_MODERATE:
            return "MODERATE", COLOR_MODERATE
        return "LOW", COLOR_LOW

    @staticmethod
    def _tier_emoji(tier: str) -> str:
        if tier == "HIGH CONVICTION":
            return "\U0001f7e2"
        if tier == "MODERATE":
            return "\U0001f7e1"
        return "\U0001f534"

    @staticmethod
    def _score_bar(display_score: int, width: int = 10) -> str:
        filled = round(display_score / 100 * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    @staticmethod
    def _mini_bar(raw: float, width: int = 6) -> str:
        filled = round(raw * width)
        return "\u2588" * filled + "\u2591" * (width - filled)

    @staticmethod
    def _trend_arrow(raw: float) -> str:
        if raw >= 0.7:
            return "\u2b06\ufe0f"
        if raw >= 0.4:
            return "\u2197\ufe0f"
        if raw >= 0.2:
            return "\u27a1\ufe0f"
        return "\u2198\ufe0f"

    @staticmethod
    def _build_search_url(top_terms: list[str]) -> str:
        """Build an X/Twitter search URL from the top narrative terms."""
        if not top_terms:
            return "https://x.com/search"
        from urllib.parse import quote
        query = " OR ".join(top_terms[:3])
        return f"https://x.com/search?q={quote(query)}&src=typed_query&f=live"

    @staticmethod
    def _domain_display(domain: str) -> str:
        return domain.replace("_", " ").title()

    @staticmethod
    def _format_window_time(wt) -> str:
        if wt is None:
            return "N/A"
        if isinstance(wt, str):
            try:
                wt = datetime.fromisoformat(wt)
            except (ValueError, TypeError):
                return wt
        return wt.strftime("%Y-%m-%d %H:%M UTC")
