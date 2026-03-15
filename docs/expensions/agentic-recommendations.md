# Agentic Recommendations

## Short answer
- Yes, LangChain supports fully agentic setups.
- LiteLLM is best used as a model gateway/router, not your primary agent runtime.
- For this trading system, a hybrid approach is better than making everything fully agentic.

## Recommendation
Use:
- **LangChain + LangGraph** for orchestration (agent loops where needed).
- **AWS Bedrock** as the model provider (`ChatBedrockConverse`).
- **LangSmith** for tracing and evaluation.
- **LiteLLM** only if we need multi-provider routing/fallback/cost controls.

## Why this is better for this repo
Current pipeline has deterministic, high-stakes parts (allocation, risk checks, order execution).  
Those should remain deterministic and policy-guarded.

Agentic behavior should be introduced where it helps most:
- news research and synthesis
- hypothesis generation
- counter-case and risk-factor exploration
- tool-using analysis loops

## Proposed architecture
1. **Deterministic core (keep)**
- market filtering
- budget/allocation math
- execution gating and order placement

2. **Agentic analysis layer (add)**
- planner/researcher agent for market context
- optional critic agent for counter-case and edge validation
- bounded tool loops (news/search/RAG) with max turns

3. **Execution gate (strict)**
- schema-validated output only
- confidence threshold + liquidity threshold + price-band checks
- optional human approval when `EXECUTE_TRADES=true`

## Migration plan (phased)
1. **Phase 1: Observability first**
- enable LangSmith tracing and capture baseline runs
- define metrics (hit rate, slippage, drawdown, latency, token spend)

2. **Phase 2: Agentic analysis only**
- replace single-shot analysis prompts with a bounded LangGraph node flow
- keep trade sizing/execution unchanged

3. **Phase 3: Controlled autonomy**
- add policy-based auto-execution only when guardrails pass
- keep manual override path for all live trades

## Guardrails to require before live agentic execution
- Max tool iterations and timeout per market
- Strict JSON schema for decision output
- Hard caps on exposure per market/day
- Kill-switch env flag for immediate stop
- Full trace logging and decision audit records

## Decision framework
- If goal is reliability now: use **LangChain + Bedrock + LangSmith**, no LiteLLM yet.
- If goal is provider routing/failover: add **LiteLLM** behind LangChain later.
- Do not convert execution logic to open-ended agent loops.
