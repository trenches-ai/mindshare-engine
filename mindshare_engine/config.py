"""
config.py - Configuration for the Clawbot Mindshare Engine
Loads from environment variables and defines domain seed lexicons.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- API & DB ---
TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindshare")
WINDOW_MINUTES = int(os.getenv("WINDOW_MINUTES", "5"))
MAX_QUERIES_PER_WINDOW = int(os.getenv("MAX_QUERIES_PER_WINDOW", "300"))
MIN_AUTHORS_FOR_BIRTH = int(os.getenv("MIN_AUTHORS_FOR_BIRTH", "3"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = os.getenv("LOG_FILE", "logs/mindshare.log")

# --- Embedding ---
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
CLUSTER_SIMILARITY_THRESHOLD = float(os.getenv("CLUSTER_SIMILARITY_THRESHOLD", "0.75"))
BIRTH_DENSITY_THRESHOLD = float(os.getenv("BIRTH_DENSITY_THRESHOLD", "0.6"))

# --- Query budget split ---
BUDGET_EXPLOITATION = 0.50  # High-velocity frontier terms
BUDGET_LANE_BALANCE = 0.30  # Per-lane coverage balancing
BUDGET_EXPLORATION = 0.20   # Random/novel term discovery
MAX_TERMS_PER_WINDOW = 60

# --- 16 Structural Domains ---
DOMAINS = [
    "institutional_politics",
    "geopolitical_conflict",
    "markets_economy",
    "corporate_brand",
    "crypto_defi",
    "tech_innovation",
    "science_knowledge",
    "health_biomedical",
    "environment_climate",
    "legal_justice",
    "cultural_identity",
    "celebrity_prestige",
    "sports_esports",
    "creator_economy",
    "nature_animals",
    "meme_platform",
]

# Seed lexicon per domain — used for initial query frontier and domain assignment
DOMAIN_SEED_LEXICONS: dict[str, list[str]] = {
    "institutional_politics": [
        "congress", "senate", "president", "election", "policy",
        "government", "democrat", "republican", "vote", "legislation",
    ],
    "geopolitical_conflict": [
        "war", "military", "invasion", "nato", "sanctions",
        "missile", "troops", "ceasefire", "geopolitics", "conflict",
    ],
    "markets_economy": [
        "stock market", "inflation", "fed rate", "recession", "gdp",
        "earnings", "interest rates", "s&p 500", "unemployment", "hedge fund",
    ],
    "corporate_brand": [
        "apple", "tesla", "amazon", "layoffs", "ceo",
        "merger", "acquisition", "quarterly results", "brand", "startup",
    ],
    "crypto_defi": [
        "bitcoin", "ethereum", "crypto", "defi", "nft",
        "altcoin", "blockchain", "token launch", "solana", "web3",
    ],
    "tech_innovation": [
        "ai", "chatgpt", "openai", "llm", "machine learning",
        "product launch", "api", "developer", "model release", "automation",
    ],
    "science_knowledge": [
        "research", "study", "peer review", "discovery", "physics",
        "biology", "astronomy", "chemistry", "paper published", "science",
    ],
    "health_biomedical": [
        "vaccine", "pandemic", "disease", "fda", "clinical trial",
        "virus", "outbreak", "cancer", "mental health", "healthcare",
    ],
    "environment_climate": [
        "climate change", "emissions", "wildfire", "flood", "carbon",
        "renewable energy", "drought", "deforestation", "esg", "sustainability",
    ],
    "legal_justice": [
        "trial", "verdict", "lawsuit", "court", "judge",
        "arrested", "indicted", "supreme court", "crime", "sentencing",
    ],
    "cultural_identity": [
        "racism", "gender", "lgbtq", "diversity", "cancel culture",
        "identity", "feminism", "woke", "immigration", "social justice",
    ],
    "celebrity_prestige": [
        "taylor swift", "beyonce", "kanye", "kardashian", "celebrity",
        "actor", "singer", "drama", "breakup", "paparazzi",
    ],
    "sports_esports": [
        "nfl", "nba", "champions league", "world cup", "transfer",
        "game 7", "championship", "esports", "tournament", "player signed",
    ],
    "creator_economy": [
        "youtube", "tiktok", "influencer", "streaming", "twitch",
        "viral video", "content creator", "subscriber", "monetization", "collab",
    ],
    "nature_animals": [
        "cat", "dog", "wildlife", "animal rescue", "cute",
        "nature", "elephant", "dolphin", "bird", "endangered species",
    ],
    "meme_platform": [
        "meme", "ratio", "based", "copium", "twitter drama",
        "main character", "npc", "shitpost", "lore", "ironic",
    ],
}

# Lifecycle states
LIFECYCLE_STATES = [
    "incubating",
    "emerging",
    "breaking",
    "dominant",
    "declining",
    "dormant",
]

# --- Virality scoring v2 ---
VIRALITY_WINDOW_LOOKBACK = int(os.getenv("VIRALITY_WINDOW_LOOKBACK", "6"))
VIRALITY_SIGNAL_THRESHOLD = float(os.getenv("VIRALITY_SIGNAL_THRESHOLD", "0.55"))
VIRALITY_ALERT_THRESHOLD = float(os.getenv("VIRALITY_ALERT_THRESHOLD", "0.75"))

# v4 weight presets — 11 signals (must sum to 1.0)
VIRALITY_WEIGHTS = {
    "velocity":      0.08,   # reduced — less predictive than spread
    "acceleration":  0.16,   # kept high — catches trends before peak
    "spread":        0.18,   # boosted — most predictive signal
    "engagement":    0.11,   # reduced — remix now separate
    "influencer":    0.06,   # reduced — smart_account covers this better
    "freshness":     0.05,   # kept same
    "emotional":     0.08,   # slightly reduced
    "remix":         0.07,   # quote tweet participation
    "controversy":   0.06,   # reply-to-like ratio
    "smart_account": 0.10,   # NEW v4 — weighted account tier participation
    "coordination":  0.05,   # NEW v4 — cross-account correlation
}

# v2 sigmoid midpoints
VELOCITY_SURGE_MIDPOINT = 2.5       # ratio vs 30-min baseline
VELOCITY_COLD_MIDPOINT = 50         # tweet count when no history
ACCEL_COLD_MIDPOINT = 30            # tweet count proxy when no history
SPREAD_NEW_AUTHOR_MIDPOINT = 0.55   # 55% new authors = midpoint
SPREAD_COLD_MIDPOINT = 30           # unique authors when no history
ENGAGEMENT_MIDPOINT = 6.0           # engagements per tweet
INFLUENCER_MIDPOINT = 0.06          # 6% high-follower ratio
FRESHNESS_MIDPOINT_MINUTES = 45     # minutes old = midpoint
EMOTIONAL_MIDPOINT = 0.65           # normalised arousal+valence score
REMIX_MIDPOINT = 0.15               # 15% quote ratio = midpoint (quotes / total engagement)
CONTROVERSY_MIDPOINT = 0.25         # replies / likes ratio — 0.25 = midpoint

# v2 post-scoring multipliers
VISUAL_VIRALITY_THRESHOLD = 0.50    # min fraction of media posts to apply boost
VISUAL_VIRALITY_MULTIPLIER = 1.12   # score multiplier when visual threshold met
CATEGORY_QUIET_BOOST = 0.15         # relative velocity/spread boost for quiet domains
QUIET_DOMAINS = [
    "nature_animals", "science_knowledge", "environment_climate",
    "creator_economy", "cultural_identity",
]

# v2 dynamic reweighting
SATURATION_THRESHOLD = 0.95         # when velocity+spread both above this
SATURATION_REDISTRIBUTE = 0.14      # total weight shifted away from saturated signals

# v2 guardrails
NARRATIVE_AGE_CAP_HOURS = 48        # demote narratives older than this
NARRATIVE_AGE_DEMOTION = 0.20       # score reduction for stale narratives
MIN_VISUAL_RATIO_TO_EMIT = 0.0     # min media ratio to emit (0 = disabled, 0.4 = strict)
FRESHNESS_SUSTAINED_HOURS = 4       # if still accelerating after this, halve decay

# v2 engagement sub-weights (within engagement component)
ENGAGEMENT_WEIGHT_LIKES_RTS = 0.40
ENGAGEMENT_WEIGHT_QUOTES_REPLIES = 0.40
ENGAGEMENT_WEIGHT_MEDIA_BOOST = 0.20

# v2.1 remixability sub-score (inside engagement)
REMIX_THRESHOLD = 0.30          # min quote-ratio to trigger boost
REMIX_BOOST = 0.10              # additive boost to engagement sigmoid input

# --- Bot / Webhook ---
BOT_WEBHOOK_URL = os.getenv("BOT_WEBHOOK_URL", "")
BOT_WEBHOOK_SECRET = os.getenv("BOT_WEBHOOK_SECRET", "")
BOT_COOLDOWN_MINUTES = int(os.getenv("BOT_COOLDOWN_MINUTES", "15"))
BOT_MAX_SIGNALS_PER_WINDOW = int(os.getenv("BOT_MAX_SIGNALS_PER_WINDOW", "8"))

# --- Discord webhook alerts ---
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
DISCORD_BOT_NAME = os.getenv("DISCORD_BOT_NAME", "Mindshare Engine")
DISCORD_BOT_AVATAR_URL = os.getenv("DISCORD_BOT_AVATAR_URL", "")
DISCORD_ALERT_HIGH_CONVICTION = os.getenv("DISCORD_ALERT_HIGH_CONVICTION", "true").lower() == "true"
DISCORD_ALERT_MODERATE = os.getenv("DISCORD_ALERT_MODERATE", "false").lower() == "true"
DISCORD_POST_SUMMARY = os.getenv("DISCORD_POST_SUMMARY", "true").lower() == "true"

# --- Discord Bot (standalone poller) ---
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID", "0") or "0")
DISCORD_POLL_INTERVAL = int(os.getenv("DISCORD_POLL_INTERVAL", "30"))

# --- Account Tier Tracking (v4) ---
# Follower thresholds for account tier classification
ACCOUNT_TIER_THRESHOLDS = {
    "mega":   1_000_000,   # 1M+ followers - massive reach
    "macro":  100_000,     # 100K+ - established influencer
    "mid":    10_000,      # 10K+ - micro-influencer
    "small":  1_000,       # 1K+ - engaged user
    # below 1K = "nano" (default)
}

# Weight multipliers for account tiers when calculating "smart account" signal
ACCOUNT_TIER_WEIGHTS = {
    "mega":   5.0,    # mega accounts count 5x
    "macro":  3.0,    # macro accounts count 3x
    "mid":    1.5,    # mid accounts count 1.5x
    "small":  1.0,    # small accounts count 1x
    "nano":   0.5,    # nano accounts count 0.5x
}

# "Smart account" virality signal config
SMART_ACCOUNT_MIDPOINT = 3.0      # weighted account score where sigmoid = 0.5
SMART_ACCOUNT_STEEPNESS = 1.5     # steepness of sigmoid curve

# Cross-account correlation detection
CROSS_ACCOUNT_WINDOW_MINUTES = 10   # time window to detect coordinated posting
CROSS_ACCOUNT_MIN_TIERS = 2         # min distinct high-tier accounts for correlation
CROSS_ACCOUNT_BOOST = 0.15          # virality score boost when correlation detected

# First-mover tracking
FIRST_MOVER_WINDOW_MINUTES = 30     # how far back to look for first tweet
FIRST_MOVER_TIER_BOOST = {          # boost if first-mover is high-tier
    "mega":   0.20,
    "macro":  0.12,
    "mid":    0.05,
    "small":  0.0,
    "nano":   0.0,
}