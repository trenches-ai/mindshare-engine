# Clawbot Mindshare Engine

Real-time Twitter/X attention dynamics engine. Detects emerging narratives, tracks domain heat, and estimates breakout probability — all in 5-minute windows.

## Architecture

Built in 4 phases (see docs/):
- **Phase A** ✅ — Core ingestion + clustering (this codebase)
- **Phase B** — Deterministic lifecycle state machine
- **Phase C** — Integrity & coordination detection
- **Phase D** — Hybrid probabilistic refinement (Hawkes + HMM)

## Setup

### 1. Prerequisites
- Python 3.11+
- PostgreSQL 14+
- X Pro API Bearer Token

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Initialise database
```bash
python run.py --init-db
```

### 5. Run
```bash
# Single window (test)
python run.py --run-once

# Continuous (production)
python run.py --continuous
```

## Project Structure

```
mindshare_engine/
├── config.py          # All config + 16 domain seed lexicons
├── database.py        # Postgres schema + connection pool
├── embedder.py        # Sentence-transformer wrapper
├── frontier_builder.py # 3-layer query budget (exploit/balance/explore)
├── twitter_ingest.py  # X Pro ingestion + rate limit handling
├── cluster_engine.py  # Narrative clustering + birth detection + domain assignment
└── window_runner.py   # 5-min pipeline orchestrator
```

## 16 Domains

| Domain | Description |
|--------|-------------|
| institutional_politics | Domestic governance, elections, legislation |
| geopolitical_conflict | Wars, sanctions, military events |
| markets_economy | Macro, stocks, inflation, Fed |
| corporate_brand | Companies, CEOs, layoffs, M&A |
| crypto_defi | BTC, ETH, DeFi, NFTs |
| tech_innovation | AI, product launches, dev tools |
| science_knowledge | Research, discoveries, papers |
| health_biomedical | Disease, vaccines, pharma, FDA |
| environment_climate | Climate, emissions, disasters |
| legal_justice | Trials, courts, arrests, verdicts |
| cultural_identity | Identity, race, gender debates |
| celebrity_prestige | Celebrities, pop culture drama |
| sports_esports | NFL, NBA, football, esports |
| creator_economy | YouTube, TikTok, influencers |
| nature_animals | Animals, wildlife, pets |
| meme_platform | Memes, Twitter meta, shitposting |

## Performance Targets (Phase A)
- < 120s per window
- ≤ 300 API calls per window  
- ≤ 20k tweets per window
- Runs on single moderate VPS
