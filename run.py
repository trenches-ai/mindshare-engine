"""
run.py - Entry point for the Clawbot Mindshare Engine.

Usage:
    python run.py --init-db          # Initialise database schema
    python run.py --run-once         # Run a single window now
    python run.py --continuous       # Run continuous windowed loop
"""
import argparse
import sys
from loguru import logger
from mindshare_engine.config import LOG_LEVEL, LOG_FILE

# Configure loguru
logger.remove()
logger.add(sys.stdout, level=LOG_LEVEL, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | {message}")
logger.add(LOG_FILE, level="DEBUG", rotation="10 MB", retention="7 days")


def main() -> None:
    parser = argparse.ArgumentParser(description="Clawbot Mindshare Engine")
    parser.add_argument("--init-db", action="store_true", help="Initialise the Postgres schema")
    parser.add_argument("--run-once", action="store_true", help="Run a single window and exit")
    parser.add_argument("--continuous", action="store_true", help="Run continuous window loop")
    args = parser.parse_args()

    if not any([args.init_db, args.run_once, args.continuous]):
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
        print(json.dumps(stats, indent=2))

    if args.continuous:
        logger.info("Starting continuous mode...")
        from mindshare_engine.window_runner import WindowRunner
        runner = WindowRunner()
        runner.run_continuous()


if __name__ == "__main__":
    main()
