# Recommendations: Current Gaps, Agentic Workflow, and LLM Stack

## Snapshot: What Is Implemented Today

Current runtime is a solid base Polymarket agent with:

- Polymarket Gamma + CLOB integration
- OpenAI-based analysis (`ChatOpenAI`) for superforecast + trade action
- Local Chroma RAG with OpenAI embeddings
- NewsAPI enrichment for event-specific analysis
- CLI-driven execution with dry-run/live mode

## Confirmed Gaps vs Extended Architecture

These items are documented in `docs/expension/*` but not implemented in runtime yet:

1. Tavily is not in the active trading path.
2. No LiteLLM router and no Bedrock-first model routing.
3. No Ollama/local model path for screening.
4. No multi-agent debate (bull/bear/aggregator); current flow is single-model.
5. No PostgreSQL/Redis persistence layer for trades/signals/calibration.
6. No production FastAPI service (server file is a stub).
7. No production scheduler/timers (cron module is a stub).
8. No full data pipeline sources (GDELT/FRED/Reddit/538/Dune/WebSocket).
9. No dashboard stack (Next.js/Supabase/Vercel) in this repo.
10. No calibration tracking (Brier score), training logger, or retraining loop.

## Should We Enable Agentic Workflow?

Yes, but in a constrained, testable way.

Recommendation:

- Enable a **deterministic agentic graph** (not open-ended autonomous agents).
- Use **LangGraph** (via LangChain ecosystem) for explicit state machine nodes.
- Keep strict guardrails: typed state, max hops, explicit stop conditions, risk gates before execution.

Rationale:

- You get extensibility (multiple data/tools/models) without losing control.
- Easier to debug and test than free-form agent loops.
- Fits your current architecture and existing prompt/rag components.

## Recommended Stack Decision

### Orchestration

- **LangGraph / LangChain** for graph orchestration and tool calling.
- Keep prompts in dedicated modules and enforce structured outputs (JSON schema / Pydantic).

### Model Gateway

- **LiteLLM** as provider abstraction and routing layer.
- Single API surface for Bedrock, OpenAI, DeepSeek, Groq, Ollama.

### Primary Model Provider

- **Bedrock-first** if your target remains AWS-hosted and EU-compliance focused.
- Use direct OpenAI only as fallback path, not primary.

Decision matrix:

1. If infra is AWS + regional compliance matters: Bedrock primary.
2. If fastest time-to-quality with minimal infra complexity: OpenAI primary (temporary), then migrate to LiteLLM.
3. If cost-sensitive high-volume screening: add Ollama local as first-pass model.

Given your stated architecture goals, the best fit is:

- **LangGraph + LiteLLM + Bedrock primary + OpenAI fallback + optional Ollama screening**.

## Proposed Agentic Graph (Phase 1)

Use this minimal graph first:

1. `collect_markets`
2. `retrieve_context` (RAG + news/Tavily)
3. `forecast` (single analyst model)
4. `risk_gate` (volume/liquidity/price/risk limits)
5. `size_position`
6. `execute_or_dry_run`
7. `persist_run`

Do **not** add multi-agent debate until this baseline is stable and measured.

## Tavily Integration Recommendation

Replace demo-only connector with production pattern:

1. `search(topic="news", search_depth="advanced", max_results=...)`
2. Post-filter by relevance score and trusted domains
3. `extract(urls=..., query=market question, chunks_per_source=2-3)`
4. Deduplicate + summarize into bounded context block per market
5. Cache results by `(market_id, hour_bucket)` to control cost/latency

## Implementation Roadmap (Pragmatic)

### Step 1: Production Foundations

- Add `LLMClient` abstraction (current OpenAI + future LiteLLM backend).
- Add run persistence table(s): runs, candidates, decisions, executions.
- Add FastAPI endpoints: `/health`, `/runs`, `/trades`, `/positions`.

### Step 2: LiteLLM + Bedrock

- Introduce LiteLLM config with model tiers (`screening`, `analysis`, `decision`).
- Switch `Executor` to use LiteLLM router calls.
- Add fallback chain and timeout/retry budgets.

### Step 3: Agentic Graph + Tavily

- Move pipeline into LangGraph nodes with typed state.
- Integrate Tavily search/extract in context node.
- Add hard risk gate node before execution.

### Step 4: Multi-Agent Debate (Only After Metrics)

- Add bull/bear/aggregator nodes.
- Add confidence agreement + escalation logic.
- Track calibration and P&L deltas vs single-model baseline.

## Guardrails to Require Before Expanding Autonomy

1. Hard limits: max daily loss, max per-market exposure, max category concentration.
2. Circuit breaker on execution failures and latency spikes.
3. Idempotency keys for order placement and run-level locking.
4. Structured logging for every decision edge.
5. Replayable run artifacts for post-mortems.

## Success Criteria

Phase-1 implementation is successful when:

1. Same market set yields deterministic decisions under fixed inputs.
2. All trade actions are reproducible from persisted run artifacts.
3. Dry-run vs live-run differ only at execution node.
4. Risk gates reject unsafe candidates before any order call.
5. Calibration and P&L metrics are queryable via API.

