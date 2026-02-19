"""
run.py - Entry point for the Clawbot Mindshare Engine.

Usage:
    python run.py --init-db          # Initialise database schema
    python run.py --run-once         # Run a single window now
    python run.py --continuous       # Run continuous windowed loop
    python run.py --discord-bot      # Start Discord signal bot
    python run.py --signals          # Show latest virality signals
    python run.py --trend <ID>       # Show score trend for a narrative
"""
import argparse
import os
import sys
from loguru import logger
from mindshare_engine.config import LOG_LEVEL, LOG_FILE

# Configure loguru
logger.remove()
logger.add(sys.stdout, level=LOG_LEVEL, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")

if LOG_FILE:
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        logger.add(LOG_FILE, level="DEBUG", rotation="10 MB", retention="7 days")
    except OSError:
        logger.warning("Could not create log file — logging to stdout only")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clawbot Mindshare Engine")
    parser.add_argument("--init-db", action="store_true", help="Initialise the Postgres schema")
    parser.add_argument("--run-once", action="store_true", help="Run a single window and exit")
    parser.add_argument("--continuous", action="store_true", help="Run continuous window loop")
    parser.add_argument("--signals", action="store_true", help="Show latest virality signals and exit")
    parser.add_argument("--trend", type=str, metavar="NARRATIVE_ID", help="Show score trend for a narrative")
    parser.add_argument("--discord-bot", action="store_true", help="Start the Discord signal bot")
    args = parser.parse_args()

    if not any([args.init_db, args.run_once, args.continuous, args.signals, args.trend, args.discord_bot]):
        parser.print_help()
        sys.exit(0)

    if args.init_db:
        logger.info("Initialising database...")
        from mindshare_engine.database import init_db
        init_db()
        logger.info("Done.")

    if args.run_once:
        logger.info("Running single window...")
        from mindshare_engine.window_runner import WindowRunner
        runner = WindowRunner()
        stats = runner.run_window()
        import json
        print(json.dumps(stats, indent=2, default=str))

    if args.continuous:
        logger.info("Starting continuous mode...")
        from mindshare_engine.window_runner import WindowRunner
        runner = WindowRunner()
        runner.run_continuous()

    if args.signals:
        from mindshare_engine.signal_emitter import SignalEmitter
        import json
        emitter = SignalEmitter()
        signals = emitter.get_latest_signals(limit=20, min_score=0.0)
        if not signals:
            print("No virality signals recorded yet.")
        else:
            for s in signals:
                bar = "[" + "#" * round(s["virality_score"] * 10) + "-" * (10 - round(s["virality_score"] * 10)) + "]"
                print(f"  {s['virality_score']:.3f} {bar}  {s['label'] or '?':30s}  {s['primary_domain']:25s}  tweets={s['tweet_count']}  authors={s['unique_authors']}")
            print(f"\n  {len(signals)} signals total")

    if args.trend:
        from mindshare_engine.signal_emitter import SignalEmitter
        emitter = SignalEmitter()
        trend = emitter.get_narrative_trend(args.trend, windows=24)
        if not trend:
            print(f"No trend data for narrative {args.trend}")
        else:
            print(f"Trend for {args.trend} ({len(trend)} windows):\n")
            for t in reversed(trend):
                bar = "[" + "#" * round(t["virality_score"] * 10) + "-" * (10 - round(t["virality_score"] * 10)) + "]"
                print(f"  {t['window_time']}  {t['virality_score']:.3f} {bar}  tweets={t['tweet_count']}  authors={t['unique_authors']}")

    if args.discord_bot:
        logger.info("Starting Discord signal bot...")
        from mindshare_engine.discord_bot import run_bot
        run_bot()


if __name__ == "__main__":
    main()
