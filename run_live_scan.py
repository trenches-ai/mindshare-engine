"""
Run a single LIVE scan using the Twitter API and emit results to Discord.
This will use your actual API credits.
"""
import os
import sys

# Load env first
from dotenv import load_dotenv
load_dotenv()

# Check required env vars
if not os.getenv("TWITTER_BEARER_TOKEN"):
    print("ERROR: TWITTER_BEARER_TOKEN not set in .env")
    sys.exit(1)
if not os.getenv("DISCORD_WEBHOOK_URL"):
    print("ERROR: DISCORD_WEBHOOK_URL not set in .env")
    sys.exit(1)
if not os.getenv("DATABASE_URL"):
    print("ERROR: DATABASE_URL not set in .env")
    sys.exit(1)

print("=" * 60)
print("  LIVE SCAN - Using Twitter API (will use credits)")
print("=" * 60)
print(f"  Config: 30 terms x 25 tweets (optimized)")
print(f"  Estimated cost: ~$7-8 per scan")
print("=" * 60)

# Import after env loaded
from mindshare_engine.window_runner import WindowRunner

def main():
    print("\nInitializing Mindshare Engine...")
    runner = WindowRunner()
    
    print("\nRunning single window scan...")
    stats = runner.run_window()
    
    print("\n" + "=" * 60)
    print("  SCAN RESULTS")
    print("=" * 60)
    
    if "error" in stats:
        print(f"  ERROR: {stats['error']}")
        sys.exit(1)
    
    print(f"  Window time: {stats.get('window_time', 'N/A')}")
    print(f"  Duration: {stats.get('duration_seconds', 'N/A')}s")
    
    ingest = stats.get("ingest", {})
    print(f"\n  INGEST:")
    print(f"    Queries run: {ingest.get('queries_run', 0)}")
    print(f"    Tweets fetched: {ingest.get('tweets_fetched', 0)}")
    print(f"    Unique authors: {ingest.get('unique_authors', 0)}")
    
    cluster = stats.get("cluster", {})
    print(f"\n  CLUSTERING:")
    print(f"    Tweets processed: {cluster.get('tweets_processed', 0)}")
    print(f"    Narratives updated: {stats.get('narratives_updated', 0)}")
    
    virality = stats.get("virality", {})
    print(f"\n  VIRALITY:")
    print(f"    Signals scored: {virality.get('scored', 0)}")
    print(f"    Top score: {virality.get('top_score', 0):.2f}")
    print(f"    Top label: {virality.get('top_label', 'N/A')}")
    
    signals = stats.get("signals", {})
    print(f"\n  EMISSIONS:")
    print(f"    Discord sent: {signals.get('discord_posted', 0)}")
    print(f"    Summary sent: {signals.get('summary_posted', False)}")
    
    print("\n" + "=" * 60)
    print("  LIVE SCAN COMPLETE - Check Discord!")
    print("=" * 60)

if __name__ == "__main__":
    main()
