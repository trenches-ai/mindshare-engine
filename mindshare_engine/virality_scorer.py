"""
virality_scorer.py - Composite virality index for narrative breakout detection.

Scores each active narrative on six dimensions per window:
  1. Velocity      — tweet volume relative to recent baseline
  2. Acceleration  — velocity change (derivative) across recent windows
  3. Spread        — unique author growth rate
  4. Engagement    — amplification ratio (retweets + quotes + likes per tweet)
  5. Influencer    — high-follower author participation signal
  6. Freshness     — recency bonus (newer narratives score higher)

The final virality_score is a weighted sum normalised to [0, 1].
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
        """
        Compute virality scores for every active narrative in this window.
        Stores results in virality_signals and returns the list of scored narratives.
        """
        narratives = self._load_window_narratives(window_time)
        if not narratives:
            logger.debug("No narratives to score this window")
            return []

        scored = []
        for n in narratives:
            nid = str(n["narrative_id"])
            history = self._load_narrative_history(nid, window_time)

            components = self._compute_components(n, history, window_time)
            virality_score = self._weighted_score(components)

            record = {
                "narrative_id": nid,
                "window_time": window_time,
                "virality_score": round(virality_score, 4),
                "components": components,
                "state": n["state"],
                "label": n["label"],
                "primary_domain": n["primary_domain"],
                "tweet_count": n["tweet_count"],
                "unique_authors": n["unique_authors"],
                "top_terms": self._extract_top_terms(nid, window_time),
            }
            self._store_signal(record)
            scored.append(record)

        scored.sort(key=lambda x: x["virality_score"], reverse=True)
        above_threshold = sum(1 for s in scored if s["virality_score"] >= self._signal_threshold)
        logger.info(
            f"Virality scoring: {len(scored)} narratives, "
            f"{above_threshold} above signal threshold ({self._signal_threshold})"
        )
        return scored

    # ------------------------------------------------------------------
    # Component calculations
    # ------------------------------------------------------------------

    def _compute_components(
        self,
        current: dict,
        history: list[dict],
        window_time: datetime,
    ) -> dict[str, float]:
        velocity = self._velocity(current, history)
        acceleration = self._acceleration(current, history)
        spread = self._spread(current, history)
        engagement = self._engagement(current)
        influencer = self._influencer_signal(current["narrative_id"], window_time)
        freshness = self._freshness(current, window_time)

        return {
            "velocity": round(velocity, 4),
            "acceleration": round(acceleration, 4),
            "spread": round(spread, 4),
            "engagement": round(engagement, 4),
            "influencer": round(influencer, 4),
            "freshness": round(freshness, 4),
        }

    def _velocity(self, current: dict, history: list[dict]) -> float:
        """Tweet count this window vs rolling baseline. Sigmoid-normalised to [0,1]."""
        tc = current["tweet_count"]
        if not history:
            return self._sigmoid(tc, midpoint=10, steepness=0.3)

        baseline = sum(h["tweet_count"] for h in history) / len(history)
        if baseline < 1:
            baseline = 1.0
        ratio = tc / baseline
        return self._sigmoid(ratio, midpoint=2.0, steepness=1.5)

    def _acceleration(self, current: dict, history: list[dict]) -> float:
        """Rate of change in velocity (second derivative). Measures if growth is speeding up."""
        if len(history) < 2:
            return 0.5

        counts = [h["tweet_count"] for h in history] + [current["tweet_count"]]
        deltas = [counts[i] - counts[i - 1] for i in range(1, len(counts))]
        if len(deltas) < 2:
            return 0.5

        recent_delta = deltas[-1]
        prior_avg = sum(deltas[:-1]) / len(deltas[:-1])

        if prior_avg == 0:
            accel = float(recent_delta)
        else:
            accel = (recent_delta - prior_avg) / abs(prior_avg)

        return self._sigmoid(accel, midpoint=0.0, steepness=1.0)

    def _spread(self, current: dict, history: list[dict]) -> float:
        """Unique author growth rate — how fast new voices are joining."""
        authors_now = current["unique_authors"]
        if not history:
            return self._sigmoid(authors_now, midpoint=5, steepness=0.4)

        authors_prev = history[-1].get("unique_authors", 1) or 1
        growth = (authors_now - authors_prev) / authors_prev
        return self._sigmoid(growth, midpoint=0.5, steepness=2.0)

    def _engagement(self, current: dict) -> float:
        """Amplification ratio: total engagement actions per tweet."""
        tc = max(current["tweet_count"], 1)
        total_engagement = current.get("total_engagement", 0)
        ratio = total_engagement / tc
        return self._sigmoid(ratio, midpoint=10.0, steepness=0.2)

    def _influencer_signal(self, narrative_id: str, window_time: datetime) -> float:
        """Fraction of tweets from high-follower authors (>10k followers)."""
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
        return self._sigmoid(fraction, midpoint=0.1, steepness=10.0)

    def _freshness(self, current: dict, window_time: datetime) -> float:
        """Recency bonus — narratives born recently score higher."""
        created = current.get("created_at")
        if not created:
            return 0.5

        if isinstance(created, str):
            try:
                created = datetime.fromisoformat(created)
            except (ValueError, TypeError):
                return 0.5

        age_minutes = (window_time - created).total_seconds() / 60.0
        age_windows = age_minutes / self._window_minutes
        return self._sigmoid(-age_windows, midpoint=-12, steepness=0.3)

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_window_narratives(self, window_time: datetime) -> list[dict]:
        """Load narratives active in this window with their stats."""
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
                ) AS total_engagement
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
              AND window_time >= %s::timestamptz - INTERVAL '%s minutes'
            ORDER BY window_time ASC
        """, (
            narrative_id,
            window_time.isoformat(),
            window_time.isoformat(),
            str(lookback_interval),
        ), fetch=True) or []

        return [
            {"tweet_count": r[0] or 0, "unique_authors": r[1] or 0, "window_time": r[2]}
            for r in rows
        ]

    def _extract_top_terms(self, narrative_id: str, window_time: datetime, limit: int = 5) -> list[str]:
        """Extract the most common query terms associated with a narrative this window."""
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

    def _weighted_score(self, components: dict[str, float]) -> float:
        """Weighted sum of components, clamped to [0, 1]."""
        total = sum(
            components.get(k, 0.0) * self._weights.get(k, 0.0)
            for k in self._weights
        )
        return max(0.0, min(1.0, total))
