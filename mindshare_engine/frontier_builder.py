"""
frontier_builder.py - 3-layer query frontier with exploit/balance/explore budget split.
"""
from __future__ import annotations
import json
import random
from datetime import datetime
from loguru import logger

from mindshare_engine import config
from mindshare_engine.database import execute


class FrontierBuilder:
    """
    Builds the query set for each 5-minute window.

    Budget split:
      Layer A (50%) — High-velocity frontier terms (exploitation)
      Layer B (30%) — Per-lane coverage balancing
      Layer C (20%) — Random exploration from bigrams + seed lexicon
    """

    def __init__(self) -> None:
        self._seed_embeddings: dict | None = None  # lazy init

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_query_set(self, window_time: datetime) -> list[dict]:
        """
        Build the ordered query set for a window.

        Returns a list of dicts:
            {term, lane, layer, priority}
        """
        max_terms = config.MAX_TERMS_PER_WINDOW
        budget_a = int(max_terms * config.BUDGET_EXPLOITATION)  # 30
        budget_b = int(max_terms * config.BUDGET_LANE_BALANCE)  # 18
        budget_c = int(max_terms * config.BUDGET_EXPLORATION)   # 12

        layer_a = self._layer_a(budget_a)
        layer_b = self._layer_b(budget_b, existing_terms={t["term"] for t in layer_a})
        layer_c = self._layer_c(budget_c, existing_terms={t["term"] for t in layer_a + layer_b})

        query_set = layer_a + layer_b + layer_c
        logger.debug(f"Frontier built: A={len(layer_a)} B={len(layer_b)} C={len(layer_c)}")
        return query_set

    def update_frontier(self, term: str, lane: str, velocity: float, window_time: datetime) -> None:
        """Upsert a term's velocity/reward into frontier_terms."""
        reward = min(velocity, 10.0)  # cap reward
        execute("""
            INSERT INTO frontier_terms (term, lane, velocity, reward_score, last_seen)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (term) DO UPDATE SET
                velocity    = EXCLUDED.velocity,
                reward_score = EXCLUDED.reward_score,
                lane         = EXCLUDED.lane,
                last_seen    = EXCLUDED.last_seen
        """, (term, lane, velocity, reward, window_time))

    # ------------------------------------------------------------------
    # Layer A — Exploitation: top-velocity terms from DB
    # ------------------------------------------------------------------

    def _layer_a(self, budget: int) -> list[dict]:
        rows = execute("""
            SELECT term, lane, velocity FROM frontier_terms
            ORDER BY velocity DESC, reward_score DESC
            LIMIT %s
        """, (budget,), fetch=True) or []

        return [
            {"term": row[0], "lane": row[1], "layer": "A", "priority": idx}
            for idx, row in enumerate(rows)
        ]

    # ------------------------------------------------------------------
    # Layer B — Lane balancing: boost under-sampled lanes
    # ------------------------------------------------------------------

    def _layer_b(self, budget: int, existing_terms: set[str]) -> list[dict]:
        """
        For each lane compute coverage ratio and pick seed terms for under-covered lanes.
        Coverage ratio = observed (in DB) / expected (uniform baseline).
        """
        # Count narratives per lane in recent windows
        rows = execute("""
            SELECT primary_domain, COUNT(*) as cnt
            FROM narratives
            WHERE updated_at > NOW() - INTERVAL '30 minutes'
            GROUP BY primary_domain
        """, fetch=True) or []

        lane_counts = {row[0]: row[1] for row in rows}
        total = sum(lane_counts.values()) or 1
        expected_per_lane = total / len(config.DOMAINS)

        # Sort lanes by under-coverage (low ratio first)
        coverage = {
            lane: lane_counts.get(lane, 0) / max(expected_per_lane, 1)
            for lane in config.DOMAINS
        }
        sorted_lanes = sorted(coverage.items(), key=lambda x: x[1])

        results = []
        per_lane = max(1, budget // max(len(sorted_lanes), 1))

        for lane, ratio in sorted_lanes:
            if len(results) >= budget:
                break
            # Pick seed terms not already in query set
            candidates = [
                t for t in config.DOMAIN_SEED_LEXICONS.get(lane, [])
                if t not in existing_terms
            ]
            chosen = candidates[:per_lane]
            for term in chosen:
                results.append({
                    "term": term,
                    "lane": lane,
                    "layer": "B",
                    "priority": len(results),
                })
            existing_terms.update(chosen)

        return results

    # ------------------------------------------------------------------
    # Layer C — Exploration: random seed terms + DB bigrams
    # ------------------------------------------------------------------

    def _layer_c(self, budget: int, existing_terms: set[str]) -> list[dict]:
        results = []

        # Random seed terms from random lanes
        lanes_shuffled = random.sample(config.DOMAINS, len(config.DOMAINS))
        for lane in lanes_shuffled:
            if len(results) >= budget:
                break
            candidates = [
                t for t in config.DOMAIN_SEED_LEXICONS.get(lane, [])
                if t not in existing_terms
            ]
            if candidates:
                term = random.choice(candidates)
                results.append({
                    "term": term,
                    "lane": lane,
                    "layer": "C",
                    "priority": len(results),
                })
                existing_terms.add(term)

        return results
