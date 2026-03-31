"""
Smoke test for Mindshare Engine — validates all core components locally
without requiring a live PostgreSQL database.

Usage:
    python test_smoke.py
"""
import sys
import math
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \033[92mPASS\033[0m  {name}")
    else:
        FAIL += 1
        print(f"  \033[91mFAIL\033[0m  {name}  {detail}")


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ── 1. Config ──────────────────────────────────────────────────────────
section("CONFIG")

from mindshare_engine.config import (
    DOMAINS, DOMAIN_SEED_LEXICONS, VIRALITY_WEIGHTS,
    LIFECYCLE_STATES, VIRALITY_SIGNAL_THRESHOLD, VIRALITY_ALERT_THRESHOLD,
)

check("16 domains loaded", len(DOMAINS) == 16, f"got {len(DOMAINS)}")
check("Seed lexicon per domain", all(d in DOMAIN_SEED_LEXICONS for d in DOMAINS))
check("Each lexicon has 10 terms", all(len(v) == 10 for v in DOMAIN_SEED_LEXICONS.values()))
check("Virality weights sum to 1.0", abs(sum(VIRALITY_WEIGHTS.values()) - 1.0) < 1e-6)
check("11 virality components (v4)", len(VIRALITY_WEIGHTS) == 11)
check("6 lifecycle states", len(LIFECYCLE_STATES) == 6)
check("Signal threshold < alert threshold", VIRALITY_SIGNAL_THRESHOLD < VIRALITY_ALERT_THRESHOLD)


# ── 2. Embedder ────────────────────────────────────────────────────────
section("EMBEDDER")

print("  Loading embedding model (may take a moment)...")
from mindshare_engine.embedder import Embedder

embedder = Embedder()

single = embedder.embed_single("bitcoin is surging today")
check("Single embed shape", single.shape == (384,), f"got {single.shape}")

batch = embedder.embed_texts(["hello world", "bitcoin crash", "AI revolution"])
check("Batch embed shape", batch.shape == (3, 384), f"got {batch.shape}")

empty = embedder.embed_texts([])
check("Empty batch returns empty", empty.shape == (0,) or len(empty) == 0)

sim_same = embedder.cosine_similarity(single, single)
check("Self-similarity == 1.0", abs(sim_same - 1.0) < 1e-5, f"got {sim_same}")

v1 = embedder.embed_single("bitcoin crypto blockchain")
v2 = embedder.embed_single("football soccer championship")
sim_diff = embedder.cosine_similarity(v1, v2)
check("Unrelated topics low similarity", sim_diff < 0.5, f"got {sim_diff:.4f}")

v3 = embedder.embed_single("ethereum defi token launch")
sim_related = embedder.cosine_similarity(v1, v3)
check("Related topics higher similarity", sim_related > sim_diff, f"crypto-crypto={sim_related:.4f} > crypto-sports={sim_diff:.4f}")

batch_sims = embedder.cosine_similarities_batch(v1, batch)
check("Batch similarity shape", batch_sims.shape == (3,), f"got {batch_sims.shape}")


# ── 3. Virality Scorer (pure math) ────────────────────────────────────
section("VIRALITY SCORER — MATH")

from mindshare_engine.virality_scorer import ViralityScorer

scorer = ViralityScorer()

sig_0 = scorer._sigmoid(0.0, midpoint=0.0, steepness=1.0)
check("Sigmoid(0, mid=0) == 0.5", abs(sig_0 - 0.5) < 1e-6, f"got {sig_0}")

sig_high = scorer._sigmoid(10.0, midpoint=0.0, steepness=1.0)
check("Sigmoid(10) ~ 1.0", sig_high > 0.999, f"got {sig_high}")

sig_low = scorer._sigmoid(-10.0, midpoint=0.0, steepness=1.0)
check("Sigmoid(-10) ~ 0.0", sig_low < 0.001, f"got {sig_low}")

sig_clamp = scorer._sigmoid(1000.0)
check("Sigmoid extreme clamp", 0.0 <= sig_clamp <= 1.0, f"got {sig_clamp}")

components = {
    "velocity": 0.8,
    "acceleration": 0.6,
    "spread": 0.7,
    "engagement": 0.5,
    "influencer": 0.3,
    "freshness": 0.9,
    "emotional": 0.65,
    "remix": 0.45,
    "controversy": 0.35,
    "smart_account": 0.55,  # v4 NEW
    "coordination": 0.40,   # v4 NEW
}
ws = scorer._weighted_score(components)
# v4 weights: velocity=0.08, accel=0.16, spread=0.18, engage=0.11, influencer=0.06, fresh=0.05, emotional=0.08, remix=0.07, controversy=0.06, smart_account=0.10, coordination=0.05
expected = (
    0.8*0.08 + 0.6*0.16 + 0.7*0.18 + 0.5*0.11 + 0.3*0.06 + 0.9*0.05 + 0.65*0.08 + 
    0.45*0.07 + 0.35*0.06 + 0.55*0.10 + 0.40*0.05
)
check("Weighted score calculation (v4)", abs(ws - expected) < 1e-6, f"got {ws:.4f} expected {expected:.4f}")
check("Weighted score in [0,1]", 0.0 <= ws <= 1.0)

now = datetime.now(tz=timezone.utc)
current = {
    "tweet_count": 50, "unique_authors": 15,
    "total_engagement": 200, "total_likes_rts": 120, "total_quotes_replies": 80,
    "total_likes": 80, "total_rts": 40, "total_quotes": 25, "total_replies": 55,
    "narrative_id": "test", "created_at": now,
}
history = [
    {"tweet_count": 10, "unique_authors": 5, "window_time": now - timedelta(minutes=5)},
    {"tweet_count": 15, "unique_authors": 7, "window_time": now - timedelta(minutes=10)},
    {"tweet_count": 12, "unique_authors": 6, "window_time": now - timedelta(minutes=15)},
]

vel = scorer._velocity(current, history)
check("Velocity in [0,1]", 0.0 <= vel <= 1.0, f"got {vel:.4f}")
check("High volume -> high velocity", vel > 0.5, f"got {vel:.4f}")

vel_no_hist = scorer._velocity(current, [])
check("Velocity no history in [0,1]", 0.0 <= vel_no_hist <= 1.0, f"got {vel_no_hist:.4f}")

accel = scorer._acceleration(current, history)
check("Acceleration in [0,1]", 0.0 <= accel <= 1.0, f"got {accel:.4f}")

accel_short = scorer._acceleration(current, [history[0]])
check("Acceleration short history fallback", 0.0 <= accel_short <= 1.0, f"got {accel_short}")

spread = scorer._spread(current, history)
check("Spread in [0,1]", 0.0 <= spread <= 1.0, f"got {spread:.4f}")

eng = scorer._engagement(current, media_ratio=0.3)
check("Engagement in [0,1]", 0.0 <= eng <= 1.0, f"got {eng:.4f}")

fresh = scorer._freshness(current, now, history)
check("Freshness in [0,1]", 0.0 <= fresh <= 1.0, f"got {fresh:.4f}")
check("Just-created narrative is fresh", fresh > 0.5, f"got {fresh:.4f}")

old_narrative = {"created_at": now - timedelta(hours=24)}
fresh_old = scorer._freshness(old_narrative, now, history)
check("Old narrative less fresh", fresh_old < fresh, f"old={fresh_old:.4f} new={fresh:.4f}")


# ── 4. Discord Formatter ──────────────────────────────────────────────
section("DISCORD FORMATTER")

from mindshare_engine.discord_formatter import (
    DiscordFormatter, COLOR_HIGH, COLOR_MODERATE, COLOR_LOW,
    DOMAIN_ICONS, STATE_LABELS, TIER_HIGH, TIER_MODERATE,
)

fmt = DiscordFormatter()

mock_signal = {
    "virality_score": 0.82,
    "primary_domain": "crypto_defi",
    "state": "breaking",
    "label": "Bitcoin ETF Surge",
    "components": components,
    "tweet_count": 450,
    "unique_authors": 120,
    "top_terms": ["bitcoin", "etf", "approval", "sec", "blackrock"],
    "window_time": now.isoformat(),
    "narrative_id": "test-123",
}

payload = fmt.format_signal(mock_signal)
check("Payload has username", "username" in payload)
check("Payload has embeds", "embeds" in payload and len(payload["embeds"]) == 1)
embed = payload["embeds"][0]
check("Embed has title", "title" in embed and "HIGH CONVICTION" in embed["title"])
check("Embed has description", "description" in embed and "Bitcoin ETF Surge" in embed["description"])
check("Embed has color", "color" in embed and embed["color"] == COLOR_HIGH)
check("Embed has fields", len(embed.get("fields", [])) >= 2)
check("Embed has footer", "footer" in embed)
check("Embed has timestamp", "timestamp" in embed)

mod_signal = dict(mock_signal, virality_score=0.58)
mod_payload = fmt.format_signal(mod_signal)
mod_embed = mod_payload["embeds"][0]
check("Moderate tier color", mod_embed["color"] == COLOR_MODERATE)
check("Moderate tier title", "MODERATE" in mod_embed["title"])

summary = fmt.format_batch_summary([mock_signal, mod_signal], now, total_scored=50)
check("Summary has embeds", len(summary.get("embeds", [])) == 1)
check("Summary title", "SCAN COMPLETE" in summary["embeds"][0]["title"])

check("should_post HIGH=True", fmt.should_post(mock_signal) is True)
check("should_post LOW=False", fmt.should_post({"virality_score": 0.20}) is False)

check("All 16 domain icons", len(DOMAIN_ICONS) >= 16)  # v4 may add more
check("All 6+ state labels", len(STATE_LABELS) >= 6)

tier_h, color_h = fmt._tier_info(80)
check("Tier 80 = HIGH CONVICTION", tier_h == "HIGH CONVICTION" and color_h == COLOR_HIGH)
tier_m, color_m = fmt._tier_info(55)
check("Tier 55 = MODERATE", tier_m == "MODERATE" and color_m == COLOR_MODERATE)
tier_l, color_l = fmt._tier_info(30)
check("Tier 30 = LOW", tier_l == "LOW" and color_l == COLOR_LOW)


# ── 5. Cluster Engine (domain assignment) ─────────────────────────────
section("CLUSTER ENGINE — DOMAIN ASSIGNMENT")

from mindshare_engine.cluster_engine import ClusterEngine

cluster = ClusterEngine(embedder)

crypto_emb = embedder.embed_single("bitcoin ethereum defi token crypto trading")
domain_dist = cluster._assign_domain(crypto_emb)
check("Domain dist has 16 keys", len(domain_dist) == 16)
check("Domain dist sums to 1.0", abs(sum(domain_dist.values()) - 1.0) < 1e-4, f"got {sum(domain_dist.values()):.4f}")
top_domain = max(domain_dist, key=domain_dist.get)
check("Crypto text -> crypto_defi domain", top_domain == "crypto_defi", f"got {top_domain}")

politics_emb = embedder.embed_single("president election senate vote congress legislation")
politics_dist = cluster._assign_domain(politics_emb)
top_politics = max(politics_dist, key=politics_dist.get)
check("Politics text -> institutional_politics", top_politics == "institutional_politics", f"got {top_politics}")

sports_emb = embedder.embed_single("NFL touchdown quarterback championship superbowl")
sports_dist = cluster._assign_domain(sports_emb)
top_sports = max(sports_dist, key=sports_dist.get)
check("Sports text -> sports_esports", top_sports == "sports_esports", f"got {top_sports}")

ai_emb = embedder.embed_single("GPT language model machine learning neural network")
ai_dist = cluster._assign_domain(ai_emb)
top_ai = max(ai_dist, key=ai_dist.get)
check("AI text -> tech_innovation", top_ai == "tech_innovation", f"got {top_ai}")


# ── 6. Signal Emitter (formatting, no network) ────────────────────────
section("SIGNAL EMITTER — FORMATTING")

from mindshare_engine.signal_emitter import SignalEmitter

with patch("mindshare_engine.signal_emitter.execute"):
    emitter = SignalEmitter()

generic = emitter._format_generic_signal(mock_signal)
check("Generic signal has tier", generic["tier"] == "HIGH_CONVICTION")
check("Generic signal display_score", generic["display_score"] == 82)
check("Generic signal has components", "velocity" in generic["components"])
check("Generic signal has top_terms", len(generic["top_terms"]) == 5)

moderate_generic = emitter._format_generic_signal(mod_signal)
check("Moderate generic tier", moderate_generic["tier"] == "MODERATE")

low_signal = dict(mock_signal, virality_score=0.30)
low_generic = emitter._format_generic_signal(low_signal)
check("Low generic tier", low_generic["tier"] == "LOW")


# ── 7. Window Runner (time alignment) ─────────────────────────────────
section("WINDOW RUNNER — TIME ALIGNMENT")

from mindshare_engine.window_runner import WindowRunner

t1 = datetime(2026, 2, 20, 14, 37, 42, tzinfo=timezone.utc)
aligned = WindowRunner._aligned_window_time(t1)
check("Aligned to 5-min boundary", aligned.minute == 35 and aligned.second == 0, f"got {aligned}")

t2 = datetime(2026, 2, 20, 14, 0, 0, tzinfo=timezone.utc)
aligned2 = WindowRunner._aligned_window_time(t2)
check("Exact boundary stays", aligned2.minute == 0, f"got {aligned2}")

t3 = datetime(2026, 2, 20, 14, 59, 59, tzinfo=timezone.utc)
aligned3 = WindowRunner._aligned_window_time(t3)
check("End of hour aligns", aligned3.minute == 55, f"got {aligned3}")


# ── 8. Frontier Builder (exploration layer) ───────────────────────────
section("FRONTIER BUILDER — EXPLORATION LAYER")

with patch("mindshare_engine.frontier_builder.execute", return_value=[]):
    frontier = FrontierBuilder = __import__("mindshare_engine.frontier_builder", fromlist=["FrontierBuilder"]).FrontierBuilder
    fb = frontier()

    layer_c = fb._layer_c(budget=12, existing_terms=set())
    check("Layer C produces terms", len(layer_c) > 0, f"got {len(layer_c)}")
    check("Layer C within budget", len(layer_c) <= 12, f"got {len(layer_c)}")
    check("Layer C terms are layer 'C'", all(t["layer"] == "C" for t in layer_c))
    check("Layer C terms have lane", all(t["lane"] in DOMAINS for t in layer_c))
    check("Layer C no duplicates", len(set(t["term"] for t in layer_c)) == len(layer_c))


# ── Results ────────────────────────────────────────────────────────────
section("RESULTS")
total = PASS + FAIL
print(f"\n  {PASS}/{total} passed", end="")
if FAIL:
    print(f" — \033[91m{FAIL} FAILED\033[0m")
else:
    print(f" — \033[92mALL PASSED\033[0m")
print()

sys.exit(1 if FAIL else 0)
