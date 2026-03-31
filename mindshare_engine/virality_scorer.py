"""
virality_scorer.py - v4 Composite virality index for narrative breakout detection.

Scores each active narrative on ELEVEN dimensions per window:
  1. Velocity       (8%)  — tweet volume vs rolling 30-min baseline
  2. Acceleration  (16%)  — second derivative of velocity
  3. Spread        (18%)  — unique author growth rate (best bot filter)
  4. Engagement    (11%)  — weighted amplification (likes/RTs + quotes/replies + media boost)
  5. Influencer     (6%)  — high-follower / verified author participation
  6. Freshness      (5%)  — recency decay with sustained-mode override
  7. Emotional      (8%)  — embedding-based arousal + valence intensity
  8. Remix          (7%)  — quote tweet participation (cultural remix)
  9. Controversy    (6%)  — reply-to-like ratio (debate signal)
 10. Smart Account (10%)  — weighted account tier participation (WHO is talking)
 11. Coordination   (5%)  — cross-account correlation detection

Post-scoring multipliers:
  - Visual Virality    ×1.12 when ≥50% of window posts contain media
  - Category Boost     +15% velocity/spread for quiet domains
  - Age Demotion       -20% for narratives >48h old without fresh acceleration
  - Dynamic Reweighting  14% shifted from saturated volume signals to quality signals
  - First-Mover Boost  up to +20% if trend was started by high-tier account
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from loguru import logger

from mindshare_engine import config
from mindshare_engine.database import execute


class ViralityScorer:

    def __init__(self) -> None:
        self._lookback = config.VIRALITY_WINDOW_LOOKBACK
        self._weights = config.VIRALITY_WEIGHTS
        self._signal_threshold = config.VIRALITY_SIGNAL_THRESHOLD
        self._window_minutes = config.WINDOW_MINUTES

    def score_window(self, window_time: datetime) -> list[dict]:
        """Compute v2 virality scores for every active narrative in this window."""
        narratives = self._load_window_narratives(window_time)
        if not narratives:
            logger.debug("No narratives to score this window")
            return []

        scored = []
        for n in narratives:
            nid = str(n["narrative_id"])
            history = self._load_narrative_history(nid, window_time)
            media_ratio = self._compute_media_ratio(nid, window_time)

            components = self._compute_components(n, history, window_time, media_ratio)
            raw_score = self._weighted_score(components)

            multipliers = self._compute_multipliers(
                raw_score, components, media_ratio,
                n["primary_domain"], n, window_time, history,
            )
            final_score = multipliers["final_score"]

            # v4: Extract who's talking data
            whos_talking = self._extract_whos_talking(nid, window_time)

            record = {
                "narrative_id": nid,
                "window_time": window_time,
                "virality_score": round(final_score, 4),
                "components": components,
                "multipliers": multipliers["applied"],
                "why": multipliers["why"],
                "media_ratio": round(media_ratio, 2),
                "state": n["state"],
                "label": n["label"],
                "primary_domain": n["primary_domain"],
                "tweet_count": n["tweet_count"],
                "unique_authors": n["unique_authors"],
                "top_terms": self._extract_top_terms(nid, window_time),
                "top_tweets": self._extract_top_tweets(nid, window_time),
                # v4 additions
                "first_mover": multipliers.get("first_mover"),
                "whos_talking": whos_talking,
            }
            self._store_signal(record)
            scored.append(record)

        scored.sort(key=lambda x: x["virality_score"], reverse=True)
        above_threshold = sum(1 for s in scored if s["virality_score"] >= self._signal_threshold)
        logger.info(
            f"Virality v2: {len(scored)} narratives, "
            f"{above_threshold} above threshold ({self._signal_threshold})"
        )
        return scored

    # ------------------------------------------------------------------
    # 11 Component calculations (v4)
    # ------------------------------------------------------------------

    def _compute_components(
        self,
        current: dict,
        history: list[dict],
        window_time: datetime,
        media_ratio: float,
    ) -> dict[str, float]:
        velocity = self._velocity(current, history)
        acceleration = self._acceleration(current, history)
        spread = self._spread(current, history)
        engagement = self._engagement(current, media_ratio)
        influencer = self._influencer_signal(current["narrative_id"], window_time)
        freshness = self._freshness(current, window_time, history)
        emotional = self._emotional_intensity(current["narrative_id"], window_time)
        remix = self._remix_signal(current)
        controversy = self._controversy_signal(current)
        smart_account = self._smart_account_signal(current["narrative_id"], window_time)
        coordination = self._coordination_signal(current["narrative_id"], window_time)

        return {
            "velocity": round(velocity, 4),
            "acceleration": round(acceleration, 4),
            "spread": round(spread, 4),
            "engagement": round(engagement, 4),
            "influencer": round(influencer, 4),
            "freshness": round(freshness, 4),
            "emotional": round(emotional, 4),
            "remix": round(remix, 4),
            "controversy": round(controversy, 4),
            "smart_account": round(smart_account, 4),
            "coordination": round(coordination, 4),
        }

    def _velocity(self, current: dict, history: list[dict]) -> float:
        """Tweet volume vs rolling baseline. 2.5x surge = sigmoid midpoint."""
        tc = current["tweet_count"]
        if not history:
            return self._sigmoid(tc, midpoint=config.VELOCITY_COLD_MIDPOINT, steepness=0.04)

        baseline = sum(h["tweet_count"] for h in history) / len(history)
        if baseline < 1:
            baseline = 1.0
        ratio = tc / baseline
        return self._sigmoid(ratio, midpoint=config.VELOCITY_SURGE_MIDPOINT, steepness=1.5)

    def _acceleration(self, current: dict, history: list[dict]) -> float:
        """Second derivative of velocity. Positive = momentum building."""
        tc = current["tweet_count"]
        if len(history) < 2:
            return self._sigmoid(tc, midpoint=config.ACCEL_COLD_MIDPOINT, steepness=0.06)

        counts = [h["tweet_count"] for h in history] + [tc]
        deltas = [counts[i] - counts[i - 1] for i in range(1, len(counts))]
        if len(deltas) < 2:
            return self._sigmoid(tc, midpoint=config.ACCEL_COLD_MIDPOINT, steepness=0.06)

        recent_delta = deltas[-1]
        prior_avg = sum(deltas[:-1]) / len(deltas[:-1])

        if prior_avg == 0:
            accel = float(recent_delta)
        else:
            accel = (recent_delta - prior_avg) / abs(prior_avg)

        return self._sigmoid(accel, midpoint=0.0, steepness=1.0)

    def _spread(self, current: dict, history: list[dict]) -> float:
        """Unique author growth. 55% new authors = midpoint."""
        authors_now = current["unique_authors"]
        if not history:
            return self._sigmoid(authors_now, midpoint=config.SPREAD_COLD_MIDPOINT, steepness=0.08)

        authors_prev = history[-1].get("unique_authors", 1) or 1
        growth = (authors_now - authors_prev) / authors_prev
        return self._sigmoid(growth, midpoint=config.SPREAD_NEW_AUTHOR_MIDPOINT, steepness=2.0)

    def _engagement(self, current: dict, media_ratio: float) -> float:
        """
        v2.1 weighted amplification:
          40% likes+RTs, 40% quotes+replies (remix signal), 20% media boost.
          +0.1 remixability bonus when >30% of engagement comes from quotes
          (video duets, meme remixes, reaction threads).
        """
        tc = max(current["tweet_count"], 1)
        total_eng = current.get("total_engagement", 0)
        likes_rts = current.get("total_likes_rts", total_eng * 0.6)
        quotes_replies = current.get("total_quotes_replies", total_eng * 0.4)

        likes_rts_ratio = likes_rts / tc
        quotes_replies_ratio = quotes_replies / tc
        media_bonus = media_ratio

        weighted = (
            config.ENGAGEMENT_WEIGHT_LIKES_RTS * likes_rts_ratio +
            config.ENGAGEMENT_WEIGHT_QUOTES_REPLIES * quotes_replies_ratio +
            config.ENGAGEMENT_WEIGHT_MEDIA_BOOST * media_bonus * 10
        )

        remix_ratio = quotes_replies / max(total_eng, 1)
        if remix_ratio > config.REMIX_THRESHOLD:
            weighted += config.REMIX_BOOST

        return self._sigmoid(weighted, midpoint=config.ENGAGEMENT_MIDPOINT, steepness=0.3)

    def _influencer_signal(self, narrative_id: str, window_time: datetime) -> float:
        """Fraction of tweets from 10k+ follower accounts. 6% = midpoint."""
        rows = execute("""
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE a.follower_count > 10000) AS influencers
            FROM tweets_raw t
            JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s AND t.window_time = %s
        """, (narrative_id, window_time.isoformat()), fetch=True)

        if not rows or rows[0][0] == 0:
            return 0.0

        total, influencers = rows[0]
        fraction = influencers / total
        return self._sigmoid(fraction, midpoint=config.INFLUENCER_MIDPOINT, steepness=15.0)

    def _freshness(self, current: dict, window_time: datetime, history: list[dict]) -> float:
        """
        Recency decay. 45 minutes old = midpoint.
        Sustained mode: if >4h old but still accelerating, halve the decay.
        """
        created = current.get("created_at")
        if not created:
            return 0.5

        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                return 0.5

        age_minutes = (window_time - created).total_seconds() / 60.0

        sustained_hours = config.FRESHNESS_SUSTAINED_HOURS
        if age_minutes > sustained_hours * 60 and len(history) >= 2:
            recent_counts = [h["tweet_count"] for h in history[-2:]]
            if len(recent_counts) == 2 and recent_counts[-1] > recent_counts[-2]:
                age_minutes *= 0.5

        return self._sigmoid(
            -age_minutes,
            midpoint=-config.FRESHNESS_MIDPOINT_MINUTES,
            steepness=0.04,
        )

    def _emotional_intensity(self, narrative_id: str, window_time: datetime) -> float:
        """
        Embedding-based arousal + valence proxy.

        Uses linguistic markers (exclamation, caps, emoji density, sentiment words)
        as a fast proxy for emotional intensity. The existing embedder can be
        upgraded to a full LLM scorer later.
        """
        rows = execute("""
            SELECT content FROM tweets_raw
            WHERE narrative_id = %s AND window_time = %s
            LIMIT 50
        """, (narrative_id, window_time.isoformat()), fetch=True) or []

        if not rows:
            return 0.5

        HIGH_AROUSAL = {
            "omg", "wtf", "insane", "crazy", "unbelievable", "incredible",
            "shocking", "breaking", "urgent", "massive", "huge", "terrifying",
            "amazing", "adorable", "hilarious", "heartbreaking", "devastating",
            "beautiful", "gorgeous", "disgusting", "furious", "love", "hate",
            "crying", "dead", "dying", "screaming", "obsessed", "iconic",
            "legendary", "tragic", "horrifying", "wholesome", "blessed",
        }

        total_signals = 0
        total_words = 0

        for row in rows:
            text = row[0] or ""
            words = text.split()
            total_words += max(len(words), 1)

            caps_words = sum(1 for w in words if w.isupper() and len(w) > 2)
            exclamations = text.count("!") + text.count("?!")
            emoji_count = sum(1 for c in text if ord(c) > 0x1F600)
            arousal_hits = sum(1 for w in words if w.lower().strip(".,!?#@") in HIGH_AROUSAL)

            total_signals += caps_words * 2 + exclamations * 1.5 + emoji_count + arousal_hits * 3

        intensity = total_signals / max(total_words, 1)
        return self._sigmoid(intensity, midpoint=config.EMOTIONAL_MIDPOINT, steepness=3.0)

    def _remix_signal(self, current: dict) -> float:
        """
        Measure quote-tweet participation — indicates cultural remix behaviour.
        High quote ratio = people adding commentary = narrative gaining traction.
        """
        total_engagement = (
            current.get("total_likes", 0)
            + current.get("total_rts", 0)
            + current.get("total_quotes", 0)
            + current.get("total_replies", 0)
        )
        if total_engagement == 0:
            return 0.0

        quote_ratio = current.get("total_quotes", 0) / total_engagement
        return self._sigmoid(quote_ratio, midpoint=config.REMIX_MIDPOINT, steepness=8.0)

    def _controversy_signal(self, current: dict) -> float:
        """
        Measure reply-to-like ratio — high ratio indicates debate/controversy.
        Controversial content drives sustained engagement and shares.
        """
        likes = current.get("total_likes", 0)
        replies = current.get("total_replies", 0)

        if likes == 0:
            # If no likes but has replies, that's very controversial
            return 1.0 if replies > 10 else 0.0

        reply_ratio = replies / likes
        return self._sigmoid(reply_ratio, midpoint=config.CONTROVERSY_MIDPOINT, steepness=5.0)

    def _smart_account_signal(self, narrative_id: str, window_time: datetime) -> float:
        """
        v4: Weighted account tier participation — WHO is talking matters.
        
        Each account is weighted by tier:
          - mega (1M+):   5x
          - macro (100K+): 3x
          - mid (10K+):   1.5x
          - small (1K+):  1x
          - nano (<1K):   0.5x
        
        Higher weighted score = more influential accounts participating.
        """
        rows = execute("""
            SELECT a.follower_count
            FROM tweets_raw t
            JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s AND t.window_time = %s
        """, (narrative_id, window_time.isoformat()), fetch=True) or []

        if not rows:
            return 0.0

        weighted_sum = 0.0
        for (follower_count,) in rows:
            tier = self._classify_tier(follower_count or 0)
            weighted_sum += config.ACCOUNT_TIER_WEIGHTS.get(tier, 0.5)

        # Normalize by number of tweets
        weighted_avg = weighted_sum / len(rows)
        
        return self._sigmoid(
            weighted_avg,
            midpoint=config.SMART_ACCOUNT_MIDPOINT,
            steepness=config.SMART_ACCOUNT_STEEPNESS,
        )

    def _coordination_signal(self, narrative_id: str, window_time: datetime) -> float:
        """
        v4: Cross-account correlation detection.
        
        Detects when multiple mid/macro/mega accounts tweet about the same 
        narrative within a short time window — indicates coordinated interest
        or breaking news that multiple sources are picking up.
        
        Returns high signal when:
          - 2+ high-tier accounts (macro/mega) tweet same topic
          - Multiple mid-tier accounts tweet within short window
        """
        cross_window = config.CROSS_ACCOUNT_WINDOW_MINUTES
        
        rows = execute("""
            SELECT a.follower_count, t.created_at, a.username
            FROM tweets_raw t
            JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s 
              AND t.window_time >= %s::timestamptz - (%s * INTERVAL '1 minute')
            ORDER BY t.created_at ASC
        """, (narrative_id, window_time.isoformat(), cross_window), fetch=True) or []

        if len(rows) < 2:
            return 0.0

        # Count distinct accounts by tier
        tier_counts = {"mega": 0, "macro": 0, "mid": 0, "small": 0, "nano": 0}
        seen_usernames = set()
        
        for follower_count, _, username in rows:
            if username and username not in seen_usernames:
                seen_usernames.add(username)
                tier = self._classify_tier(follower_count or 0)
                tier_counts[tier] += 1

        # High signal if multiple high-tier accounts participate
        high_tier_count = tier_counts["mega"] + tier_counts["macro"]
        mid_plus_count = high_tier_count + tier_counts["mid"]

        if high_tier_count >= config.CROSS_ACCOUNT_MIN_TIERS:
            # Strong coordination signal
            return self._sigmoid(high_tier_count, midpoint=2.0, steepness=1.0)
        elif mid_plus_count >= 3:
            # Moderate coordination
            return self._sigmoid(mid_plus_count, midpoint=4.0, steepness=0.5)
        
        return 0.0

    @staticmethod
    def _classify_tier(follower_count: int) -> str:
        """Classify account into tier based on follower count."""
        if follower_count >= config.ACCOUNT_TIER_THRESHOLDS["mega"]:
            return "mega"
        elif follower_count >= config.ACCOUNT_TIER_THRESHOLDS["macro"]:
            return "macro"
        elif follower_count >= config.ACCOUNT_TIER_THRESHOLDS["mid"]:
            return "mid"
        elif follower_count >= config.ACCOUNT_TIER_THRESHOLDS["small"]:
            return "small"
        else:
            return "nano"

    # ------------------------------------------------------------------
    # Post-scoring multipliers
    # ------------------------------------------------------------------

    def _compute_multipliers(
        self,
        raw_score: float,
        components: dict,
        media_ratio: float,
        domain: str,
        current: dict,
        window_time: datetime,
        history: list[dict],
    ) -> dict:
        """Apply visual, category, age, and first-mover multipliers. Return final score + explanation."""
        score = raw_score
        applied = {}
        why_parts = []
        first_mover_info = None

        # Visual virality multiplier
        if media_ratio >= config.VISUAL_VIRALITY_THRESHOLD:
            score *= config.VISUAL_VIRALITY_MULTIPLIER
            applied["visual"] = config.VISUAL_VIRALITY_MULTIPLIER
            why_parts.append(f"Visual x{config.VISUAL_VIRALITY_MULTIPLIER}")

        # Category-aware baseline boost for quiet domains
        if domain in config.QUIET_DOMAINS:
            boost = 1.0 + config.CATEGORY_QUIET_BOOST
            score *= boost
            applied["category_boost"] = boost
            why_parts.append(f"{domain.split('_')[0].title()} +{config.CATEGORY_QUIET_BOOST:.0%}")

        # Narrative age cap demotion
        created = current.get("created_at")
        if created:
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created)
                except (ValueError, TypeError):
                    created = None

            if created:
                age_hours = (window_time - created).total_seconds() / 3600.0
                still_accelerating = (
                    len(history) >= 2
                    and history[-1]["tweet_count"] > history[-2]["tweet_count"]
                )
                if age_hours > config.NARRATIVE_AGE_CAP_HOURS and not still_accelerating:
                    score *= (1.0 - config.NARRATIVE_AGE_DEMOTION)
                    applied["age_demotion"] = config.NARRATIVE_AGE_DEMOTION
                    why_parts.append(f"Stale -{config.NARRATIVE_AGE_DEMOTION:.0%}")

        # v4: First-mover boost — if the first tweet came from a high-tier account
        first_mover_info = self._get_first_mover(current["narrative_id"], window_time)
        if first_mover_info:
            tier = first_mover_info.get("tier", "nano")
            boost = config.FIRST_MOVER_TIER_BOOST.get(tier, 0.0)
            if boost > 0:
                score *= (1.0 + boost)
                applied["first_mover"] = boost
                username = first_mover_info.get("username", "unknown")
                why_parts.append(f"First-mover @{username} ({tier}) +{boost:.0%}")

        # v4: Cross-account coordination boost
        if components.get("coordination", 0) > 0.6:
            coord_boost = config.CROSS_ACCOUNT_BOOST
            score *= (1.0 + coord_boost)
            applied["coordination_boost"] = coord_boost
            why_parts.append(f"Multi-account +{coord_boost:.0%}")

        score = max(0.0, min(1.0, score))

        # Build the one-line "why" explanation
        top_component = max(components, key=components.get)
        top_val = components[top_component]
        label = current.get("label", "narrative")
        why = f"{label}: {top_component.title()} {top_val:.2f}"
        if why_parts:
            why += " + " + " + ".join(why_parts)

        return {
            "final_score": score,
            "raw_score": round(raw_score, 4),
            "applied": applied,
            "why": why,
            "first_mover": first_mover_info,
        }

    def _get_first_mover(self, narrative_id: str, window_time: datetime) -> dict | None:
        """
        Find the first tweet in this narrative and return info about who posted it.
        
        Returns dict with: username, follower_count, tier, tweet_id, created_at
        """
        first_mover_window = config.FIRST_MOVER_WINDOW_MINUTES
        
        rows = execute("""
            SELECT t.tweet_id, t.created_at, a.username, a.follower_count
            FROM tweets_raw t
            JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s
              AND t.window_time >= %s::timestamptz - (%s * INTERVAL '1 minute')
            ORDER BY t.created_at ASC
            LIMIT 1
        """, (narrative_id, window_time.isoformat(), first_mover_window), fetch=True)

        if not rows:
            return None

        tweet_id, created_at, username, follower_count = rows[0]
        tier = self._classify_tier(follower_count or 0)

        return {
            "tweet_id": str(tweet_id),
            "created_at": created_at.isoformat() if created_at else None,
            "username": username or "unknown",
            "follower_count": follower_count or 0,
            "tier": tier,
        }

    def _extract_whos_talking(self, narrative_id: str, window_time: datetime) -> dict:
        """
        v4: Extract "who's talking" data — notable accounts participating in this narrative.
        
        Returns:
            {
                "tier_breakdown": {"mega": 1, "macro": 3, ...},
                "notable_accounts": [{"username": "x", "tier": "mega", "followers": 1M}, ...],
                "first_mover": {...}
            }
        """
        rows = execute("""
            SELECT DISTINCT a.username, a.follower_count
            FROM tweets_raw t
            JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s AND t.window_time = %s
        """, (narrative_id, window_time.isoformat()), fetch=True) or []

        tier_breakdown = {"mega": 0, "macro": 0, "mid": 0, "small": 0, "nano": 0}
        notable_accounts = []

        for username, follower_count in rows:
            tier = self._classify_tier(follower_count or 0)
            tier_breakdown[tier] += 1

            # Track notable accounts (mid tier and above)
            if tier in ("mega", "macro", "mid") and username:
                notable_accounts.append({
                    "username": username,
                    "tier": tier,
                    "follower_count": follower_count or 0,
                })

        # Sort notable accounts by follower count descending
        notable_accounts.sort(key=lambda x: -x["follower_count"])

        return {
            "tier_breakdown": tier_breakdown,
            "notable_accounts": notable_accounts[:5],  # Top 5 notable accounts
            "total_accounts": len(rows),
        }

    # ------------------------------------------------------------------
    # Media ratio
    # ------------------------------------------------------------------

    def _compute_media_ratio(self, narrative_id: str, window_time: datetime) -> float:
        """
        Fraction of tweets containing visual media (photo/video/gif).

        Tries the has_media column first; falls back to URL-based heuristic
        for tweets ingested before v2.
        """
        rows = execute("""
            SELECT COALESCE(has_media, FALSE), content FROM tweets_raw
            WHERE narrative_id = %s AND window_time = %s
            LIMIT 200
        """, (narrative_id, window_time.isoformat()), fetch=True) or []

        if not rows:
            return 0.0

        media_count = 0
        for has_media_flag, content in rows:
            if has_media_flag:
                media_count += 1
            else:
                text = (content or "").lower()
                if any(sig in text for sig in ["pic.twitter", "t.co/", "https://t.co"]):
                    media_count += 1

        return media_count / len(rows)

    # ------------------------------------------------------------------
    # Weighted score with dynamic reweighting
    # ------------------------------------------------------------------

    def _weighted_score(self, components: dict[str, float]) -> float:
        """
        v2 weighted sum with dynamic reweighting.

        When velocity + spread both saturate (>0.95), redistribute 14% of their
        combined weight evenly to engagement + influencer + emotional.
        """
        weights = dict(self._weights)

        vel = components.get("velocity", 0.0)
        spr = components.get("spread", 0.0)
        threshold = config.SATURATION_THRESHOLD
        redistribute = config.SATURATION_REDISTRIBUTE

        if vel > threshold and spr > threshold:
            per_source = redistribute / 2
            weights["velocity"] = weights.get("velocity", 0) - per_source
            weights["spread"] = weights.get("spread", 0) - per_source
            per_target = redistribute / 3
            weights["engagement"] = weights.get("engagement", 0) + per_target
            weights["influencer"] = weights.get("influencer", 0) + per_target
            weights["emotional"] = weights.get("emotional", 0) + per_target

        total = sum(
            components.get(k, 0.0) * weights.get(k, 0.0)
            for k in weights
        )
        return max(0.0, min(1.0, total))

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_window_narratives(self, window_time: datetime) -> list[dict]:
        """Load narratives active in this window with engagement breakdown."""
        rows = execute("""
            SELECT
                nw.narrative_id,
                n.state,
                n.label,
                n.primary_domain,
                n.created_at,
                nw.tweet_count,
                nw.unique_authors,
                COALESCE(
                    (SELECT SUM(t.retweet_count + t.reply_count + t.quote_count + t.like_count)
                     FROM tweets_raw t
                     WHERE t.narrative_id = nw.narrative_id AND t.window_time = nw.window_time),
                    0
                ) AS total_engagement,
                COALESCE(
                    (SELECT SUM(t.retweet_count + t.like_count)
                     FROM tweets_raw t
                     WHERE t.narrative_id = nw.narrative_id AND t.window_time = nw.window_time),
                    0
                ) AS total_likes_rts,
                COALESCE(
                    (SELECT SUM(t.quote_count + t.reply_count)
                     FROM tweets_raw t
                     WHERE t.narrative_id = nw.narrative_id AND t.window_time = nw.window_time),
                    0
                ) AS total_quotes_replies
            FROM narrative_windows nw
            JOIN narratives n ON n.id = nw.narrative_id
            WHERE nw.window_time = %s
        """, (window_time.isoformat(),), fetch=True) or []

        return [
            {
                "narrative_id": str(r[0]),
                "state": r[1],
                "label": r[2],
                "primary_domain": r[3],
                "created_at": r[4],
                "tweet_count": r[5] or 0,
                "unique_authors": r[6] or 0,
                "total_engagement": r[7] or 0,
                "total_likes_rts": r[8] or 0,
                "total_quotes_replies": r[9] or 0,
            }
            for r in rows
        ]

    def _load_narrative_history(self, narrative_id: str, window_time: datetime) -> list[dict]:
        """Load the last N windows of stats for a narrative (excluding current)."""
        lookback_interval = self._lookback * self._window_minutes
        rows = execute("""
            SELECT tweet_count, unique_authors, window_time
            FROM narrative_windows
            WHERE narrative_id = %s
              AND window_time < %s
              AND window_time >= %s::timestamptz - (%s * INTERVAL '1 minute')
            ORDER BY window_time ASC
        """, (
            narrative_id,
            window_time.isoformat(),
            window_time.isoformat(),
            lookback_interval,
        ), fetch=True) or []

        return [
            {"tweet_count": r[0] or 0, "unique_authors": r[1] or 0, "window_time": r[2]}
            for r in rows
        ]

    def _extract_top_terms(self, narrative_id: str, window_time: datetime, limit: int = 5) -> list[str]:
        """Most common terms associated with a narrative this window."""
        rows = execute("""
            SELECT content FROM tweets_raw
            WHERE narrative_id = %s AND window_time = %s
            LIMIT 100
        """, (narrative_id, window_time.isoformat()), fetch=True) or []

        if not rows:
            return []

        word_freq: dict[str, int] = {}
        stop_words = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                      "to", "of", "in", "for", "on", "with", "at", "by", "from",
                      "it", "this", "that", "and", "or", "but", "not", "so",
                      "i", "you", "he", "she", "we", "they", "my", "your", "his",
                      "her", "its", "our", "their", "me", "him", "us", "them",
                      "rt", "https", "http", "co", "amp"}

        for row in rows:
            text = (row[0] or "").lower()
            for word in text.split():
                word = word.strip(".,!?:;\"'()[]{}#@")
                if len(word) > 2 and word not in stop_words and not word.startswith("http"):
                    word_freq[word] = word_freq.get(word, 0) + 1

        sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
        return [w for w, _ in sorted_words[:limit]]

    def _extract_top_tweets(self, narrative_id: str, window_time: datetime, limit: int = 3) -> list[dict]:
        """Highest-engagement tweets for a narrative this window."""
        rows = execute("""
            SELECT t.tweet_id, t.content, t.author_id,
                   t.retweet_count, t.like_count, t.reply_count, t.quote_count,
                   a.username
            FROM tweets_raw t
            LEFT JOIN authors a ON a.author_id = t.author_id
            WHERE t.narrative_id = %s AND t.window_time = %s
            ORDER BY (t.retweet_count + t.like_count + t.quote_count) DESC
            LIMIT %s
        """, (narrative_id, window_time.isoformat(), limit), fetch=True) or []

        return [
            {
                "tweet_id": str(r[0]),
                "content": r[1] or "",
                "author_id": str(r[2]),
                "retweet_count": r[3] or 0,
                "like_count": r[4] or 0,
                "reply_count": r[5] or 0,
                "quote_count": r[6] or 0,
                "author_username": r[7] or "",
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _store_signal(self, record: dict) -> None:
        """Upsert virality signal for this narrative+window."""
        try:
            execute("""
                INSERT INTO virality_signals
                    (narrative_id, window_time, virality_score, components, state,
                     label, primary_domain, tweet_count, unique_authors, top_terms)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (narrative_id, window_time) DO UPDATE SET
                    virality_score = EXCLUDED.virality_score,
                    components     = EXCLUDED.components,
                    state          = EXCLUDED.state,
                    label          = EXCLUDED.label,
                    primary_domain = EXCLUDED.primary_domain,
                    tweet_count    = EXCLUDED.tweet_count,
                    unique_authors = EXCLUDED.unique_authors,
                    top_terms      = EXCLUDED.top_terms
            """, (
                record["narrative_id"],
                record["window_time"].isoformat(),
                record["virality_score"],
                json.dumps(record["components"]),
                record["state"],
                record["label"],
                record["primary_domain"],
                record["tweet_count"],
                record["unique_authors"],
                json.dumps(record["top_terms"]),
            ))
        except Exception as e:
            logger.error(f"Failed to store virality signal: {e}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _sigmoid(x: float, midpoint: float = 0.0, steepness: float = 1.0) -> float:
        """Sigmoid normalisation to [0, 1]."""
        z = steepness * (x - midpoint)
        z = max(min(z, 500), -500)
        return 1.0 / (1.0 + math.exp(-z))
