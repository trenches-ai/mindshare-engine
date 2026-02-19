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
