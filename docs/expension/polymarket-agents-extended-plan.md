# Polymarket/agents Extended — Architecture & Feature Plan

## v2 — Updated: Bedrock-First + Dashboard + Python/TypeScript Split

## Decision: Fork & Extend, Don't Rewrite

We fork `Polymarket/agents` and build on its strengths (ChromaDB RAG, superforecaster prompting, LangChain orchestration, py-clob-client integration) while adding everything it lacks (risk management, multi-LLM routing, open-source model support, data pipeline, monitoring, dashboard, training).

**Language split:** Python for the trading bot (entire ecosystem is Python-native — py-clob-client, LiteLLM, LangChain, ChromaDB, training libs). TypeScript/Next.js for the dashboard (aligns with TradeAgentAI SaaS stack, deploys to Vercel, becomes multi-user later).

---

## Recommended Architecture Stack

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                    AWS EC2 c6a.xlarge — eu-west-1 (Ireland)                       │
│                    Elastic IP: deterministic Irish IP                             │
│                    Ubuntu 24.04 + Python 3.11 + Docker                           │
│                    4 vCPU / 8GB RAM / 100GB EBS — ~$45/mo spot                   │
│                    IAM Role: BedrockFullAccess (no API keys needed)               │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────┐  │
│  │                    POLYMARKET/AGENTS (FORKED BASE)                          │  │
│  │  • GammaMarketClient — market discovery                                    │  │
│  │  • Polymarket class — CLOB trading via py-clob-client                      │  │
│  │  • ChromaDB — RAG knowledge base                                           │  │
│  │  • Agent class — superforecaster prompting                                 │  │
│  │  • LangGraph — multi-step pipeline orchestration                           │  │
│  │  • FastAPI server — REST API for bot + dashboard                           │  │
│  └────────────────────┬───────────────────────────────────────────────────────┘  │
│                        │ We extend with ↓                                        │
│  ┌─────────────────────┴──────────────────────────────────────────────────────┐  │
│  │                                                                             │  │
│  │  ┌──────────────────┐  ┌──────────────┐  ┌────────────┐  ┌────────────┐   │  │
│  │  │     LiteLLM      │  │  7 Data      │  │  Risk &    │  │ Monitoring │   │  │
│  │  │     Gateway      │  │  Collectors  │  │  Sizing    │  │ & Feedback │   │  │
│  │  │                  │  │              │  │            │  │            │   │  │
│  │  │  ┌─ PRIMARY ──┐  │  │  GDELT       │  │  Kelly     │  │  Telegram  │   │  │
│  │  │  │ Bedrock    │  │  │  FRED        │  │  Filters   │  │  P&L API   │   │  │
│  │  │  │  Claude ···│  │  │  Reddit      │  │  Paper     │  │  Calibra-  │   │  │
│  │  │  │  Llama ····│  │  │  538 Poll    │  │  Trade     │  │  tion      │   │  │
│  │  │  │  Mistral ··│  │  │  Dune        │  │  Circuit   │  │  Training  │   │  │
│  │  │  └────────────┘  │  │  Tavily      │  │  Breaker   │  │  Logger    │   │  │
│  │  │  ┌─ FALLBACK ─┐  │  │  WebSocket   │  │            │  │            │   │  │
│  │  │  │ OpenAI     │  │  │              │  │            │  │            │   │  │
│  │  │  │ DeepSeek   │  │  │              │  │            │  │            │   │  │
│  │  │  │ Groq       │  │  │              │  │            │  │            │   │  │
│  │  │  └────────────┘  │  │              │  │            │  │            │   │  │
│  │  │  ┌─ LOCAL ─────┐ │  │              │  │            │  │            │   │  │
│  │  │  │ Ollama      │ │  │              │  │            │  │            │   │  │
│  │  │  └─────────────┘ │  │              │  │            │  │            │   │  │
│  │  └──────────────────┘  └──────────────┘  └────────────┘  └────────────┘   │  │
│  │                                                                             │  │
│  │  ┌───────────────────────────────────────────────────────────────────────┐  │  │
│  │  │  LOCAL SERVICES (Docker Compose on same EC2)                          │  │  │
│  │  │  • Ollama — run Qwen3-8B, Mistral-7B, FinGPT locally                 │  │  │
│  │  │  • ChromaDB — persistent vector store                                 │  │  │
│  │  │  • PostgreSQL 16 — trade state, signals, positions (shared with dash) │  │  │
│  │  │  • Redis — caching, rate limiting, pub/sub for signals                │  │  │
│  │  └───────────────────────────────────────────────────────────────────────┘  │  │
│  └─────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                  │
│  ┌───────────────────────────┐  ┌───────────────────────────────────────────┐    │
│  │  S3 (eu-west-1)           │  │  Future: GPU Instance (spot)              │    │
│  │  • Training data (JSONL)  │  │  • g4dn.xlarge ($0.16/hr spot)            │    │
│  │  • Daily snapshots        │  │  • QLoRA fine-tuning on Qwen/Llama        │    │
│  │  • Backtest archives      │  │  • Spin up → train → push weights → down  │    │
│  └───────────────────────────┘  └───────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ HTTPS (FastAPI REST API)
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  VERCEL (global edge) — Next.js Dashboard (TypeScript)                           │
│                                                                                  │
│  • Portfolio overview (positions, P&L, unrealized gains, exposure %)              │
│  • Trade history with AI reasoning for each trade decision                       │
│  • Signal log (every signal: p_model, p_market, edge, pass/reject + why)         │
│  • Calibration curves (Brier score visualization over time)                      │
│  • Market scanner (what the bot is currently watching)                            │
│  • LLM cost/usage dashboard (per-model tokens, cost, latency from LiteLLM)       │
│  • Config panel (thresholds, risk limits, model selection, toggle paper mode)     │
│  • Real-time updates via SSE from FastAPI                                        │
│                                                                                  │
│  Auth: Supabase Auth (just you for now, multi-user SaaS later)                   │
│  Hosting: Vercel free tier · Stack: Next.js 15 + TypeScript + Tailwind + shadcn  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Why This Stack

### Infrastructure: AWS EC2 c6a.xlarge (eu-west-1, Ireland)

We chose this over Cloudflare/Vercel/GCP/Fargate for these reasons:

**Geo-compliance:** Deterministic Irish IP via Elastic IP. Polymarket blocks 33 countries including the US — every outbound request must exit from an EU IP.

**Why EC2 over Fargate:** Fargate is 3.2x more expensive for always-on workloads ($144/mo vs $45/mo for identical compute). Ollama needs persistent model files in RAM — Fargate has no persistent local storage, so every task restart means re-downloading and re-loading 5GB+ of model weights. WebSocket connections need stable long-lived processes, not recyclable containers.

**Why c6a.xlarge:** Running Ollama for local open-source models alongside the bot. 4 vCPU / 8GB RAM handles Qwen3-8B inference at ~15 tokens/sec while the trading pipeline runs concurrently. Spot pricing: ~$45/month (vs $150 on-demand).

### LLM Gateway: LiteLLM with Bedrock as Primary Provider

LiteLLM provides a **unified OpenAI-compatible API** that routes to any provider. We configure **AWS Bedrock as the primary** because:

- **Same region, same VPC** — LLM calls stay inside AWS internal network. ~5-15ms network overhead vs ~100-200ms hitting external APIs. Matters at 300+ LLM calls/day.
- **Single AWS bill** — consolidate compute + inference under one account. One invoice, one set of spend alerts, one Cost Explorer dashboard.
- **Data stays in EU** — all inference data remains within eu-west-1. Not just Polymarket requests, but LLM inference data never leaves Ireland.
- **IAM auth, no API keys** — LiteLLM picks up the EC2 instance's IAM role automatically. Just attach `BedrockFullAccess` policy. One fewer secret to manage.
- **Model coverage** — Bedrock offers Claude Haiku 3.5, Claude Sonnet 4, Llama 3.3 70B, Mistral Large. Covers analysis, decision, and debate tiers.

**Fallback chain:** Bedrock (primary, same-region) → OpenAI (external fallback for GPT-4o) → DeepSeek (cheap overflow at $0.28/M) → Groq (free tier for burst) → Ollama (local, always available).

**Note:** Model access requires opt-in in the Bedrock console — takes minutes for most models, up to a day for some. Do this early in Phase 1.

### Open-Source Models: Ollama (local)

**Local via Ollama on EC2:**
- Qwen3-8B (4-bit quantized, ~5GB, fits in CPU RAM) — screening/filtering
- Mistral-7B-Instruct — general analysis fallback
- FinGPT-Llama (when fine-tuned) — financial sentiment

Ollama models appear as just another LiteLLM provider. Used for free screening at unlimited volume and model diversity in debate agents.

### Database: PostgreSQL 16 (replaces SQLite)

PostgreSQL gives us proper ACID transactions, concurrent access from multiple pipeline stages, JSON columns for flexible schema evolution, and easy migration to managed Supabase/RDS later if needed. Running in Docker on the same EC2 instance — zero network latency. **Shared between bot (writes) and dashboard API (reads).**

### Vector Store: ChromaDB (keep from base repo)

Already in Polymarket/agents. We extend it with richer document types (GDELT articles, Reddit threads, economic indicators, polling data) and use it for both RAG-enriched prompts and competence-based market filtering.

### Dashboard: Next.js on Vercel

TypeScript/Next.js dashboard deployed to Vercel's free tier. Reads from PostgreSQL via FastAPI REST endpoints on the EC2 instance. When we build the SaaS version of TradeAgentAI, this dashboard becomes the multi-user template — just add Supabase RLS and per-user bot instances.

---

## Monthly Cost Breakdown

| Component | Service | Cost |
|-----------|---------|------|
| EC2 c6a.xlarge spot (Ireland) | AWS | ~$45 |
| Elastic IP | AWS | Free (attached) |
| EBS 100GB gp3 | AWS | ~$8 |
| S3 training data (50GB) | AWS | ~$1 |
| Bedrock Claude Haiku 3.5 (~300/day) | AWS Bedrock | $3-8 |
| Bedrock Claude Sonnet 4 (~50/day) | AWS Bedrock | $5-15 |
| Bedrock Llama 3.3 70B (debate agent) | AWS Bedrock | $1-3 |
| OpenAI GPT-4o (fallback only) | OpenAI | $0-5 |
| DeepSeek V3 (cheap overflow) | DeepSeek | $0-3 |
| Groq free tier (burst) | Groq | $0 |
| Ollama local models | Local | $0 |
| GDELT + FRED + 538 + Reddit | Free APIs | $0 |
| Tavily web search | Tavily | $0 (free tier) |
| Telegram alerts | Telegram | $0 |
| Vercel (dashboard hosting) | Vercel | $0 (free tier) |
| **TOTAL** | | **$65-90/mo** |

Well under $200/month budget. ~$110 buffer for paid data sources or GPU training runs.

---

## Extended Project Structure

```
polymarket-agents-extended/
│
├── bot/                                 # ← PYTHON (trading engine)
│   ├── agents/                          #    FORKED FROM Polymarket/agents
│   │   ├── ai/
│   │   │   ├── agent.py                 # MODIFIED: swap OpenAI → LiteLLM
│   │   │   ├── superforecaster.py       # EXTRACTED: Tetlock prompting logic
│   │   │   └── debate.py                # NEW: multi-agent bull/bear debate
│   │   ├── application/
│   │   │   ├── trade.py                 # MODIFIED: full pipeline with risk checks
│   │   │   └── autonomous.py            # NEW: 24/7 autonomous loop
│   │   ├── connectors/
│   │   │   ├── search.py                # KEEP: Tavily web search
│   │   │   └── news.py                  # KEEP: NewsAPI connector
│   │   ├── polymarket/
│   │   │   ├── chroma.py                # KEEP: ChromaDB RAG
│   │   │   ├── gamma.py                 # KEEP: GammaMarketClient
│   │   │   └── polymarket.py            # KEEP: CLOB trading
│   │   └── utils/
│   │       └── objects.py               # KEEP: Pydantic models
│   │
│   ├── extensions/                      #    ALL NEW CAPABILITIES
│   │   ├── llm/
│   │   │   ├── router.py                # LiteLLM config + Bedrock-first routing
│   │   │   ├── providers.py             # Provider registry + fallover chains
│   │   │   └── cost_tracker.py          # Per-model cost + token tracking
│   │   ├── collectors/
│   │   │   ├── gdelt_news.py            # GDELT global news (15-min updates)
│   │   │   ├── fred_economic.py         # FRED economic series (daily)
│   │   │   ├── reddit_sentiment.py      # Reddit/PRAW sentiment (hourly)
│   │   │   ├── polling.py               # FiveThirtyEight polling (daily)
│   │   │   ├── dune_onchain.py          # Dune whale tracking (4-hourly)
│   │   │   ├── polymarket_ws.py         # WebSocket price stream (real-time)
│   │   │   └── resolution_monitor.py    # Resolution source change detection
│   │   ├── enrichment/
│   │   │   ├── context_builder.py       # Assemble market analysis context
│   │   │   ├── deduplicator.py          # TF-IDF news deduplication
│   │   │   └── sentiment_scorer.py      # VADER + GDELT tone aggregation
│   │   ├── analysis/
│   │   │   ├── debate_engine.py         # Bull vs Bear vs Aggregator pipeline
│   │   │   ├── calibration_prompt.py    # Superforecaster calibration layer
│   │   │   └── escalation.py            # Haiku → Sonnet escalation logic
│   │   ├── filtering/
│   │   │   ├── edge_detector.py         # |p_model - p_market| threshold
│   │   │   ├── liquidity_filter.py      # Min orderbook depth check
│   │   │   ├── time_filter.py           # Resolution window check
│   │   │   ├── correlation_guard.py     # Portfolio correlation limits
│   │   │   └── confidence_gate.py       # Min confidence + agent agreement
│   │   ├── validation/
│   │   │   ├── kelly.py                 # Fractional Kelly position sizing
│   │   │   ├── risk_engine.py           # Portfolio-level risk constraints
│   │   │   ├── paper_trade.py           # Paper trading gate for new strategies
│   │   │   └── backtest.py              # Historical validation engine
│   │   ├── execution/
│   │   │   ├── smart_router.py          # Slippage-aware order placement
│   │   │   ├── fill_monitor.py          # WebSocket fill tracking
│   │   │   └── exit_manager.py          # TP/SL/time-based exit logic
│   │   ├── monitoring/
│   │   │   ├── telegram.py              # Trade alerts + daily summaries
│   │   │   ├── position_tracker.py      # Live portfolio state
│   │   │   ├── calibration.py           # Brier score + calibration curves
│   │   │   └── training_logger.py       # S3 prediction→outcome logging
│   │   └── training/                    # Phase 7
│   │       ├── data_builder.py          # Build fine-tuning datasets from S3
│   │       ├── qlora_trainer.py         # QLoRA fine-tuning script
│   │       └── eval_harness.py          # Evaluate fine-tuned vs base models
│   │
│   ├── api/                             #    FastAPI REST API (serves dashboard)
│   │   ├── server.py                    # Main FastAPI app
│   │   ├── routes/
│   │   │   ├── portfolio.py             # GET /portfolio — positions, P&L, exposure
│   │   │   ├── trades.py                # GET /trades — history with AI reasoning
│   │   │   ├── signals.py               # GET /signals — all signals with filter reasons
│   │   │   ├── calibration.py           # GET /calibration — Brier scores, curves
│   │   │   ├── markets.py               # GET /markets — watched markets, scanner
│   │   │   ├── models.py                # GET /models — LLM cost, tokens, latency
│   │   │   └── config.py                # GET/PUT /config — thresholds, risk limits
│   │   ├── middleware/
│   │   │   └── auth.py                  # API key or Supabase JWT validation
│   │   └── schemas.py                   # Pydantic response models
│   │
│   ├── config/
│   │   ├── litellm_config.yaml          # LiteLLM Bedrock-first routing config
│   │   ├── trading_config.yaml          # Thresholds, limits, feature flags
│   │   └── .env                         # API keys (gitignored)
│   │
│   ├── requirements.txt                 # Python dependencies
│   └── Dockerfile                       # Bot + API container
│
├── dashboard/                           # ← TYPESCRIPT (Next.js on Vercel)
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx                 # Portfolio overview (default view)
│   │   │   ├── trades/page.tsx          # Trade history with reasoning
│   │   │   ├── signals/page.tsx         # Signal log with filter results
│   │   │   ├── calibration/page.tsx     # Brier score + calibration curves
│   │   │   ├── markets/page.tsx         # Active market scanner
│   │   │   ├── models/page.tsx          # LLM cost/usage dashboard
│   │   │   └── settings/page.tsx        # Config panel
│   │   ├── components/
│   │   │   ├── charts/                  # Recharts: P&L, calibration, exposure
│   │   │   ├── tables/                  # Trade history, signal log tables
│   │   │   └── layout/                  # Sidebar, header, theme
│   │   └── lib/
│   │       ├── api.ts                   # FastAPI client (fetch wrapper)
│   │       └── types.ts                 # Shared types matching Pydantic schemas
│   ├── package.json
│   ├── tailwind.config.ts
│   ├── next.config.ts
│   └── vercel.json
│
├── docker/
│   ├── docker-compose.yml               # PostgreSQL + Redis + Ollama + ChromaDB
│   ├── docker-compose.prod.yml          # Production overrides (resource limits)
│   └── init.sql                         # Database schema initialization
│
├── deploy/
│   ├── setup-ec2.sh                     # EC2 initial provisioning + IAM role
│   ├── systemd/                         # Timer definitions for each pipeline stage
│   └── terraform/                       # Optional IaC for EC2 + S3 + security groups
│
├── tests/
│   ├── test_kelly.py
│   ├── test_filters.py
│   ├── test_debate.py
│   └── test_backtest.py
│
└── README.md
```

---

## LiteLLM Configuration — Bedrock-First

```yaml
# bot/config/litellm_config.yaml

model_list:
  # ═══════════════════════════════════════════════════════════════
  # TIER 1: SCREENING (cheapest, highest volume)
  # ═══════════════════════════════════════════════════════════════
  
  # Primary: local Ollama (free, unlimited)
  - model_name: "screening"
    litellm_params:
      model: "ollama/qwen3:8b"
      api_base: "http://localhost:11434"
    model_info:
      description: "Local Qwen3-8B for high-volume market screening"

  # Fallback: Bedrock Llama (same region, no API key needed)
  - model_name: "screening"
    litellm_params:
      model: "bedrock/meta.llama3-3-70b-instruct-v1:0"
    model_info:
      description: "Bedrock Llama fallback for screening overflow"

  # Overflow: Groq free tier (external, rate limited)
  - model_name: "screening"
    litellm_params:
      model: "groq/llama-3.3-70b-versatile"
      api_key: "os.environ/GROQ_API_KEY"
    model_info:
      description: "Groq free tier burst capacity"

  # ═══════════════════════════════════════════════════════════════
  # TIER 2: ANALYSIS (balanced cost/quality)
  # ═══════════════════════════════════════════════════════════════
  
  # Primary: Bedrock Claude Haiku (same-region, IAM auth)
  - model_name: "analysis"
    litellm_params:
      model: "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0"
    model_info:
      description: "Primary analyst — probability estimation (Bedrock, eu-west-1)"

  # Fallback: DeepSeek (cheapest external at $0.28/M tokens)
  - model_name: "analysis"
    litellm_params:
      model: "deepseek/deepseek-chat"
      api_key: "os.environ/DEEPSEEK_API_KEY"
    model_info:
      description: "DeepSeek fallback — 10-30x cheaper than most providers"

  # Overflow: OpenAI GPT-4o-mini
  - model_name: "analysis"
    litellm_params:
      model: "openai/gpt-4o-mini"
      api_key: "os.environ/OPENAI_API_KEY"
    model_info:
      description: "OpenAI fallback for analysis"

  # ═══════════════════════════════════════════════════════════════
  # TIER 3: DECISION (highest quality for final trade calls)
  # ═══════════════════════════════════════════════════════════════
  
  # Primary: Bedrock Claude Sonnet (same-region, best reasoning)
  - model_name: "decision"
    litellm_params:
      model: "bedrock/anthropic.claude-sonnet-4-20250514-v1:0"
    model_info:
      description: "Final decision maker — high-edge trades (Bedrock, eu-west-1)"

  # Fallback: OpenAI GPT-4o
  - model_name: "decision"
    litellm_params:
      model: "openai/gpt-4o"
      api_key: "os.environ/OPENAI_API_KEY"
    model_info:
      description: "OpenAI fallback for decisions"

  # ═══════════════════════════════════════════════════════════════
  # TIER 4: DEBATE AGENTS (model diversity = different biases)
  # ═══════════════════════════════════════════════════════════════
  
  # Bull agent: local Ollama (different model family = genuine perspective diversity)
  - model_name: "bull_agent"
    litellm_params:
      model: "ollama/qwen3:14b"
      api_base: "http://localhost:11434"
    model_info:
      description: "Bull agent — Qwen3 local, different bias from Llama/Claude"

  # Bear agent: Bedrock Llama (different model family from bull)
  - model_name: "bear_agent"
    litellm_params:
      model: "bedrock/meta.llama3-3-70b-instruct-v1:0"
    model_info:
      description: "Bear agent — Llama via Bedrock, genuine disagreement"

  # Bear agent fallback: Groq (same Llama model, external)
  - model_name: "bear_agent"
    litellm_params:
      model: "groq/llama-3.3-70b-versatile"
      api_key: "os.environ/GROQ_API_KEY"
    model_info:
      description: "Bear agent fallback via Groq"

  # ═══════════════════════════════════════════════════════════════
  # TIER 5: SPECIALIZED
  # ═══════════════════════════════════════════════════════════════
  
  # Sentiment: local FinGPT (after fine-tuning in Phase 7)
  - model_name: "sentiment"
    litellm_params:
      model: "ollama/fingpt-llama:7b"
      api_base: "http://localhost:11434"
    model_info:
      description: "Specialized financial sentiment — zero marginal cost"

  # Sentiment fallback: Bedrock Haiku
  - model_name: "sentiment"
    litellm_params:
      model: "bedrock/anthropic.claude-3-5-haiku-20241022-v1:0"
    model_info:
      description: "Haiku fallback for sentiment when FinGPT not yet trained"

# Router settings
router_settings:
  routing_strategy: "simple-shuffle"    # Load balance across same-name models
  num_retries: 3
  retry_after: 5                        # seconds
  timeout: 60
  fallbacks:
    - analysis: ["screening"]           # If analysis tier fails, fall to screening
    - decision: ["analysis"]            # If decision tier fails, fall to analysis
  set_verbose: true

# General settings
general_settings:
  master_key: "os.environ/LITELLM_MASTER_KEY"
  database_url: "postgresql://bot:password@localhost:5432/litellm"
```

### Using LiteLLM in the Agent

```python
# bot/extensions/llm/router.py
from litellm import Router
import yaml

def create_router() -> Router:
    with open("config/litellm_config.yaml") as f:
        config = yaml.safe_load(f)
    
    return Router(
        model_list=config["model_list"],
        **config.get("router_settings", {})
    )

# Usage — IDENTICAL syntax regardless of provider:
router = create_router()

# Screening → routes to local Ollama, falls to Bedrock Llama, then Groq:
response = await router.acompletion(
    model="screening",
    messages=[{"role": "user", "content": "Filter these 50 markets..."}]
)

# Analysis → routes to Bedrock Claude Haiku (same-region), falls to DeepSeek:
response = await router.acompletion(
    model="analysis",
    messages=[{"role": "user", "content": market_analysis_prompt}]
)

# Decision → routes to Bedrock Claude Sonnet (same-region), falls to OpenAI GPT-4o:
response = await router.acompletion(
    model="decision",
    messages=[{"role": "user", "content": final_decision_prompt}]
)
```

**No API keys needed for Bedrock calls** — LiteLLM auto-detects the EC2 instance IAM role via `boto3` credential chain. Only external providers (OpenAI, DeepSeek, Groq) need explicit keys.

---

## Docker Compose (Local Services)

```yaml
# docker/docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: polybot
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped

  chromadb:
    image: chromadb/chroma:latest
    volumes:
      - chromadata:/chroma/chroma
    ports:
      - "8000:8000"
    restart: unless-stopped

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_models:/root/.ollama
    ports:
      - "11434:11434"
    deploy:
      resources:
        limits:
          memory: 6G
    restart: unless-stopped
    # Pull models on first start:
    # docker exec ollama ollama pull qwen3:8b
    # docker exec ollama ollama pull mistral:7b-instruct

  litellm:
    image: ghcr.io/berriai/litellm:main-latest
    volumes:
      - ../bot/config/litellm_config.yaml:/app/config.yaml
    command: ["--config", "/app/config.yaml"]
    ports:
      - "4000:4000"
    environment:
      # Bedrock: NO API KEY — uses EC2 IAM role via boto3
      - AWS_DEFAULT_REGION=eu-west-1
      # External providers (fallback only):
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
      - GROQ_API_KEY=${GROQ_API_KEY}
      # Internal:
      - DATABASE_URL=postgresql://bot:${DB_PASSWORD}@postgres:5432/litellm
      - REDIS_HOST=redis
    depends_on:
      - postgres
      - redis
      - ollama
    restart: unless-stopped

volumes:
  pgdata:
  chromadata:
  ollama_models:
```

---

## Phased Feature Plan

### Phase 1: Foundation (Weeks 1-3)
**Goal:** Fork repo, replace OpenAI with LiteLLM+Bedrock, deploy to EU, run first autonomous trade.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 1.1 | Fork & setup | Fork Polymarket/agents, setup dev environment, run locally | CRITICAL |
| 1.2 | Docker Compose | PostgreSQL + Redis + ChromaDB + Ollama + LiteLLM | CRITICAL |
| 1.3 | Bedrock model access | Request access to Claude Haiku, Sonnet, Llama 3.3, Mistral in eu-west-1 console | CRITICAL |
| 1.4 | Replace OpenAI with LiteLLM | Swap all `langchain-openai` calls → LiteLLM router with Bedrock-first config | CRITICAL |
| 1.5 | Pull Ollama models | Qwen3-8B + Mistral-7B-Instruct on EC2 | CRITICAL |
| 1.6 | Deploy to AWS eu-west-1 | EC2 spot + Elastic IP + IAM role (BedrockFullAccess) + security groups | CRITICAL |
| 1.7 | Verify geo-compliance | Confirm all Polymarket requests exit from Irish IP | CRITICAL |
| 1.8 | Basic systemd timers | Run `one_best_trade()` every 4 hours automatically | HIGH |
| 1.9 | Telegram notifications | Alert on every trade + errors + daily status | HIGH |
| 1.10 | PostgreSQL schema | Migrate from in-memory to persistent trade/signal storage | HIGH |
| 1.11 | First live trade | Paper trade mode → verify → execute first real trade | HIGH |

**Deliverable:** Bot running 24/7 in Ireland, making 1-2 trades/day via Bedrock Claude Haiku + local Qwen3 with OpenAI/DeepSeek/Groq as fallbacks.

---

### Phase 2: Data Pipeline + Enrichment (Weeks 4-6)
**Goal:** Feed the bot vastly richer context than raw Gamma API + NewsAPI.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 2.1 | GDELT collector | 15-min news with tone scores, geo metadata | CRITICAL |
| 2.2 | FRED collector | Daily economic data (8 key series) | HIGH |
| 2.3 | Reddit/PRAW collector | Hourly sentiment from 8 subreddits | HIGH |
| 2.4 | FiveThirtyEight collector | Daily polling data for political markets | HIGH |
| 2.5 | Dune on-chain collector | 4-hourly whale wallet tracking | MEDIUM |
| 2.6 | Polymarket WebSocket | Real-time price stream (replace REST polling) | HIGH |
| 2.7 | Context builder | Assemble per-market dossiers from all sources | CRITICAL |
| 2.8 | News deduplicator | TF-IDF similarity to collapse duplicate stories | MEDIUM |
| 2.9 | Sentiment aggregator | VADER + GDELT tone → composite sentiment score | MEDIUM |
| 2.10 | Resolution monitor | Track resolution source URLs for changes | MEDIUM |
| 2.11 | ChromaDB enrichment | Index all new data sources into vector store | HIGH |
| 2.12 | RAG competence filter | Only analyze markets where we have data depth | HIGH |

**Deliverable:** 7 data sources feeding ChromaDB + context builder. Markets get rich dossiers before AI analysis.

---

### Phase 3: Advanced Analysis + Debate (Weeks 7-9)
**Goal:** Multi-agent debate with superforecaster calibration replaces single-model analysis.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 3.1 | Bull agent | Ollama/Qwen3-14B argues YES case with evidence | CRITICAL |
| 3.2 | Bear agent | Bedrock/Llama-3.3-70B argues NO case with evidence | CRITICAL |
| 3.3 | Aggregator agent | Bedrock/Claude Haiku synthesizes with weighted probability | CRITICAL |
| 3.4 | Superforecaster layer | Tetlock calibration prompt: base rates, reference classes | HIGH |
| 3.5 | Escalation logic | Haiku for routine → Bedrock/Sonnet for high-edge (>15pp) | HIGH |
| 3.6 | Multi-model diversity | Bull=Ollama/Qwen, Bear=Bedrock/Llama, Agg=Bedrock/Claude | HIGH |
| 3.7 | Confidence scoring | Aggregate LLM confidence + agent agreement ratio | HIGH |
| 3.8 | LangSmith integration | Trace every LLM call with inputs/outputs/cost | MEDIUM |
| 3.9 | Prompt versioning | Track prompt templates in Git, A/B test variants | MEDIUM |
| 3.10 | Batch analysis mode | Analyze top 20 markets in parallel, not sequential | MEDIUM |

**Deliverable:** Multi-agent debate system producing calibrated probability estimates with full observability.

---

### Phase 4: Signal Filtering + Risk Management (Weeks 10-12)
**Goal:** Only the highest-quality signals survive to execution. Never risk more than Kelly says.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 4.1 | Edge detector | Require |p_model - p_market| > configurable threshold | CRITICAL |
| 4.2 | Liquidity filter | Min $5K orderbook depth within 3¢ of mid | CRITICAL |
| 4.3 | Time-to-resolution | Filter <24h (too late) and >6mo (capital lock) | HIGH |
| 4.4 | Correlation guard | Max 3 positions in same category | HIGH |
| 4.5 | Confidence gate | Require confidence ≥7/10 AND ≥2/3 agents agree | HIGH |
| 4.6 | Kelly criterion | Fractional Kelly (25%) position sizing | CRITICAL |
| 4.7 | Portfolio risk engine | Max 10% single, 40% total, 50% cash reserve | CRITICAL |
| 4.8 | Daily loss circuit breaker | Stop trading if daily loss exceeds 5% | CRITICAL |
| 4.9 | Paper trade gate | New strategy versions run 30 days paper first | HIGH |
| 4.10 | Smart order router | Split large orders, slippage protection | HIGH |
| 4.11 | WebSocket fill monitor | Real-time fill confirmations | HIGH |
| 4.12 | Exit manager | TP (edge <2pp), SL (-15%), time-based exits | HIGH |

**Deliverable:** Production-grade risk management. ~80% of signals filtered. Kelly-sized positions with hard limits.

---

### Phase 5: Monitoring + Feedback Loops (Weeks 13-15)
**Goal:** Complete observability and continuous improvement through data.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 5.1 | Position tracker | Live portfolio state refreshed every 5 min | CRITICAL |
| 5.2 | FastAPI REST endpoints | /portfolio, /trades, /signals, /calibration, /models, /config | CRITICAL |
| 5.3 | API authentication | API key + Supabase JWT middleware | HIGH |
| 5.4 | Calibration monitor | Brier score + "when we say 70%, is it 70%?" | HIGH |
| 5.5 | Training data logger | Log context → prediction → outcome to S3 as JSONL | HIGH |
| 5.6 | Telegram daily summary | Trades, P&L, open positions, next analysis cycle | HIGH |
| 5.7 | Error alerting | Immediate notification on API failures, order rejects | HIGH |
| 5.8 | Model cost dashboard | Per-model token usage, cost, latency via LiteLLM | MEDIUM |
| 5.9 | Threshold auto-tuner | Adjust edge/confidence thresholds based on backtest | MEDIUM |
| 5.10 | Market resolution tracker | Auto-detect resolved markets, calculate realized P&L | HIGH |
| 5.11 | Weekly calibration report | Telegram report with Brier score + calibration curve | MEDIUM |

**Deliverable:** Full REST API serving bot data. Every prediction tracked against outcome. Ready for dashboard.

---

### Phase 6: Dashboard (Weeks 14-17, overlaps Phase 5)
**Goal:** Visual interface for portfolio monitoring, trade analysis, and bot configuration.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 6.1 | Next.js project setup | `create-next-app` with TypeScript, Tailwind, shadcn/ui | CRITICAL |
| 6.2 | API client library | Type-safe fetch wrapper matching FastAPI Pydantic schemas | CRITICAL |
| 6.3 | Portfolio page | Open positions, unrealized P&L, exposure %, cash reserve | CRITICAL |
| 6.4 | Trade history page | Table: market question, side, size, entry/exit, P&L, AI reasoning | HIGH |
| 6.5 | Signal log page | Every signal: p_model, p_market, edge, confidence, pass/reject + why | HIGH |
| 6.6 | Calibration page | Brier score over time + interactive calibration curve (Recharts) | HIGH |
| 6.7 | Market scanner page | What the bot is currently watching, data freshness, next analysis | HIGH |
| 6.8 | LLM metrics page | Per-model cost, tokens, latency, error rate (from LiteLLM DB) | MEDIUM |
| 6.9 | Config panel | Edit thresholds, risk limits, model selection, toggle paper mode | MEDIUM |
| 6.10 | Real-time updates | SSE (Server-Sent Events) from FastAPI → live dashboard updates | MEDIUM |
| 6.11 | Authentication | Supabase Auth (single user now, multi-user SaaS later) | HIGH |
| 6.12 | Deploy to Vercel | Connect GitHub repo, auto-deploy dashboard/ directory | HIGH |

**Dashboard tech stack:**
- Next.js 15 + TypeScript + Tailwind CSS + shadcn/ui
- Recharts for P&L charts, calibration curves, exposure pie
- Supabase Auth for login (prepares multi-user SaaS path)
- Vercel free tier hosting (generous for single-user)
- FastAPI SSE for real-time position/trade updates

**Deliverable:** Production dashboard on Vercel showing portfolio, trades, signals, calibration, costs, config. Template for future SaaS multi-user version.

---

### Phase 7: Model Training + Fine-Tuning (Weeks 18-22)
**Goal:** Use accumulated prediction data to train specialized models.

| # | Task | Details | Priority |
|---|------|---------|----------|
| 7.1 | Training data builder | Compile S3 JSONL into train/val/test splits | CRITICAL |
| 7.2 | Spot GPU provisioning | Script to spin up g4dn.xlarge, train, destroy | CRITICAL |
| 7.3 | QLoRA fine-tuning | Fine-tune Qwen3-8B on market analysis → outcome | HIGH |
| 7.4 | Eval harness | Compare fine-tuned vs base model on held-out data | HIGH |
| 7.5 | Sentiment fine-tune | Train FinGPT variant on Polymarket-specific sentiment | HIGH |
| 7.6 | Deploy to Ollama | Push adapter weights → Ollama on EC2 | HIGH |
| 7.7 | A/B testing framework | Run fine-tuned vs base in parallel, compare Brier | MEDIUM |
| 7.8 | Continuous training | Monthly retraining pipeline triggered by cron | MEDIUM |
| 7.9 | Bedrock custom model | Deploy fine-tuned model to Bedrock custom model import | MEDIUM |
| 7.10 | RLHF from outcomes | Use resolved market outcomes as reward signal | LOW |
| 7.11 | Distillation pipeline | Distill Sonnet's reasoning into smaller local model | LOW |

**Training architecture:**
```
Daily:  Bot runs → logs context + prediction + outcome to S3
Monthly: Cron triggers →
         1. Download training data from S3
         2. Spin up g4dn.xlarge spot ($0.16/hr)
         3. QLoRA fine-tune Qwen3-8B (~2 hours = $0.32)
         4. Evaluate on held-out test set
         5. If improved: push weights to Ollama on EC2
         6. If not: keep current model, adjust training data
         7. Terminate spot instance
         Total cost per training run: ~$0.50
         
Optional: Deploy fine-tuned model to Bedrock via Custom Model Import
          → eliminates Ollama dependency for that model
          → inference via same Bedrock IAM auth
```

**Deliverable:** Self-improving models that get better as they accumulate prediction data. Fine-tuned local models replace expensive cloud API calls over time.

---

## LLM Routing Strategy by Pipeline Stage

| Pipeline Stage | Primary Model | Fallback 1 | Fallback 2 | Why |
|---------------|--------------|------------|------------|-----|
| Market screening | Ollama/Qwen3-8B (local) | Bedrock/Llama-3.3-70B | Groq/Llama (free) | High volume (~50 markets), local = free |
| RAG filtering | Ollama/Qwen3-8B (local) | Bedrock/Llama | — | Simple relevance check |
| Bull agent (debate) | Ollama/Qwen3-14B (local) | DeepSeek-Chat | — | Qwen family = different bias from Llama/Claude |
| Bear agent (debate) | Bedrock/Llama-3.3-70B | Groq/Llama | Ollama/Mistral-7B | Different model family = genuine disagreement |
| Aggregator | Bedrock/Claude Haiku 3.5 | DeepSeek-Chat | OpenAI/GPT-4o-mini | Calibrated reasoning, same-region |
| Superforecaster calibration | Bedrock/Claude Haiku 3.5 | OpenAI/GPT-4o-mini | — | Tetlock methodology needs instruction-following |
| High-edge escalation | Bedrock/Claude Sonnet 4 | OpenAI/GPT-4o | — | Best reasoning for decisions worth >$100 |
| Sentiment analysis | Ollama/FinGPT (fine-tuned) | Bedrock/Claude Haiku | — | Specialized local model, zero marginal cost |
| Exit decisions | Bedrock/Claude Haiku 3.5 | Ollama/Qwen3 | — | Quick assessment, moderate quality needed |

**Routing priority:** Local Ollama (free) → Bedrock (same-region, IAM auth) → DeepSeek (cheapest external) → Groq (free tier) → OpenAI (highest quality fallback)

**Key principles:**
1. **Bedrock as primary for all paid inference** — same-region latency, single bill, EU data residency
2. **Model diversity for debate agents** — different model families (Qwen vs Llama vs Claude) = different biases = better synthesis
3. **Quality for final decisions** — Sonnet for high-edge trades, Haiku for routine analysis
4. **Cost-efficiency for screening** — local Ollama first, Bedrock Llama as backup
5. **OpenAI as external safety net** — if AWS has an outage, OpenAI keeps the bot running

---

## Cron Schedule (systemd timers)

```
# Pipeline runs on EC2 via systemd timers

Every 15 min:    collect-prices       # Polymarket CLOB + GDELT news
Hourly:          collect-social       # Reddit sentiment scan
Every 4 hours:   full-analysis        # Complete pipeline: enrich → debate → filter → validate → execute
Every 5 min:     monitor-positions    # Check fills, exits, portfolio state
Daily 06:00 UTC: daily-data           # FRED + FiveThirtyEight + market refresh
Daily 22:00 UTC: daily-review         # EOD summary, resolve markets, calibration
Weekly Sunday:   recalibrate          # Backtest, threshold adjustment, training data export
Monthly 1st:     retrain              # Spin up GPU, fine-tune, evaluate, deploy
Continuous:      websocket-stream     # Polymarket WebSocket price feed (background process)
```

---

## Key Modifications to Polymarket/agents Base

### 1. Replace OpenAI with LiteLLM + Bedrock (agent.py)

```python
# BEFORE (Polymarket/agents):
from langchain_openai import ChatOpenAI
llm = ChatOpenAI(model="gpt-4", api_key=os.getenv("OPENAI_API_KEY"))

# AFTER (our fork):
from litellm import Router
router = Router(model_list=load_config("litellm_config.yaml"))

# All calls go through router — Bedrock primary, no API keys for AWS:
response = await router.acompletion(
    model="analysis",  # Routes to Bedrock Claude Haiku (same-region, IAM auth)
    messages=messages
)
```

### 2. Extend one_best_trade() → full_pipeline() (trade.py)

```python
# BEFORE: one_best_trade() → single LLM call → single trade → done

# AFTER: Full 7-stage pipeline
async def full_pipeline(config, db, router):
    # Stage 1: Collect latest data
    await run_collectors(db)
    
    # Stage 2: Enrich and build context
    markets = await discover_and_filter_markets(db)
    contexts = [build_context(db, m) for m in markets]
    
    # Stage 3: AI Analysis (debate + calibration)
    signals = []
    for ctx in contexts:
        result = await debate_engine.analyze(ctx, router)
        if result["edge"] > config["min_edge"]:
            # Escalate high-edge to Bedrock Sonnet
            if result["edge"] > 0.15:
                result = await escalate_to_sonnet(ctx, router)
            signals.append(result)
    
    # Stage 4: Filter
    approved = filter_pipeline.filter_all(signals, db)
    
    # Stage 5: Size & Validate
    orders = []
    for signal in approved:
        size = kelly.calculate(signal, portfolio_state(db))
        if risk_engine.validate(signal, size, db):
            orders.append((signal, size))
    
    # Stage 6: Execute
    for signal, size in orders:
        if paper_trade_gate.should_paper(signal.strategy_version):
            paper_trade_gate.record(signal, size)
        else:
            order = await smart_router.execute(signal, size)
            telegram.trade_alert(signal, size, order)
    
    # Stage 7: Monitor (runs separately on 5-min timer)
    training_logger.log_all(contexts, signals, approved, orders)
```

### 3. Add persistent state (replace in-memory)

```python
# BEFORE: Ephemeral — state lost between runs
# AFTER: PostgreSQL for all trade/signal/position state

# bot/extensions/db/models.py
from sqlalchemy import create_engine, Column, Float, String, Integer, DateTime, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    market_id = Column(String, index=True)
    market_question = Column(String)
    token_id = Column(String)
    side = Column(String)
    size = Column(Float)
    entry_price = Column(Float)
    exit_price = Column(Float)
    pnl = Column(Float)
    p_model = Column(Float)
    p_market = Column(Float)
    edge = Column(Float)
    confidence = Column(Integer)
    strategy_version = Column(String)
    reasoning = Column(JSON)           # Full AI reasoning for dashboard display
    status = Column(String, default="open")
    created_at = Column(DateTime, server_default="now()")
    closed_at = Column(DateTime, nullable=True)

class Signal(Base):
    __tablename__ = "signals"
    id = Column(Integer, primary_key=True)
    market_id = Column(String, index=True)
    market_question = Column(String)
    p_model = Column(Float)
    p_market = Column(Float)
    edge = Column(Float)
    confidence = Column(Integer)
    bull_p = Column(Float)
    bear_p = Column(Float)
    aggregator_p = Column(Float)
    agreement = Column(Float)
    model_used = Column(String)
    passed_filters = Column(Integer)   # boolean
    filter_reason = Column(String)
    debate_summary = Column(JSON)      # Bull/bear arguments for dashboard
    created_at = Column(DateTime, server_default="now()")

class CalibrationEntry(Base):
    __tablename__ = "calibration"
    id = Column(Integer, primary_key=True)
    market_id = Column(String, index=True)
    predicted_p = Column(Float)
    actual_outcome = Column(Integer)   # 1=YES, 0=NO
    brier_score = Column(Float)
    resolved_at = Column(DateTime)
    created_at = Column(DateTime, server_default="now()")
```

---

## Summary: What We Keep vs. Add vs. Replace

| Component | Polymarket/agents | Our Extension |
|-----------|-------------------|---------------|
| Market discovery | ✅ Keep GammaMarketClient | + WebSocket real-time prices |
| CLOB trading | ✅ Keep Polymarket class | + Smart order router, fill monitor, exit manager |
| Vector store | ✅ Keep ChromaDB | + Index 7 data sources instead of just news |
| RAG filtering | ✅ Keep competence filter | + Richer context matching |
| Superforecaster | ✅ Keep methodology | + As calibration layer after debate |
| LangGraph orchestration | ✅ Keep for pipeline | + Extend with 7-stage workflow |
| FastAPI server | ✅ Keep for remote API | + Full REST API for dashboard |
| OpenAI-only LLM | ❌ Replace | → LiteLLM with **Bedrock primary** + OpenAI/DeepSeek/Groq fallback |
| Single model analysis | ❌ Replace | → Multi-agent bull/bear debate with model diversity |
| No data pipeline | ❌ Missing | → 7 collectors + enrichment |
| No risk management | ❌ Missing | → Kelly + filters + risk engine |
| No monitoring | ❌ Missing | → Telegram + P&L + calibration |
| No dashboard | ❌ Missing | → **Next.js + TypeScript on Vercel** |
| No training | ❌ Missing | → S3 logging + QLoRA pipeline + Bedrock custom model import |
| No position tracking | ❌ Missing | → PostgreSQL + exit manager |
| No paper trading | ❌ Missing | → Paper trade gate |
| In-memory state | ❌ Replace | → PostgreSQL persistent state |
