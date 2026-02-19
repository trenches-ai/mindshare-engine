"""
cluster_engine.py - Narrative clustering, birth detection, domain assignment.
"""
from __future__ import annotations
import json
import uuid
from datetime import datetime
from loguru import logger
import numpy as np

from mindshare_engine import config
from mindshare_engine.database import execute, get_connection, release_connection
from mindshare_engine.embedder import Embedder


class ClusterEngine:
    """
    Assigns tweets to existing narratives or creates new ones.
    Computes domain distributions via cosine similarity to seed embeddings.
    """

    def __init__(self, embedder: Embedder) -> None:
        self._embedder = embedder
        self._domain_seed_embeddings: dict[str, np.ndarray] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_tweets(self, tweets: list[dict], window_time: datetime) -> dict:
        """
        Main entry: embed tweets, assign to narratives, detect births.

        Returns stats dict.
        """
        if not tweets:
            return {"assigned": 0, "new_narratives": 0, "births": 0}

        texts = [t["content"] for t in tweets]
        embeddings = self._embedder.embed_texts(texts)

        # Load existing active narratives
        active_narratives = self._load_active_narratives()

        assigned = 0
        new_narratives = 0

        for tweet, emb in zip(tweets, embeddings):
            narrative_id = self._assign_to_narrative(emb, active_narratives)

            if narrative_id is None:
                # Create new narrative
                domain_dist = self._assign_domain(emb)
                primary = max(domain_dist, key=domain_dist.get)
                narrative_id = self._create_narrative(emb, domain_dist, primary, window_time)
                active_narratives[narrative_id] = {
                    "id": narrative_id,
                    "centroid": emb,
                    "primary_domain": primary,
                }
                new_narratives += 1
            else:
                # Update centroid (rolling average)
                self._update_centroid(narrative_id, emb, active_narratives)
                assigned += 1

            # Store tweet with narrative assignment
            self._store_tweet(tweet, narrative_id, emb, window_time)

        # Detect births for this window
        births = self._detect_births(window_time)

        return {
            "assigned": assigned,
            "new_narratives": new_narratives,
            "births": births,
            "total_tweets": len(tweets),
        }

    def compute_narrative_window_stats(self, window_time: datetime) -> list[dict]:
        """
        For each active narrative, compute per-window stats and upsert narrative_windows.
        Returns list of narrative stats dicts.
        """
        rows = execute("""
            SELECT
                t.narrative_id,
                COUNT(DISTINCT t.author_id) AS unique_authors,
                COUNT(*) AS tweet_count,
                n.primary_domain
            FROM tweets_raw t
            JOIN narratives n ON n.id = t.narrative_id
            WHERE t.window_time = %s
            GROUP BY t.narrative_id, n.primary_domain
        """, (window_time.isoformat(),), fetch=True) or []

        stats = []
        for row in rows:
            narrative_id, unique_authors, tweet_count, primary_domain = row
            features = {
                "unique_authors": unique_authors,
                "tweet_count": tweet_count,
                "primary_domain": primary_domain,
            }
            execute("""
                INSERT INTO narrative_windows
                    (narrative_id, window_time, unique_authors, tweet_count, features)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
            """, (
                str(narrative_id),
                window_time.isoformat(),
                unique_authors,
                tweet_count,
                json.dumps(features),
            ))
            stats.append(features)

        return stats

    def compute_lane_stats(self, window_time: datetime) -> None:
        """Aggregate per-lane intensity into lane_windows."""
        rows = execute("""
            SELECT n.primary_domain, COUNT(DISTINCT nw.narrative_id), SUM(nw.unique_authors)
            FROM narrative_windows nw
            JOIN narratives n ON n.id = nw.narrative_id
            WHERE nw.window_time = %s
            GROUP BY n.primary_domain
        """, (window_time.isoformat(),), fetch=True) or []

        for row in rows:
            lane, narrative_count, lane_intensity = row
            execute("""
                INSERT INTO lane_windows (lane, window_time, lane_intensity, narrative_count)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (lane, window_time) DO UPDATE SET
                    lane_intensity  = EXCLUDED.lane_intensity,
                    narrative_count = EXCLUDED.narrative_count
            """, (lane, window_time.isoformat(), float(lane_intensity or 0), int(narrative_count or 0)))

    # ------------------------------------------------------------------
    # Domain assignment
    # ------------------------------------------------------------------

    def _get_domain_seed_embeddings(self) -> dict[str, np.ndarray]:
        """Lazy-load domain centroid embeddings from seed lexicons."""
        if self._domain_seed_embeddings is None:
            logger.info("Building domain seed embeddings...")
            self._domain_seed_embeddings = {}
            for domain, terms in config.DOMAIN_SEED_LEXICONS.items():
                vecs = self._embedder.embed_texts(terms)
                self._domain_seed_embeddings[domain] = vecs.mean(axis=0)
            logger.info("Domain seed embeddings ready")
        return self._domain_seed_embeddings

    def _assign_domain(self, embedding: np.ndarray) -> dict[str, float]:
        """Return probability distribution over domains via cosine similarity."""
        seed_embs = self._get_domain_seed_embeddings()
        scores = {}
        for domain, centroid in seed_embs.items():
            scores[domain] = float(self._embedder.cosine_similarity(embedding, centroid))

        # Softmax normalisation (shift by max for stability)
        import math
        vals = list(scores.values())
        max_v = max(vals)
        exp_vals = [math.exp(v - max_v) for v in vals]
        total = sum(exp_vals)
        domains = list(scores.keys())
        return {d: exp_vals[i] / total for i, d in enumerate(domains)}

    # ------------------------------------------------------------------
    # Narrative assignment & creation
    # ------------------------------------------------------------------

    def _assign_to_narrative(
        self,
        embedding: np.ndarray,
        active_narratives: dict,
    ) -> str | None:
        """Find best-matching narrative above similarity threshold, or None."""
        best_id = None
        best_sim = config.CLUSTER_SIMILARITY_THRESHOLD

        for nid, data in active_narratives.items():
            sim = self._embedder.cosine_similarity(embedding, data["centroid"])
            if sim > best_sim:
                best_sim = sim
                best_id = nid

        return best_id

    def _create_narrative(
        self,
        embedding: np.ndarray,
        domain_dist: dict[str, float],
        primary_domain: str,
        window_time: datetime,
    ) -> str:
        """Insert new narrative row, return its UUID."""
        nid = str(uuid.uuid4())
        secondary = [d for d, p in sorted(domain_dist.items(), key=lambda x: -x[1]) if d != primary_domain][:3]
        execute("""
            INSERT INTO narratives (id, centroid, primary_domain, secondary_domains, state, label)
            VALUES (%s, %s, %s, %s, 'incubating', %s)
        """, (
            nid,
            json.dumps(embedding.tolist()),
            primary_domain,
            json.dumps(secondary),
            f"{primary_domain}_{window_time.strftime('%H%M')}",
        ))
        return nid

    def _update_centroid(self, narrative_id: str, new_emb: np.ndarray, active_narratives: dict) -> None:
        """Rolling average centroid update (alpha=0.1)."""
        alpha = 0.1
        current = active_narratives[narrative_id]["centroid"]
        updated = (1 - alpha) * current + alpha * new_emb
        active_narratives[narrative_id]["centroid"] = updated
        execute("""
            UPDATE narratives SET centroid = %s, updated_at = NOW() WHERE id = %s
        """, (json.dumps(updated.tolist()), narrative_id))

    # ------------------------------------------------------------------
    # Birth detection
    # ------------------------------------------------------------------

    def _detect_births(self, window_time: datetime) -> int:
        """
        Birth conditions:
          - unique_authors >= MIN_AUTHORS_FOR_BIRTH
          - narrative active in <= 2 consecutive windows (new)
          - state = 'incubating'
        Marks qualifying narratives as 'emerging'.
        Returns count of births.
        """
        rows = execute("""
            SELECT nw.narrative_id, SUM(nw.unique_authors) AS total_authors, COUNT(*) AS window_count
            FROM narrative_windows nw
            JOIN narratives n ON n.id = nw.narrative_id
            WHERE n.state = 'incubating'
              AND nw.window_time >= %s::timestamptz - INTERVAL '10 minutes'
            GROUP BY nw.narrative_id
            HAVING SUM(nw.unique_authors) >= %s
               AND COUNT(*) <= 2
        """, (window_time.isoformat(), config.MIN_AUTHORS_FOR_BIRTH), fetch=True) or []

        for row in rows:
            narrative_id = str(row[0])
            execute("""
                UPDATE narratives SET state = 'incubating', updated_at = NOW() WHERE id = %s
            """, (narrative_id,))
            logger.info(f"Birth detected: narrative {narrative_id}")

        return len(rows)

    # ------------------------------------------------------------------
    # Data loaders
    # ------------------------------------------------------------------

    def _load_active_narratives(self) -> dict:
        """Load narratives updated in the last 2 hours."""
        rows = execute("""
            SELECT id, centroid, primary_domain FROM narratives
            WHERE state NOT IN ('dormant') AND updated_at > NOW() - INTERVAL '2 hours'
        """, fetch=True) or []

        result = {}
        for row in rows:
            nid, centroid_json, primary_domain = row
            centroid = np.array(json.loads(centroid_json)) if centroid_json else None
            if centroid is not None:
                result[str(nid)] = {
                    "id": str(nid),
                    "centroid": centroid,
                    "primary_domain": primary_domain,
                }
        return result

    def _store_tweet(self, tweet: dict, narrative_id: str, embedding: np.ndarray, window_time: datetime) -> None:
        """Persist tweet to tweets_raw."""
        try:
            execute("""
                INSERT INTO tweets_raw
                    (tweet_id, narrative_id, author_id, content, embedding, window_time,
                     retweet_count, reply_count, quote_count, like_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tweet_id) DO NOTHING
            """, (
                tweet["tweet_id"],
                narrative_id,
                tweet["author_id"],
                tweet["content"],
                json.dumps(embedding.tolist()),
                window_time.isoformat(),
                tweet.get("retweet_count", 0),
                tweet.get("reply_count", 0),
                tweet.get("quote_count", 0),
                tweet.get("like_count", 0),
            ))
        except Exception as e:
            logger.error(f"Failed to store tweet {tweet.get('tweet_id')}: {e}")
