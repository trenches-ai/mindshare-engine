# Clawbot Mindshare Engine

Real-time Twitter/X attention dynamics engine. Detects emerging narratives, tracks domain heat, and estimates breakout probability — all in 5-minute windows.

## Architecture

Built in 4 phases (see docs/):
- **Phase A** ✅ — Core ingestion + clustering
- **Phase A.5** ✅ — Virality scoring + bot signal pipeline
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
├── config.py            # All config + 16 domain seed lexicons
├── database.py          # Postgres schema + connection pool
├── embedder.py          # Sentence-transformer wrapper
├── frontier_builder.py  # 3-layer query budget (exploit/balance/explore)
├── twitter_ingest.py    # X Pro ingestion + rate limit handling
├── cluster_engine.py    # Narrative clustering + birth detection + domain assignment
├── virality_scorer.py   # Composite virality index (6-dimensional scoring)
├── signal_emitter.py    # Bot signal pipeline (webhook delivery + cooldown)
├── discord_bot.py       # Discord bot with rich embed signal posting
└── window_runner.py     # 5-min pipeline orchestrator
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

## Virality Index

Each narrative is scored on six dimensions every window:

| Component | Weight | What it measures |
|-----------|--------|-----------------|
| Velocity | 25% | Tweet volume vs rolling baseline |
| Acceleration | 20% | Rate of velocity change (is growth speeding up?) |
| Spread | 20% | Unique author growth rate |
| Engagement | 15% | Amplification ratio (retweets + quotes + likes per tweet) |
| Influencer | 10% | High-follower accounts participating |
| Freshness | 10% | Recency bonus (newer narratives score higher) |

Scores are normalised to **[0, 1]** via sigmoid functions. Narratives above the signal threshold (default 0.55) are emitted to the bot webhook. Scores above the alert threshold (0.75) are tagged as **ALERT** tier.

### Bot Signal Flow

```
Window Pipeline → Virality Scorer → Signal Emitter → virality_signals (DB)
                                                            ↓
                                         ┌──────────────────┼──────────────┐
                                         ↓                  ↓              ↓
                                   Discord Bot        Webhook POST    CLI / polling
                                   (rich embeds)      (any consumer)  (--signals)
```

Signals are stored in Postgres and consumed by any combination of:
- **Discord bot** — polls DB, posts colour-coded embeds with score bars, component breakdowns, and trend sparklines
- **Webhook** — structured JSON POST to any endpoint (Telegram, custom)
- **CLI** — `--signals` and `--trend` commands

### Discord Bot

The built-in Discord bot posts rich embeds with:
- Colour-coded tiers (🔴 Alert, 🟠 High, 🟡 Signal, 🔵 Watch)
- Domain emoji icons for quick scanning
- Component breakdown bars (velocity, acceleration, spread, engagement, influencer, freshness)
- Trend sparklines across recent windows
- Top terms extracted from tweets
- Discord timestamps for relative time display

```bash
# Start the Discord bot (runs continuously)
python run.py --discord-bot
```

Set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in your `.env` file.

### CLI

```bash
# View latest virality signals
python run.py --signals

# View score trend for a specific narrative
python run.py --trend <narrative_id>
```

## Performance Targets (Phase A)
- < 120s per window
- ≤ 300 API calls per window  
- ≤ 20k tweets per window
- Runs on single moderate VPS
