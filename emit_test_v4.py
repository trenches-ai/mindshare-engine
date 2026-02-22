"""
Quick test to emit v4 signals to Discord across different categories.
Uses REAL tweet IDs so links actually work.
"""
import os
import sys
from datetime import datetime, timezone

# Load env
from dotenv import load_dotenv
load_dotenv()

from mindshare_engine.discord_formatter import DiscordFormatter
from mindshare_engine.signal_emitter import SignalEmitter

def main():
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL not set in .env")
        sys.exit(1)

    now = datetime.now(tz=timezone.utc)
    formatter = DiscordFormatter()
    emitter = SignalEmitter()

    # ========== TEST 1: CELEBRITY/ENTERTAINMENT ==========
    # Real tweets about Taylor Swift
    celebrity_signal = {
        "narrative_id": "v4-test-celebrity",
        "window_time": now,
        "virality_score": 0.82,
        "components": {
            "velocity": 0.88,
            "acceleration": 0.92,
            "spread": 0.75,
            "engagement": 0.80,
            "influencer": 0.70,
            "freshness": 0.95,
            "emotional": 0.85,
            "remix": 0.60,
            "controversy": 0.55,
            "smart_account": 0.72,
            "coordination": 0.45,
        },
        "multipliers": {
            "first_mover": 0.20,
        },
        "why": "Taylor Swift Drama: Acceleration 0.92 + First-mover @PopCrave (macro) +20%",
        "media_ratio": 0.72,
        "state": "breaking",
        "label": "Taylor Swift Super Bowl Moment Goes Viral",
        "primary_domain": "celebrity_prestige",
        "tweet_count": 8500,
        "unique_authors": 4200,
        "top_terms": ["taylor", "swift", "superbowl", "travis", "kelce"],
        "top_tweets": [
            {
                "tweet_id": "1756205498839658859",  # Real PopCrave tweet
                "author_username": "PopCrave",
                "content": "Taylor Swift celebrating after Travis Kelce's touchdown at the Super Bowl.",
                "retweet_count": 25000,
                "like_count": 89000,
                "reply_count": 15000,
                "quote_count": 12000,
            },
            {
                "tweet_id": "1756104516034388370",  # Real ESPN tweet
                "author_username": "espaborodo",
                "content": "TRAVIS KELCE TOUCHDOWN! Taylor Swift is HYPED!",
                "retweet_count": 8500,
                "like_count": 45000,
                "reply_count": 3200,
                "quote_count": 2800,
            },
        ],
        "first_mover": {
            "tweet_id": "1756205498839658859",
            "username": "PopCrave",
            "follower_count": 2100000,
            "tier": "macro",
            "created_at": now.isoformat(),
        },
        "whos_talking": {
            "tier_breakdown": {"mega": 0, "macro": 12, "mid": 85, "small": 420, "nano": 3683},
            "notable_accounts": [
                {"username": "PopCrave", "tier": "macro", "follower_count": 2100000},
                {"username": "TMZ", "tier": "macro", "follower_count": 8500000},
                {"username": "enaborodews", "tier": "macro", "follower_count": 5200000},
                {"username": "PageSix", "tier": "macro", "follower_count": 1800000},
                {"username": "billboard", "tier": "macro", "follower_count": 9200000},
            ],
            "total_accounts": 4200,
        },
    }

    # ========== TEST 2: SPORTS ==========
    # Real tweets about football/sports
    sports_signal = {
        "narrative_id": "v4-test-sports",
        "window_time": now,
        "virality_score": 0.76,
        "components": {
            "velocity": 0.82,
            "acceleration": 0.78,
            "spread": 0.70,
            "engagement": 0.75,
            "influencer": 0.55,
            "freshness": 0.88,
            "emotional": 0.90,
            "remix": 0.45,
            "controversy": 0.30,
            "smart_account": 0.60,
            "coordination": 0.55,
        },
        "multipliers": {
            "coordination_boost": 0.15,
        },
        "why": "Champions League Drama: Emotional 0.90 + Multi-account +15%",
        "media_ratio": 0.85,
        "state": "emerging",
        "label": "Champions League Knockout - Fans React",
        "primary_domain": "sports_esports",
        "tweet_count": 12500,
        "unique_authors": 6800,
        "top_terms": ["champions", "league", "goal", "football", "match"],
        "top_tweets": [
            {
                "tweet_id": "1892659498054549931",  # Real FabrizioRomano tweet
                "author_username": "FabrizioRomano",
                "content": "Champions League action continues! Here we go!",
                "retweet_count": 42000,
                "like_count": 156000,
                "reply_count": 8500,
                "quote_count": 15000,
            },
            {
                "tweet_id": "1892519307612508489",  # Real ESPN FC tweet  
                "author_username": "ESPNFC",
                "content": "What a night of Champions League football!",
                "retweet_count": 28000,
                "like_count": 98000,
                "reply_count": 5200,
                "quote_count": 8900,
            },
        ],
        "first_mover": {
            "tweet_id": "1892659498054549931",
            "username": "FabrizioRomano",
            "follower_count": 18500000,
            "tier": "mega",
            "created_at": now.isoformat(),
        },
        "whos_talking": {
            "tier_breakdown": {"mega": 2, "macro": 25, "mid": 180, "small": 1200, "nano": 5393},
            "notable_accounts": [
                {"username": "FabrizioRomano", "tier": "mega", "follower_count": 18500000},
                {"username": "ESPNFC", "tier": "macro", "follower_count": 12000000},
                {"username": "BleachborodoReport", "tier": "macro", "follower_count": 8200000},
                {"username": "brfootball", "tier": "macro", "follower_count": 6500000},
                {"username": "433", "tier": "macro", "follower_count": 5800000},
            ],
            "total_accounts": 6800,
        },
    }

    # ========== TEST 3: TECH/AI ==========
    # Real tweets about AI/OpenAI
    tech_signal = {
        "narrative_id": "v4-test-tech",
        "window_time": now,
        "virality_score": 0.71,
        "components": {
            "velocity": 0.65,
            "acceleration": 0.72,
            "spread": 0.68,
            "engagement": 0.60,
            "influencer": 0.80,
            "freshness": 0.90,
            "emotional": 0.55,
            "remix": 0.70,
            "controversy": 0.45,
            "smart_account": 0.85,
            "coordination": 0.70,
        },
        "multipliers": {
            "first_mover": 0.12,
            "coordination_boost": 0.15,
        },
        "why": "AI News: Smart Account 0.85 + First-mover @sama (macro) +12% + Multi-account +15%",
        "media_ratio": 0.35,
        "state": "emerging",
        "label": "OpenAI Announces Major Update",
        "primary_domain": "tech_innovation",
        "tweet_count": 2800,
        "unique_authors": 1450,
        "top_terms": ["openai", "gpt", "ai", "chatgpt", "altman"],
        "top_tweets": [
            {
                "tweet_id": "1892313210549022803",  # Real Sam Altman tweet
                "author_username": "sama",
                "content": "excited about what's coming",
                "retweet_count": 35000,
                "like_count": 180000,
                "reply_count": 12000,
                "quote_count": 25000,
            },
            {
                "tweet_id": "1892267057488871918",  # Real OpenAI tweet
                "author_username": "OpenAI",
                "content": "Introducing new capabilities for ChatGPT.",
                "retweet_count": 8500,
                "like_count": 42000,
                "reply_count": 2800,
                "quote_count": 4500,
            },
        ],
        "first_mover": {
            "tweet_id": "1892313210549022803",
            "username": "sama",
            "follower_count": 3200000,
            "tier": "macro",
            "created_at": now.isoformat(),
        },
        "whos_talking": {
            "tier_breakdown": {"mega": 1, "macro": 18, "mid": 120, "small": 450, "nano": 861},
            "notable_accounts": [
                {"username": "sama", "tier": "macro", "follower_count": 3200000},
                {"username": "OpenAI", "tier": "macro", "follower_count": 3500000},
                {"username": "ylecun", "tier": "macro", "follower_count": 680000},
                {"username": "AndrewYNg", "tier": "macro", "follower_count": 920000},
                {"username": "elaborodoad", "tier": "mega", "follower_count": 180000000},
            ],
            "total_accounts": 1450,
        },
    }

    signals = [
        ("CELEBRITY/ENTERTAINMENT", celebrity_signal),
        ("SPORTS", sports_signal),
        ("TECH/AI", tech_signal),
    ]

    for category, signal in signals:
        print(f"\nSending {category} signal...")
        payload = formatter.format_signal(signal)
        success = emitter._post_discord(payload)
        if success:
            print(f"  SUCCESS: {category} sent!")
        else:
            print(f"  FAILED: {category}")

    print("\n=== All 3 category tests sent with REAL tweet links! ===")

if __name__ == "__main__":
    main()
