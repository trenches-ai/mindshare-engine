"""
window_runner.py - 5-minute window orchestrator. Runs the full Phase A pipeline.
"""
from __future__ import annotations
import time
from datetime import datetime, timezone, timedelta
from loguru import logger

from mindshare_engine.config import WINDOW_MINUTES
from mindshare_engine.frontier_builder import FrontierBuilder
from mindshare_engine.twitter_ingest import TwitterIngest
from mindshare_engine.embedder import Embedder
from mindshare_engine.cluster_engine import ClusterEngine
from mindshare_engine.virality_scorer import ViralityScorer
from mindshare_engine.signal_emitter import SignalEmitter
from mindshare_engine.database import execute


class WindowRunner:
    """
    Runs a single 5-minute processing window end-to-end,
    or loops continuously in aligned windows.
    """

    def __init__(self) -> None:
        logger.info("Initialising WindowRunner...")
        self._embedder = Embedder()
        self._frontier = FrontierBuilder()
        self._ingest = TwitterIngest()
        self._cluster = ClusterEngine(self._embedder)
        self._scorer = ViralityScorer()
        self._emitter = SignalEmitter()
        logger.info("WindowRunner ready")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_window(self, window_time: datetime | None = None) -> dict:
        """
        Execute the full pipeline for one window.

        Args:
            window_time: The aligned window start time (UTC). Defaults to now-aligned.

        Returns:
            stats dict with all pipeline metrics.
        """
        if window_time is None:
            window_time = self._aligned_window_time()

        logger.info(f"=== WINDOW START: {window_time.isoformat()} ===")
        t0 = time.time()

        stats: dict = {"window_time": window_time.isoformat()}

        try:
            # Step 1: Build query frontier
            query_set = self._frontier.build_query_set(window_time)
            stats["queries_planned"] = len(query_set)
            logger.info(f"Frontier: {len(query_set)} queries planned")

            # Step 2: Ingest tweets
            ingest_result = self._ingest.ingest_window(query_set, window_time)
            tweets = ingest_result["tweets"]
            authors = ingest_result.get("authors", [])
            stats["ingest"] = ingest_result["stats"]
            logger.info(f"Ingested {len(tweets)} tweets from {len(authors)} authors")

            # Step 3: Store authors
            self._store_authors(authors)

            # Step 4: Embed + cluster
            cluster_result = self._cluster.process_tweets(tweets, window_time)
            stats["cluster"] = cluster_result
            logger.info(f"Cluster: {cluster_result}")

            # Step 5: Narrative window stats
            narrative_stats = self._cluster.compute_narrative_window_stats(window_time)
            stats["narratives_updated"] = len(narrative_stats)

            # Step 6: Lane aggregates
            self._cluster.compute_lane_stats(window_time)

            # Step 7: Update frontier velocity
            self._update_frontier_from_window(tweets, window_time)

            # Step 8: Virality scoring
            scored = self._scorer.score_window(window_time)
            stats["virality"] = {
                "scored": len(scored),
                "top_score": scored[0]["virality_score"] if scored else 0,
                "top_label": scored[0].get("label", "") if scored else "",
            }

            # Step 9: Signal emission to bot
            emission_stats = self._emitter.emit(scored, window_time)
            stats["signals"] = emission_stats

            stats["duration_seconds"] = round(time.time() - t0, 2)
            logger.info(f"=== WINDOW DONE: {stats['duration_seconds']}s ===")

        except Exception as e:
            logger.error(f"Window pipeline error: {e}", exc_info=True)
            stats["error"] = str(e)
            stats["duration_seconds"] = round(time.time() - t0, 2)

        return stats

    def run_continuous(self) -> None:
        """
        Run windows in a continuous aligned loop.
        Sleeps until the next aligned window boundary.
        """
        logger.info(f"Starting continuous mode — {WINDOW_MINUTES}-minute windows")
        while True:
            next_window = self._next_aligned_window_time()
            now = datetime.now(tz=timezone.utc)
            sleep_secs = (next_window - now).total_seconds()

            if sleep_secs > 0:
                logger.info(f"Sleeping {sleep_secs:.1f}s until next window at {next_window.isoformat()}")
                time.sleep(sleep_secs)

            self.run_window(next_window)

    # ------------------------------------------------------------------
    # Window time helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _aligned_window_time(dt: datetime | None = None) -> datetime:
        """Floor datetime to the nearest WINDOW_MINUTES boundary (UTC)."""
        if dt is None:
            dt = datetime.now(tz=timezone.utc)
        minutes = dt.minute - (dt.minute % WINDOW_MINUTES)
        return dt.replace(minute=minutes, second=0, microsecond=0)

    @staticmethod
    def _next_aligned_window_time() -> datetime:
        """Next aligned window boundary from now."""
        now = datetime.now(tz=timezone.utc)
        minutes = now.minute - (now.minute % WINDOW_MINUTES) + WINDOW_MINUTES
        base = now.replace(minute=0, second=0, microsecond=0)
        return base + timedelta(minutes=minutes)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _store_authors(self, authors: list[dict]) -> None:
        """Upsert author records."""
        for author in authors:
            try:
                execute("""
                    INSERT INTO authors (author_id, username, account_created_at, follower_count, fetched_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (author_id) DO UPDATE SET
                        follower_count = EXCLUDED.follower_count,
                        fetched_at     = NOW()
                """, (
                    author["author_id"],
                    author.get("username", ""),
                    author.get("account_created_at"),
                    author.get("follower_count", 0),
                ))
            except Exception as e:
                logger.error(f"Author store error: {e}")

    def _update_frontier_from_window(self, tweets: list[dict], window_time: datetime) -> None:
        """
        Compute per-query-term velocity from this window and update the frontier.
        Velocity = tweet count this window / expected baseline (use 10 as soft baseline).
        """
        term_counts: dict[str, dict] = {}
        for tweet in tweets:
            term = tweet.get("query_term", "")
            lane = tweet.get("query_lane", "")
            if not term:
                continue
            if term not in term_counts:
                term_counts[term] = {"count": 0, "lane": lane}
            term_counts[term]["count"] += 1

        baseline = 10.0
        for term, data in term_counts.items():
            velocity = data["count"] / baseline
            self._frontier.update_frontier(term, data["lane"], velocity, window_time)
