"""
twitter_ingest.py - X Pro API ingestion with rate limit tracking and deduplication.
"""
from __future__ import annotations
import time
from datetime import datetime
from loguru import logger

import tweepy

from mindshare_engine.config import TWITTER_BEARER_TOKEN
from mindshare_engine.database import execute


class TwitterIngest:
    """
    Wraps Tweepy v2 client for windowed ingestion.
    Tracks rate limits and deduplicates against tweets_raw.
    """

    def __init__(self) -> None:
        if not TWITTER_BEARER_TOKEN:
            logger.warning("TWITTER_BEARER_TOKEN not set — ingest will be a no-op")
            self._client = None
        else:
            self._client = tweepy.Client(
                bearer_token=TWITTER_BEARER_TOKEN,
                wait_on_rate_limit=False,
            )
        self._remaining_calls = 300
        self._reset_at: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ingest_window(self, query_set: list[dict], window_time: datetime) -> dict:
        """
        Run all queries in query_set, return collected tweets and authors.

        Returns:
            {tweets: list[dict], author_ids: set[str], stats: dict}
        """
        if not self._client:
            logger.warning("No Twitter client — skipping ingest")
            return {"tweets": [], "author_ids": set(), "stats": {"skipped": True}}

        all_tweets: list[dict] = []
        author_ids: set[str] = set()
        queries_run = 0
        tweets_fetched = 0
        tweets_skipped = 0

        # Load existing tweet IDs for dedup (recent window only)
        existing_ids = self._load_existing_ids(window_time)

        for q in query_set:
            if self._remaining_calls <= 5:
                logger.warning("Rate limit budget low — stopping early")
                break

            term = q["term"]
            try:
                tweets = self._search_recent(term, max_results=50)
                queries_run += 1

                for t in tweets:
                    if t["tweet_id"] in existing_ids:
                        tweets_skipped += 1
                        continue
                    t["query_term"] = term
                    t["query_lane"] = q["lane"]
                    t["window_time"] = window_time.isoformat()
                    all_tweets.append(t)
                    author_ids.add(t["author_id"])
                    existing_ids.add(t["tweet_id"])
                    tweets_fetched += 1

            except tweepy.TooManyRequests:
                logger.warning(f"Rate limit hit on query '{term}' — stopping ingest")
                self._remaining_calls = 0
                break
            except tweepy.TwitterServerError as e:
                logger.error(f"Twitter server error on '{term}': {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error on '{term}': {e}")
                continue

        # Fetch author metadata in batches
        authors = self._fetch_authors(list(author_ids)) if author_ids else []

        stats = {
            "queries_run": queries_run,
            "tweets_fetched": tweets_fetched,
            "tweets_skipped_dedup": tweets_skipped,
            "unique_authors": len(author_ids),
            "remaining_calls": self._remaining_calls,
        }
        logger.info(f"Ingest window complete: {stats}")
        return {"tweets": all_tweets, "authors": authors, "author_ids": author_ids, "stats": stats}

    def search_recent(self, query_term: str, max_results: int = 100, since_id: str | None = None) -> list[dict]:
        """Public single-query method."""
        return self._search_recent(query_term, max_results, since_id)

    def fetch_authors(self, author_ids: list[str]) -> list[dict]:
        """Public batch author fetch."""
        return self._fetch_authors(author_ids)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _search_recent(self, query_term: str, max_results: int = 50, since_id: str | None = None) -> list[dict]:
        """Search recent tweets for a query term."""
        query = f"{query_term} -is:retweet lang:en"
        kwargs: dict = {
            "query": query,
            "max_results": min(max_results, 100),
            "tweet_fields": ["created_at", "author_id", "public_metrics", "conversation_id", "attachments"],
            "expansions": ["author_id", "attachments.media_keys"],
            "media_fields": ["type"],
            "user_fields": ["username"],
        }
        if since_id:
            kwargs["since_id"] = since_id

        try:
            response = self._client.search_recent_tweets(**kwargs)
            self._remaining_calls -= 1

            if not response.data:
                return []

            user_map = {}
            if response.includes and "users" in response.includes:
                for u in response.includes["users"]:
                    user_map[str(u.id)] = u.username

            media_keys_with_visual = set()
            if response.includes and "media" in response.includes:
                for m in response.includes["media"]:
                    if m.type in ("photo", "video", "animated_gif"):
                        media_keys_with_visual.add(m.media_key)

            results = []
            for tweet in response.data:
                metrics = tweet.public_metrics or {}
                author_id = str(tweet.author_id)
                attachments = tweet.attachments or {}
                tweet_media_keys = attachments.get("media_keys", []) or []
                has_media = any(mk in media_keys_with_visual for mk in tweet_media_keys)

                results.append({
                    "tweet_id": str(tweet.id),
                    "author_id": author_id,
                    "author_username": user_map.get(author_id, ""),
                    "content": tweet.text,
                    "created_at": tweet.created_at.isoformat() if tweet.created_at else None,
                    "retweet_count": metrics.get("retweet_count", 0),
                    "reply_count": metrics.get("reply_count", 0),
                    "quote_count": metrics.get("quote_count", 0),
                    "like_count": metrics.get("like_count", 0),
                    "has_media": has_media,
                })
            return results

        except tweepy.TooManyRequests:
            raise
        except Exception as e:
            logger.error(f"Search error for '{query_term}': {e}")
            return []

    def _fetch_authors(self, author_ids: list[str]) -> list[dict]:
        """Batch-fetch author metadata (up to 100 per call)."""
        results = []
        for i in range(0, len(author_ids), 100):
            batch = author_ids[i:i + 100]
            try:
                response = self._client.get_users(
                    ids=batch,
                    user_fields=["created_at", "public_metrics"],
                )
                self._remaining_calls -= 1
                if not response.data:
                    continue
                for user in response.data:
                    metrics = user.public_metrics or {}
                    results.append({
                        "author_id": str(user.id),
                        "username": user.username,
                        "account_created_at": user.created_at.isoformat() if user.created_at else None,
                        "follower_count": metrics.get("followers_count", 0),
                    })
            except tweepy.TooManyRequests:
                logger.warning("Rate limit hit fetching authors")
                break
            except Exception as e:
                logger.error(f"Author fetch error: {e}")
        return results

    def _load_existing_ids(self, window_time: datetime) -> set[str]:
        """Load tweet IDs from current and previous window for dedup."""
        rows = execute("""
            SELECT tweet_id FROM tweets_raw
            WHERE window_time >= %s::timestamptz - INTERVAL '10 minutes'
        """, (window_time.isoformat(),), fetch=True) or []
        return {row[0] for row in rows}
