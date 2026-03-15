# Polymarket/agents Extended — Architecture Summary

> **v2** — Bedrock-First · Python Bot + TypeScript Dashboard · EU-Compliant · Self-Training

## Quick Reference

| Dimension | Value |
|-----------|-------|
| **Monthly Cost** | $65-90 (of $200 budget) |
| **Phases** | 7 phases, 22 weeks |
| **Primary LLM** | AWS Bedrock (same-region, IAM auth) |
| **Fallback LLMs** | OpenAI → DeepSeek → Groq → Ollama |
| **Data Sources** | 7 (all free tier) |
| **Region** | eu-west-1 (Ireland), Elastic IP |
| **Bot Language** | Python (forked Polymarket/agents) |
| **Dashboard Language** | TypeScript (Next.js on Vercel) |
| **Infrastructure** | EC2 c6a.xlarge spot + Docker Compose |

---

## Core Decision

**Fork & extend** Polymarket/agents. Keep its strengths, replace its weaknesses, add everything missing.

**Keep:** ChromaDB RAG, superforecaster prompting, GammaMarketClient, py-clob-client CLOB trading, LangGraph orchestration, FastAPI server.

**Replace:** OpenAI-only LLM → LiteLLM with Bedrock-first routing. Single model analysis → multi-agent bull/bear debate. In-memory state → PostgreSQL.

**Add:** 7 data collectors, signal filtering (~80% rejection), Kelly criterion sizing, portfolio risk engine, Telegram monitoring, Next.js dashboard, S3 training logger, QLoRA fine-tuning pipeline.

---

## Why Bedrock as Primary

| Advantage | Detail |
|-----------|--------|
| **Same-region latency** | ~5-15ms (same VPC) vs ~100-200ms external APIs |
| **Single AWS bill** | Compute + inference on one invoice, one Cost Explorer |
| **EU data residency** | All inference data stays in eu-west-1 Ireland |
| **IAM authentication** | No API keys needed — EC2 role auto-detected by LiteLLM |
| **Model coverage** | Claude Haiku 3.5, Sonnet 4, Llama 3.3 70B, Mistral Large |

---

## Why EC2 over Fargate

| Factor | EC2 c6a.xlarge (spot) | Fargate equivalent |
|--------|----------------------|-------------------|
| Monthly cost | ~$45 | ~$144 (3.2x more) |
| Ollama support | Models cached on EBS | No persistent storage, cold start every restart |
| WebSocket | Stable long-lived connections | Tasks recyclable, connections interrupted |
| Local storage | 100GB EBS for ChromaDB, models | Ephemeral only |

---

## LLM Routing Strategy

All calls go through LiteLLM with identical syntax: `router.acompletion(model="tier_name")`.

**Priority order:** Local Ollama (free) → Bedrock (same-region, IAM) → DeepSeek ($0.28/M) → Groq (free tier) → OpenAI (safety net).

| Pipeline Stage | Primary | Fallback 1 | Fallback 2 | Why |
|---------------|---------|------------|------------|-----|
| Market screening | Ollama/Qwen3-8B | Bedrock/Llama-3.3-70B | Groq (free) | High volume, local = free |
| RAG filtering | Ollama/Qwen3-8B | Bedrock/Llama | — | Simple relevance check |
| Bull agent | Ollama/Qwen3-14B | DeepSeek-Chat | — | Qwen family = different bias |
| Bear agent | Bedrock/Llama-3.3-70B | Groq/Llama | Ollama/Mistral | Different model = disagreement |
| Aggregator | Bedrock/Claude Haiku 3.5 | DeepSeek-Chat | OpenAI/4o-mini | Calibrated reasoning |
| Superforecaster | Bedrock/Claude Haiku 3.5 | OpenAI/GPT-4o-mini | — | Tetlock needs instruction-following |
| High-edge (>15pp) | Bedrock/Claude Sonnet 4 | OpenAI/GPT-4o | — | Best reasoning for >$100 decisions |
| Sentiment | Ollama/FinGPT (tuned) | Bedrock/Claude Haiku | — | Specialized local, zero cost |
| Exit decisions | Bedrock/Claude Haiku 3.5 | Ollama/Qwen3 | — | Quick assessment |

**Key principles:**
1. Bedrock for all paid inference (same-region, single bill, EU)
2. Model diversity in debate (Qwen vs Llama vs Claude = different biases)
3. Quality for final decisions (Sonnet for high-edge)
4. Cost-efficiency for screening (local Ollama first)
5. OpenAI as external safety net (AWS outage protection)

---

## 7-Stage Trading Pipeline

```
Every 4 hours (systemd timer):

Stage 1: COLLECT      → 7 data sources (GDELT, FRED, Reddit, 538, Dune, Tavily, WebSocket)
Stage 2: ENRICH       → Deduplicate, score sentiment, build per-market dossiers, RAG filter
Stage 3: ANALYZE      → Bull/Bear debate → Aggregator → Superforecaster calibration
                         High-edge (>15pp) escalated to Bedrock/Sonnet
Stage 4: FILTER       → Edge + Liquidity + Time + Correlation + Confidence (~80% rejected)
Stage 5: SIZE         → Kelly criterion (25% fractional) + portfolio risk engine
Stage 6: EXECUTE      → Paper trade gate → smart order router → fill monitor → Telegram alert
Stage 7: MONITOR      → Position tracker + exit manager + S3 training logger (runs on 5-min timer)
```

---

## Monthly Cost Breakdown

| Component | Provider | Cost |
|-----------|----------|------|
| EC2 c6a.xlarge spot (Ireland) | AWS | ~$45 |
| EBS 100GB gp3 | AWS | ~$8 |
| S3 training data | AWS | ~$1 |
| Bedrock Claude Haiku 3.5 (~300/day) | AWS Bedrock | $3-8 |
| Bedrock Claude Sonnet 4 (~50/day) | AWS Bedrock | $5-15 |
| Bedrock Llama 3.3 70B (debate) | AWS Bedrock | $1-3 |
| OpenAI GPT-4o (fallback only) | OpenAI | $0-5 |
| DeepSeek V3 (cheap overflow) | DeepSeek | $0-3 |
| Groq free tier (burst) | Groq | $0 |
| Ollama local models | Local | $0 |
| 7 data sources | Free APIs | $0 |
| Vercel dashboard hosting | Vercel | $0 |
| Telegram Bot | Telegram | $0 |
| **TOTAL** | | **$65-90/mo** |

Budget remaining: $110-135 for upgrades or GPU training runs.

---

## Phased Development Plan

### Phase 1: Foundation (Weeks 1-3)

Fork repo, replace OpenAI with LiteLLM+Bedrock, deploy to EU, first trade.

| Task | Priority |
|------|----------|
| Fork Polymarket/agents, setup dev env | CRITICAL |
| Docker Compose (PG + Redis + ChromaDB + Ollama + LiteLLM) | CRITICAL |
| Request Bedrock model access in eu-west-1 | CRITICAL |
| Replace OpenAI → LiteLLM with Bedrock-first routing | CRITICAL |
| Pull Ollama models (Qwen3-8B, Mistral-7B) | CRITICAL |
| Deploy EC2 + Elastic IP + IAM role (BedrockFullAccess) | CRITICAL |
| Verify geo-compliance (Irish IP) | CRITICAL |
| Systemd timers for 4-hour cycle | HIGH |
| Telegram notifications | HIGH |
| PostgreSQL schema (replace in-memory) | HIGH |
| First paper trade → first live trade | HIGH |

**Deliverable:** Bot running 24/7 in Ireland via Bedrock Haiku + local Qwen3 + fallbacks.

### Phase 2: Data Pipeline (Weeks 4-6)

Feed the bot richer context than raw Gamma API + NewsAPI.

| Task | Priority |
|------|----------|
| GDELT news collector (15-min, tone scores) | CRITICAL |
| FRED economic data (8 key series) | HIGH |
| Reddit/PRAW sentiment (8 subreddits, hourly) | HIGH |
| FiveThirtyEight polling (political markets) | HIGH |
| Dune on-chain whale tracking (4-hourly) | MEDIUM |
| Polymarket WebSocket real-time prices | HIGH |
| Context builder (per-market dossiers) | CRITICAL |
| News deduplicator (TF-IDF) | MEDIUM |
| Sentiment aggregator (VADER + GDELT tone) | MEDIUM |
| Resolution source monitor | MEDIUM |
| ChromaDB: index all new sources | HIGH |
| RAG competence filter | HIGH |

**Deliverable:** 7 data sources feeding ChromaDB. Rich dossiers before AI analysis.

### Phase 3: AI Debate (Weeks 7-9)

Multi-agent debate with superforecaster calibration.

| Task | Priority |
|------|----------|
| Bull agent (Ollama/Qwen — argues YES) | CRITICAL |
| Bear agent (Bedrock/Llama — argues NO) | CRITICAL |
| Aggregator (Bedrock/Claude Haiku) | CRITICAL |
| Superforecaster calibration (Tetlock base rates) | HIGH |
| Escalation: Haiku → Sonnet for edge >15pp | HIGH |
| Multi-model diversity (Qwen vs Llama vs Claude) | HIGH |
| Confidence scoring (LLM + agent agreement) | HIGH |
| LangSmith observability | MEDIUM |
| Prompt versioning + A/B testing | MEDIUM |
| Batch analysis (top 20 in parallel) | MEDIUM |

**Deliverable:** Multi-agent debate producing calibrated probabilities with observability.

### Phase 4: Risk & Execution (Weeks 10-12)

Only highest-quality signals survive. Kelly-sized positions with hard limits.

| Task | Priority |
|------|----------|
| Edge detector (threshold configurable) | CRITICAL |
| Liquidity filter ($5K min depth) | CRITICAL |
| Time-to-resolution filter | HIGH |
| Correlation guard (max 3 per category) | HIGH |
| Confidence gate (≥7/10 AND ≥2/3 agree) | HIGH |
| Kelly criterion (25% fractional) | CRITICAL |
| Portfolio risk engine (10% single, 40% total) | CRITICAL |
| Daily loss circuit breaker (5% stop) | CRITICAL |
| Paper trade gate (30 days for new) | HIGH |
| Smart order router (slippage protection) | HIGH |
| WebSocket fill monitor | HIGH |
| Exit manager (TP/SL/time-based) | HIGH |

**Deliverable:** Production risk management. ~80% filtered. Kelly-sized positions.

### Phase 5: Monitoring + API (Weeks 13-15)

Complete observability and REST API for dashboard.

| Task | Priority |
|------|----------|
| Position tracker (5-min refresh) | CRITICAL |
| FastAPI REST endpoints | CRITICAL |
| API auth (API key + Supabase JWT) | HIGH |
| Calibration monitor (Brier score) | HIGH |
| Training data logger (S3 JSONL) | HIGH |
| Telegram daily summary | HIGH |
| Error alerting | HIGH |
| Model cost metrics (LiteLLM DB) | MEDIUM |
| Threshold auto-tuner | MEDIUM |
| Market resolution tracker | HIGH |
| Weekly calibration report | MEDIUM |

**Deliverable:** Full REST API. Every prediction tracked. Ready for dashboard.

### Phase 6: Dashboard (Weeks 14-17, overlaps Phase 5)

Next.js + TypeScript visual interface on Vercel.

| Task | Priority |
|------|----------|
| Next.js project (TS + Tailwind + shadcn/ui) | CRITICAL |
| Type-safe API client | CRITICAL |
| Portfolio page (positions, P&L, exposure %) | CRITICAL |
| Trade history page (+ AI reasoning) | HIGH |
| Signal log page (edge, pass/reject + why) | HIGH |
| Calibration page (Brier score + curve) | HIGH |
| Market scanner page (bot watchlist) | HIGH |
| LLM metrics page (cost, tokens, latency) | MEDIUM |
| Config panel (thresholds, risk limits) | MEDIUM |
| SSE real-time updates from FastAPI | MEDIUM |
| Supabase Auth (→ multi-user later) | HIGH |
| Deploy to Vercel | HIGH |

**Tech stack:** Next.js 15 + TypeScript + Tailwind + shadcn/ui + Recharts + Supabase Auth.

**Deliverable:** Production dashboard on Vercel. Template for SaaS multi-user version.

### Phase 7: Model Training (Weeks 18-22)

Self-improving models trained on accumulated prediction data.

| Task | Priority |
|------|----------|
| Training data builder (S3 → splits) | CRITICAL |
| Spot GPU provisioning (g4dn.xlarge) | CRITICAL |
| QLoRA fine-tune Qwen3-8B | HIGH |
| Eval harness (fine-tuned vs base) | HIGH |
| Sentiment fine-tune (FinGPT) | HIGH |
| Deploy to Ollama on EC2 | HIGH |
| A/B testing (compare Brier scores) | MEDIUM |
| Monthly retraining cron | MEDIUM |
| Bedrock custom model import | MEDIUM |
| RLHF from market outcomes | LOW |
| Distill Sonnet → local model | LOW |

**Training loop:** Daily bot logs to S3 → Monthly cron spins up g4dn.xlarge spot ($0.16/hr) → QLoRA fine-tune (~2h = $0.32) → evaluate → if better, push to Ollama → terminate instance. ~$0.50/run.

**Deliverable:** Self-improving models replacing expensive cloud APIs over time.

---

## Cron Schedule

| Frequency | Job | What it does |
|-----------|-----|-------------|
| Every 15 min | collect-prices | Polymarket CLOB + GDELT news |
| Hourly | collect-social | Reddit sentiment scan |
| Every 4 hours | full-analysis | Complete 7-stage pipeline |
| Every 5 min | monitor-positions | Fills, exits, portfolio state |
| Daily 06:00 UTC | daily-data | FRED + FiveThirtyEight + market refresh |
| Daily 22:00 UTC | daily-review | EOD summary, resolve markets, calibration |
| Weekly Sunday | recalibrate | Backtest, threshold adjustment, training export |
| Monthly 1st | retrain | GPU spot → fine-tune → evaluate → deploy |
| Continuous | websocket-stream | Polymarket WebSocket price feed |

---

## Project Structure

```
polymarket-agents-extended/
├── bot/                           ← Python (trading engine)
│   ├── agents/                       Forked from Polymarket/agents
│   │   ├── ai/agent.py              MODIFIED: OpenAI → LiteLLM
│   │   ├── ai/superforecaster.py    EXTRACTED: Tetlock logic
│   │   ├── ai/debate.py             NEW: multi-agent debate
│   │   ├── application/trade.py     MODIFIED: 7-stage pipeline
│   │   ├── application/autonomous.py NEW: 24/7 loop
│   │   ├── polymarket/              KEEP: gamma, chroma, CLOB
│   │   └── connectors/              KEEP: tavily, news
│   ├── extensions/                   All new capabilities
│   │   ├── llm/                      LiteLLM + Bedrock routing
│   │   ├── collectors/               7 data collectors
│   │   ├── enrichment/               Context builder, dedup, sentiment
│   │   ├── analysis/                 Debate engine, calibration, escalation
│   │   ├── filtering/                Edge, liquidity, time, correlation, confidence
│   │   ├── validation/               Kelly, risk engine, paper trade, backtest
│   │   ├── execution/                Smart router, fill monitor, exit manager
│   │   ├── monitoring/               Telegram, calibration, training logger
│   │   └── training/                 QLoRA, eval harness
│   ├── api/                          FastAPI REST for dashboard
│   │   ├── routes/                   /portfolio /trades /signals /calibration /config
│   │   └── middleware/auth.py        API key + Supabase JWT
│   └── config/
│       └── litellm_config.yaml       Bedrock-first routing
│
├── dashboard/                     ← TypeScript (Next.js on Vercel)
│   ├── src/app/                      Pages: portfolio, trades, signals, calibration
│   ├── src/components/               Charts (Recharts), tables, layout
│   └── src/lib/                      API client, types
│
├── docker/
│   └── docker-compose.yml            PostgreSQL + Redis + Ollama + ChromaDB + LiteLLM
│
└── deploy/
    ├── setup-ec2.sh                  Provisioning + IAM role
    └── systemd/                      Timer definitions
```

---

## Mermaid Diagrams

Four mermaid diagram files are provided alongside this document:

1. **`architecture-system.mermaid`** — Full system architecture showing EC2, Docker services, extensions, Vercel dashboard, and data flow
2. **`architecture-llm-routing.mermaid`** — LLM routing flowchart showing every pipeline stage mapped to primary/fallback models across Ollama, Bedrock, and external providers
3. **`architecture-pipeline.mermaid`** — 7-stage trading pipeline from data collection through execution and monitoring, with decision points and filter gates
4. **`architecture-timeline.mermaid`** — Gantt chart showing all 7 phases across 22 weeks with task dependencies and milestones
