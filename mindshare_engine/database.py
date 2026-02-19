"""
database.py - Postgres schema, connection pool, and helpers.
"""
from __future__ import annotations
import psycopg2
from psycopg2 import pool
from loguru import logger
from mindshare_engine.config import DATABASE_URL

_pool: pool.SimpleConnectionPool | None = None


def get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
        _pool = pool.SimpleConnectionPool(1, 10, DATABASE_URL)
        logger.info("DB connection pool created")
    return _pool


def get_connection() -> psycopg2.extensions.connection:
    return get_pool().getconn()


def release_connection(conn: psycopg2.extensions.connection) -> None:
    get_pool().putconn(conn)


def init_db() -> None:
    """Create all tables if they do not exist."""
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS narratives (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                centroid        JSONB,
                primary_domain  TEXT,
                secondary_domains JSONB DEFAULT '[]',
                state           TEXT DEFAULT 'incubating',
                label           TEXT,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                updated_at      TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS narrative_windows (
                id              BIGSERIAL PRIMARY KEY,
                narrative_id    UUID REFERENCES narratives(id) ON DELETE CASCADE,
                window_time     TIMESTAMPTZ,
                unique_authors  INT DEFAULT 0,
                tweet_count     INT DEFAULT 0,
                domain_distribution JSONB DEFAULT '{}',
                features        JSONB DEFAULT '{}',
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_nw_narrative_window
                ON narrative_windows(narrative_id, window_time);
            CREATE INDEX IF NOT EXISTS idx_nw_window_time
                ON narrative_windows(window_time);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS tweets_raw (
                tweet_id        TEXT PRIMARY KEY,
                narrative_id    UUID REFERENCES narratives(id) ON DELETE SET NULL,
                author_id       TEXT,
                content         TEXT,
                embedding       JSONB,
                window_time     TIMESTAMPTZ,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                retweet_count   INT DEFAULT 0,
                reply_count     INT DEFAULT 0,
                quote_count     INT DEFAULT 0,
                like_count      INT DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_tweets_narrative ON tweets_raw(narrative_id);
            CREATE INDEX IF NOT EXISTS idx_tweets_window ON tweets_raw(window_time);
            CREATE INDEX IF NOT EXISTS idx_tweets_author ON tweets_raw(author_id);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS authors (
                author_id           TEXT PRIMARY KEY,
                username            TEXT,
                account_created_at  TIMESTAMPTZ,
                follower_count      INT DEFAULT 0,
                fetched_at          TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS lane_windows (
                id              BIGSERIAL PRIMARY KEY,
                lane            TEXT,
                window_time     TIMESTAMPTZ,
                lane_intensity  FLOAT DEFAULT 0,
                narrative_count INT DEFAULT 0,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(lane, window_time)
            );
            CREATE INDEX IF NOT EXISTS idx_lw_window ON lane_windows(window_time);
            CREATE INDEX IF NOT EXISTS idx_lw_lane ON lane_windows(lane);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id              BIGSERIAL PRIMARY KEY,
                narrative_id    UUID REFERENCES narratives(id) ON DELETE SET NULL,
                alert_type      TEXT,
                window_time     TIMESTAMPTZ,
                data            JSONB DEFAULT '{}',
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_window ON alerts(window_time);
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS frontier_terms (
                term            TEXT PRIMARY KEY,
                lane            TEXT,
                velocity        FLOAT DEFAULT 0,
                reward_score    FLOAT DEFAULT 0,
                last_seen       TIMESTAMPTZ DEFAULT NOW(),
                created_at      TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE INDEX IF NOT EXISTS idx_ft_lane ON frontier_terms(lane);
            CREATE INDEX IF NOT EXISTS idx_ft_velocity ON frontier_terms(velocity DESC);
        """)

        conn.commit()
        logger.info("Database schema initialised")
    except Exception as e:
        conn.rollback()
        logger.error(f"DB init error: {e}")
        raise
    finally:
        cur.close()
        release_connection(conn)


def execute(sql: str, params: tuple = (), fetch: bool = False):
    """Run a parameterised query, optionally returning rows."""
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        result = cur.fetchall() if fetch else None
        conn.commit()
        return result
    except Exception as e:
        conn.rollback()
        logger.error(f"DB execute error: {e} | SQL: {sql[:120]}")
        raise
    finally:
        cur.close()
        release_connection(conn)
