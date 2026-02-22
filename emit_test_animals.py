"""
Test signal for nature_animals category.
Links go to user profiles (always work) since we don't have real tweet IDs.
"""
import os
import sys
from datetime import datetime, timezone

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

    # NATURE/ANIMALS TEST
    # Using real usernames - links will go to their profiles
    animals_signal = {
        "narrative_id": "v4-test-animals",
        "window_time": now,
        "virality_score": 0.74,
        "components": {
            "velocity": 0.70,
            "acceleration": 0.82,
            "spread": 0.78,
            "engagement": 0.88,
            "influencer": 0.45,
            "freshness": 0.95,
            "emotional": 0.92,
            "remix": 0.65,
            "controversy": 0.10,
            "smart_account": 0.55,
            "coordination": 0.40,
        },
        "multipliers": {
            "category_boost": 1.15,
        },
        "why": "Viral Animal Content: Emotional 0.92 + Category +15% (quiet domain boost)",
        "media_ratio": 0.92,
        "state": "emerging",
        "label": "Adorable Animal Video Takes Over Timeline",
        "primary_domain": "nature_animals",
        "tweet_count": 4200,
        "unique_authors": 2800,
        "top_terms": ["cute", "animal", "adorable", "wildlife", "viral"],
        "top_tweets": [
            {
                # Real username - link goes to profile
                "tweet_id": "",  # Empty = will link to profile instead
                "author_username": "NatGeo",
                "content": "Witness the incredible bond between elephants in our latest documentary.",
                "retweet_count": 12000,
                "like_count": 85000,
                "reply_count": 2500,
                "quote_count": 3200,
            },
            {
                "tweet_id": "",
                "author_username": "BBCEarth",
                "content": "Nature never fails to amaze us. Watch this incredible moment.",
                "retweet_count": 8500,
                "like_count": 45000,
                "reply_count": 1800,
                "quote_count": 2100,
            },
            {
                "tweet_id": "",
                "author_username": "WWF",
                "content": "Every animal saved is a victory for conservation.",
                "retweet_count": 5200,
                "like_count": 28000,
                "reply_count": 890,
                "quote_count": 1500,
            },
        ],
        "first_mover": {
            "tweet_id": "",
            "username": "NatGeo",
            "follower_count": 25000000,
            "tier": "mega",
            "created_at": now.isoformat(),
        },
        "whos_talking": {
            "tier_breakdown": {"mega": 1, "macro": 8, "mid": 65, "small": 520, "nano": 2206},
            "notable_accounts": [
                {"username": "NatGeo", "tier": "mega", "follower_count": 25000000},
                {"username": "BBCEarth", "tier": "macro", "follower_count": 2100000},
                {"username": "WWF", "tier": "macro", "follower_count": 3800000},
                {"username": "Discovery", "tier": "macro", "follower_count": 4500000},
                {"username": "AnimalPlanet", "tier": "macro", "follower_count": 2800000},
            ],
            "total_accounts": 2800,
        },
    }

    print("Sending NATURE/ANIMALS signal...")
    print("(Links will go to user profiles - always work!)")
    payload = formatter.format_signal(animals_signal)
    success = emitter._post_discord(payload)
    
    if success:
        print("\nSUCCESS: Nature/Animals test sent to Discord!")
        print("Click @NatGeo, @BBCEarth, @WWF links - they go to real profiles!")
    else:
        print("FAILED: Could not send to Discord")
        sys.exit(1)

if __name__ == "__main__":
    main()
