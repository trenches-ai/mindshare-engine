"""
Test signal using REAL tweets fetched from Twitter API.
This will have working tweet links!
"""
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

from mindshare_engine.discord_formatter import DiscordFormatter
from mindshare_engine.signal_emitter import SignalEmitter
from mindshare_engine.twitter_ingest import TwitterIngest

def main():
    # Check required env vars
    bearer_token = os.getenv("TWITTER_BEARER_TOKEN", "")
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "")
    
    if not bearer_token:
        print("ERROR: TWITTER_BEARER_TOKEN not set in .env")
        sys.exit(1)
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL not set in .env")
        sys.exit(1)

    print("Fetching real tweets from Twitter API...")
    
    # Initialize Twitter client
    ingest = TwitterIngest()
    
    # Search for animal/wildlife tweets
    search_query = "cute animal viral"
    tweets = ingest.search_recent(search_query, max_results=10)
    
    if not tweets:
        print(f"No tweets found for '{search_query}'. Trying another search...")
        tweets = ingest.search_recent("wildlife nature", max_results=10)
    
    if not tweets:
        print("ERROR: Could not fetch any tweets. Check your API access.")
        sys.exit(1)
    
    print(f"Found {len(tweets)} real tweets!")
    
    # Sort by engagement and take top 3
    tweets.sort(key=lambda t: t.get("like_count", 0) + t.get("retweet_count", 0), reverse=True)
    top_3 = tweets[:3]
    
    # Show what we found
    for i, t in enumerate(top_3, 1):
        print(f"\n{i}. @{t.get('author_username', 'unknown')}")
        print(f"   Tweet ID: {t.get('tweet_id')}")
        print(f"   Likes: {t.get('like_count', 0)}, RTs: {t.get('retweet_count', 0)}")
        print(f"   Content: {t.get('content', '')[:80]}...")
    
    now = datetime.now(tz=timezone.utc)
    formatter = DiscordFormatter()
    emitter = SignalEmitter()

    # Build signal with REAL tweet data
    animals_signal = {
        "narrative_id": "real-api-test",
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
        "why": "Real API Test: Fetched live tweets with working links!",
        "media_ratio": 0.85,
        "state": "emerging",
        "label": "Live Animal/Wildlife Tweets - Real API Data",
        "primary_domain": "nature_animals",
        "tweet_count": len(tweets),
        "unique_authors": len(set(t.get("author_id") for t in tweets)),
        "top_terms": ["cute", "animal", "wildlife", "nature", "viral"],
        "top_tweets": [
            {
                "tweet_id": t.get("tweet_id", ""),
                "author_username": t.get("author_username", ""),
                "content": t.get("content", ""),
                "retweet_count": t.get("retweet_count", 0),
                "like_count": t.get("like_count", 0),
                "reply_count": t.get("reply_count", 0),
                "quote_count": t.get("quote_count", 0),
            }
            for t in top_3
        ],
        "first_mover": {
            "tweet_id": top_3[0].get("tweet_id", "") if top_3 else "",
            "username": top_3[0].get("author_username", "") if top_3 else "",
            "follower_count": 0,  # Would need user lookup for this
            "tier": "mid",
            "created_at": now.isoformat(),
        },
        "whos_talking": {
            "tier_breakdown": {"mega": 0, "macro": 1, "mid": 3, "small": 4, "nano": 2},
            "notable_accounts": [],
            "total_accounts": len(set(t.get("author_id") for t in tweets)),
        },
    }

    print("\n" + "="*50)
    print("Sending to Discord with REAL tweet links...")
    payload = formatter.format_signal(animals_signal)
    success = emitter._post_discord(payload)
    
    if success:
        print("\nSUCCESS! Check Discord - the tweet links should work now!")
    else:
        print("\nFAILED: Could not send to Discord")
        sys.exit(1)

if __name__ == "__main__":
    main()
