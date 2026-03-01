import { useState } from "react";

const PHASES = [
  {
    id: 1, weeks: "1-3", title: "Foundation",
    color: "#ef4444",
    goal: "Fork repo, replace OpenAI with LiteLLM+Bedrock, deploy to EU, first trade",
    tasks: [
      { name: "Fork Polymarket/agents, setup dev env", priority: "CRITICAL" },
      { name: "Docker Compose (PG + Redis + ChromaDB + Ollama + LiteLLM)", priority: "CRITICAL" },
      { name: "Request Bedrock model access (Claude, Llama, Mistral) in eu-west-1", priority: "CRITICAL" },
      { name: "Replace OpenAI → LiteLLM with Bedrock-first routing", priority: "CRITICAL" },
      { name: "Pull Ollama models (Qwen3-8B, Mistral-7B)", priority: "CRITICAL" },
      { name: "Deploy EC2 c6a.xlarge eu-west-1 + Elastic IP + IAM role", priority: "CRITICAL" },
      { name: "Verify geo-compliance (all reqs from Irish IP)", priority: "CRITICAL" },
      { name: "Systemd timers for 4-hour analysis cycle", priority: "HIGH" },
      { name: "Telegram notifications (trades + errors)", priority: "HIGH" },
      { name: "PostgreSQL schema (replace in-memory state)", priority: "HIGH" },
      { name: "First paper trade → first live trade", priority: "HIGH" },
    ],
    deliverable: "Bot running 24/7 in Ireland via Bedrock Claude Haiku + local Qwen3 + OpenAI/DeepSeek/Groq fallbacks"
  },
  {
    id: 2, weeks: "4-6", title: "Data Pipeline",
    color: "#f97316",
    goal: "Feed the bot vastly richer context than raw Gamma API + NewsAPI",
    tasks: [
      { name: "GDELT news collector (15-min, tone scores)", priority: "CRITICAL" },
      { name: "FRED economic data (8 key series, daily)", priority: "HIGH" },
      { name: "Reddit/PRAW sentiment (8 subreddits, hourly)", priority: "HIGH" },
      { name: "FiveThirtyEight polling (political markets)", priority: "HIGH" },
      { name: "Dune on-chain whale tracking (4-hourly)", priority: "MEDIUM" },
      { name: "Polymarket WebSocket real-time prices", priority: "HIGH" },
      { name: "Context builder (per-market dossiers)", priority: "CRITICAL" },
      { name: "News deduplicator (TF-IDF similarity)", priority: "MEDIUM" },
      { name: "Sentiment aggregator (VADER + GDELT tone)", priority: "MEDIUM" },
      { name: "Resolution source monitor", priority: "MEDIUM" },
      { name: "ChromaDB: index all new data sources", priority: "HIGH" },
      { name: "RAG competence filter (only trade what we know)", priority: "HIGH" },
    ],
    deliverable: "7 data sources feeding ChromaDB + context builder. Rich dossiers before AI analysis."
  },
  {
    id: 3, weeks: "7-9", title: "AI Debate",
    color: "#eab308",
    goal: "Multi-agent debate with superforecaster calibration replaces single-model",
    tasks: [
      { name: "Bull agent (Ollama/Qwen — argues YES)", priority: "CRITICAL" },
      { name: "Bear agent (Bedrock/Llama — argues NO)", priority: "CRITICAL" },
      { name: "Aggregator (Bedrock/Claude Haiku — synthesizes)", priority: "CRITICAL" },
      { name: "Superforecaster calibration layer (Tetlock base rates)", priority: "HIGH" },
      { name: "Escalation: Haiku → Bedrock/Sonnet for edge >15pp", priority: "HIGH" },
      { name: "Multi-model diversity (Qwen vs Llama vs Claude)", priority: "HIGH" },
      { name: "Confidence scoring (LLM + agent agreement)", priority: "HIGH" },
      { name: "LangSmith observability (trace all LLM calls)", priority: "MEDIUM" },
      { name: "Prompt versioning + A/B testing", priority: "MEDIUM" },
      { name: "Batch analysis (top 20 markets in parallel)", priority: "MEDIUM" },
    ],
    deliverable: "Multi-agent debate producing calibrated probabilities with full LLM observability"
  },
  {
    id: 4, weeks: "10-12", title: "Risk & Execution",
    color: "#22c55e",
    goal: "Only highest-quality signals survive. Kelly-sized positions with hard limits.",
    tasks: [
      { name: "Edge detector (|p_model - p_market| > threshold)", priority: "CRITICAL" },
      { name: "Liquidity filter ($5K min orderbook depth)", priority: "CRITICAL" },
      { name: "Time-to-resolution filter (<24h / >6mo)", priority: "HIGH" },
      { name: "Correlation guard (max 3 per category)", priority: "HIGH" },
      { name: "Confidence gate (≥7/10 AND ≥2/3 agents)", priority: "HIGH" },
      { name: "Kelly criterion (25% fractional Kelly)", priority: "CRITICAL" },
      { name: "Portfolio risk engine (10% max single, 40% total)", priority: "CRITICAL" },
      { name: "Daily loss circuit breaker (5% stop)", priority: "CRITICAL" },
      { name: "Paper trade gate (30 days for new strategies)", priority: "HIGH" },
      { name: "Smart order router (slippage protection)", priority: "HIGH" },
      { name: "WebSocket fill monitor (real-time confirms)", priority: "HIGH" },
      { name: "Exit manager (TP/SL/time-based exits)", priority: "HIGH" },
    ],
    deliverable: "Production-grade risk management. ~80% signals filtered. Kelly-sized positions."
  },
  {
    id: 5, weeks: "13-15", title: "Monitoring + API",
    color: "#3b82f6",
    goal: "Complete observability, REST API for dashboard, training data logging",
    tasks: [
      { name: "Position tracker (live portfolio, 5-min refresh)", priority: "CRITICAL" },
      { name: "FastAPI REST endpoints (/portfolio, /trades, /signals, /calibration, /config)", priority: "CRITICAL" },
      { name: "API auth middleware (API key + Supabase JWT)", priority: "HIGH" },
      { name: "Calibration monitor (Brier score tracking)", priority: "HIGH" },
      { name: "Training data logger (S3 JSONL)", priority: "HIGH" },
      { name: "Telegram daily summary", priority: "HIGH" },
      { name: "Error alerting (API failures, order rejects)", priority: "HIGH" },
      { name: "Model cost metrics (via LiteLLM DB)", priority: "MEDIUM" },
      { name: "Threshold auto-tuner (backtest-driven)", priority: "MEDIUM" },
      { name: "Market resolution tracker", priority: "HIGH" },
      { name: "Weekly calibration report (Telegram)", priority: "MEDIUM" },
    ],
    deliverable: "Full REST API serving bot data. Every prediction tracked. Ready for dashboard."
  },
  {
    id: 6, weeks: "14-17", title: "Dashboard",
    color: "#06b6d4",
    goal: "Next.js + TypeScript visual interface on Vercel — portfolio, trades, calibration",
    tasks: [
      { name: "Next.js project (TypeScript + Tailwind + shadcn/ui)", priority: "CRITICAL" },
      { name: "Type-safe API client matching FastAPI schemas", priority: "CRITICAL" },
      { name: "Portfolio page (positions, P&L, exposure %)", priority: "CRITICAL" },
      { name: "Trade history page (table + AI reasoning)", priority: "HIGH" },
      { name: "Signal log page (edge, pass/reject + why)", priority: "HIGH" },
      { name: "Calibration page (Brier score + curve chart)", priority: "HIGH" },
      { name: "Market scanner page (bot watchlist)", priority: "HIGH" },
      { name: "LLM metrics page (cost, tokens, latency)", priority: "MEDIUM" },
      { name: "Config panel (thresholds, risk limits)", priority: "MEDIUM" },
      { name: "SSE real-time updates from FastAPI", priority: "MEDIUM" },
      { name: "Supabase Auth (→ multi-user SaaS later)", priority: "HIGH" },
      { name: "Deploy to Vercel", priority: "HIGH" },
    ],
    deliverable: "Production dashboard on Vercel. Template for future SaaS multi-user version."
  },
  {
    id: 7, weeks: "18-22", title: "Model Training",
    color: "#8b5cf6",
    goal: "Self-improving models trained on accumulated prediction data",
    tasks: [
      { name: "Training data builder (S3 → train/val/test)", priority: "CRITICAL" },
      { name: "Spot GPU provisioning (g4dn.xlarge)", priority: "CRITICAL" },
      { name: "QLoRA fine-tune Qwen3-8B", priority: "HIGH" },
      { name: "Eval harness (fine-tuned vs base)", priority: "HIGH" },
      { name: "Sentiment fine-tune (FinGPT)", priority: "HIGH" },
      { name: "Deploy to Ollama on EC2", priority: "HIGH" },
      { name: "A/B testing (compare Brier scores)", priority: "MEDIUM" },
      { name: "Monthly retraining cron", priority: "MEDIUM" },
      { name: "Bedrock custom model import", priority: "MEDIUM" },
      { name: "RLHF from market outcomes", priority: "LOW" },
      { name: "Distill Sonnet → local model", priority: "LOW" },
    ],
    deliverable: "Self-improving models. Fine-tuned local replaces expensive cloud APIs."
  },
];

const STACK_COMPONENTS = [
  {
    category: "Infrastructure",
    items: [
      { name: "AWS EC2 c6a.xlarge", detail: "eu-west-1, Elastic IP, IAM Role (BedrockFullAccess)", cost: "~$45/mo spot", why: "Irish IP for geo-compliance. IAM role = no Bedrock API keys." },
      { name: "Ubuntu 24.04 + Docker", detail: "All services containerized via Docker Compose", cost: "Included", why: "Not Fargate — 3.2x cheaper + Ollama needs persistent storage." },
      { name: "S3 (eu-west-1)", detail: "Training data, snapshots, backtest archives", cost: "~$1/mo", why: "Durable ML storage, same region as compute." },
      { name: "Vercel", detail: "Dashboard hosting, auto-deploy from GitHub", cost: "$0 (free)", why: "Global edge CDN. Becomes paid only at SaaS scale." },
    ]
  },
  {
    category: "LLM Gateway — Bedrock Primary",
    items: [
      { name: "LiteLLM Router", detail: "Bedrock → OpenAI → DeepSeek → Groq → Ollama", cost: "Free (OSS)", why: "One API for all providers. Auto-fallback, cost tracking, caching." },
      { name: "AWS Bedrock (primary)", detail: "Claude Haiku/Sonnet + Llama 3.3 70B — same-region, IAM", cost: "$5-25/mo", why: "~5-15ms latency. Single bill. EU data residency. No API keys." },
      { name: "OpenAI (fallback)", detail: "GPT-4o + GPT-4o-mini — AWS outage safety net", cost: "$0-5/mo", why: "External fallback for highest quality decisions." },
      { name: "DeepSeek (overflow)", detail: "V3 at $0.28/M tokens", cost: "$0-3/mo", why: "10-30x cheaper than competitors." },
      { name: "Groq (burst)", detail: "Llama-3.3-70B free tier, 276 tok/sec", cost: "$0", why: "Free burst for screening overflow." },
      { name: "Ollama (local)", detail: "Qwen3-8B, Mistral-7B, FinGPT on EC2", cost: "$0", why: "Free screening + model diversity for debate." },
    ]
  },
  {
    category: "Data Layer",
    items: [
      { name: "PostgreSQL 16", detail: "Trades, signals, calibration — shared with dashboard", cost: "$0 (Docker)", why: "ACID, JSON columns. Bot writes, dashboard reads." },
      { name: "ChromaDB", detail: "Vector store: 7 data sources indexed", cost: "$0 (Docker)", why: "RAG competence filtering across all sources." },
      { name: "Redis", detail: "LLM cache, rate limiting, pub/sub", cost: "$0 (Docker)", why: "LiteLLM Redis cache avoids duplicate LLM calls." },
    ]
  },
  {
    category: "Data Sources (all free)",
    items: [
      { name: "Polymarket CLOB + Gamma", detail: "Prices, orderbooks, WebSocket feed", cost: "$0", why: "Primary market data" },
      { name: "GDELT", detail: "15-min news, tone scores, geo metadata", cost: "$0", why: "Structured sentiment, not just headlines" },
      { name: "FRED", detail: "840K+ economic time series", cost: "$0", why: "Macro context for economic markets" },
      { name: "Reddit/PRAW", detail: "r/politics, r/polymarket, r/worldnews", cost: "$0", why: "Retail sentiment for political markets" },
      { name: "FiveThirtyEight", detail: "Polling data (CSV)", cost: "$0", why: "Critical for political markets" },
      { name: "Dune Analytics", detail: "Whale wallets, on-chain volume", cost: "$0", why: "Smart money tracking" },
      { name: "Tavily Search", detail: "Real-time web search", cost: "$0", why: "Breaking news before GDELT indexes" },
    ]
  },
  {
    category: "Dashboard (TypeScript)",
    items: [
      { name: "Next.js 15", detail: "App Router + TypeScript + SSR", cost: "$0", why: "Aligns with TradeAgentAI SaaS stack." },
      { name: "Tailwind + shadcn/ui", detail: "Utility CSS + headless components", cost: "$0", why: "Production UI, dark mode built-in." },
      { name: "Recharts", detail: "P&L, calibration curves, exposure charts", cost: "$0", why: "React-native, composable." },
      { name: "Supabase Auth", detail: "Login → multi-user SaaS later", cost: "$0", why: "Prepares SaaS path without custom auth." },
    ]
  },
  {
    category: "Monitoring",
    items: [
      { name: "Telegram Bot", detail: "Alerts, daily P&L, weekly calibration", cost: "$0", why: "Instant mobile notifications." },
      { name: "LangSmith", detail: "LLM tracing: prompts, cost, latency", cost: "$0 (free)", why: "Debug predictions by replaying LLM chain." },
      { name: "LiteLLM Dashboard", detail: "Per-model cost, Bedrock spend tracking", cost: "Included", why: "Unified view across all providers." },
    ]
  },
];

const MODEL_ROUTING = [
  { stage: "Market screening", primary: "Ollama/Qwen3-8B", fallback: "Bedrock/Llama-3.3-70B", fb2: "Groq (free)", reason: "High volume, local = free", tier: "screening" },
  { stage: "RAG filtering", primary: "Ollama/Qwen3-8B", fallback: "Bedrock/Llama", fb2: "—", reason: "Simple relevance check", tier: "screening" },
  { stage: "Bull agent", primary: "Ollama/Qwen3-14B", fallback: "DeepSeek-Chat", fb2: "—", reason: "Qwen family = different bias", tier: "debate" },
  { stage: "Bear agent", primary: "Bedrock/Llama-3.3-70B", fallback: "Groq/Llama", fb2: "Ollama/Mistral", reason: "Different model = disagreement", tier: "debate" },
  { stage: "Aggregator", primary: "Bedrock/Claude Haiku", fallback: "DeepSeek-Chat", fb2: "OpenAI/4o-mini", reason: "Calibrated reasoning, same-region", tier: "analysis" },
  { stage: "Superforecaster", primary: "Bedrock/Claude Haiku", fallback: "OpenAI/GPT-4o-mini", fb2: "—", reason: "Tetlock needs instruction-following", tier: "analysis" },
  { stage: "High-edge", primary: "Bedrock/Claude Sonnet 4", fallback: "OpenAI/GPT-4o", fb2: "—", reason: "Best reasoning for >$100 decisions", tier: "decision" },
  { stage: "Sentiment", primary: "Ollama/FinGPT (tuned)", fallback: "Bedrock/Claude Haiku", fb2: "—", reason: "Specialized local, zero cost", tier: "specialized" },
  { stage: "Exit decisions", primary: "Bedrock/Claude Haiku", fallback: "Ollama/Qwen3", fb2: "—", reason: "Quick, moderate quality", tier: "analysis" },
];

const TIER_COLORS = { screening: "#22c55e", debate: "#f97316", analysis: "#3b82f6", decision: "#8b5cf6", specialized: "#ec4899" };

function App() {
  const [activeView, setActiveView] = useState("overview");
  const [expandedPhase, setExpandedPhase] = useState(null);
  const [expandedStack, setExpandedStack] = useState(null);
  const totalTasks = PHASES.reduce((sum, p) => sum + p.tasks.length, 0);
  const criticalTasks = PHASES.reduce((sum, p) => sum + p.tasks.filter(t => t.priority === "CRITICAL").length, 0);

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, sans-serif", background: "#0a0a0f", color: "#e2e8f0", minHeight: "100vh", padding: "24px" }}>
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "12px", marginBottom: "8px" }}>
          <div style={{ background: "linear-gradient(135deg, #f97316, #8b5cf6)", padding: "8px 12px", borderRadius: "8px", fontSize: "20px" }}>🧬</div>
          <div>
            <h1 style={{ margin: 0, fontSize: "24px", fontWeight: 700, background: "linear-gradient(to right, #f97316, #8b5cf6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>Polymarket/agents Extended</h1>
            <p style={{ margin: 0, fontSize: "13px", color: "#94a3b8" }}>v2 — Bedrock-First · Python Bot + TypeScript Dashboard · EU-Compliant · Self-Training</p>
          </div>
        </div>
        <div style={{ display: "flex", gap: "12px", flexWrap: "wrap", marginTop: "16px" }}>
          {[
            { label: "Monthly Cost", value: "$65-90", sub: "of $200 budget" },
            { label: "Phases", value: "7", sub: "22 weeks total" },
            { label: "Total Tasks", value: totalTasks.toString(), sub: `${criticalTasks} critical` },
            { label: "Primary LLM", value: "Bedrock", sub: "same-region IAM" },
            { label: "Data Sources", value: "7", sub: "all free tier" },
            { label: "Region", value: "eu-west-1", sub: "Irish Elastic IP" },
            { label: "Bot", value: "Python", sub: "forked base repo" },
            { label: "Dashboard", value: "Next.js", sub: "TypeScript/Vercel" },
          ].map((s, i) => (
            <div key={i} style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "8px", padding: "8px 12px", minWidth: "100px" }}>
              <div style={{ fontSize: "16px", fontWeight: 700, color: "#f1f5f9" }}>{s.value}</div>
              <div style={{ fontSize: "10px", color: "#64748b" }}>{s.label}</div>
              <div style={{ fontSize: "9px", color: "#475569" }}>{s.sub}</div>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", gap: "6px", marginBottom: "20px", flexWrap: "wrap" }}>
        {[
          { id: "overview", label: "🏗️ Architecture" },
          { id: "phases", label: "📋 Phases (7)" },
          { id: "routing", label: "🤖 LLM Routing" },
          { id: "stack", label: "🔧 Full Stack" },
        ].map(v => (
          <button key={v.id} onClick={() => setActiveView(v.id)} style={{
            padding: "8px 16px", borderRadius: "6px", border: "none", cursor: "pointer", fontSize: "13px", fontWeight: 600,
            background: activeView === v.id ? "linear-gradient(135deg, #f97316, #8b5cf6)" : "#1e293b",
            color: activeView === v.id ? "#fff" : "#94a3b8",
          }}>{v.label}</button>
        ))}
      </div>

      {activeView === "overview" && (
        <div>
          <div style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "12px", padding: "20px", marginBottom: "16px" }}>
            <h3 style={{ margin: "0 0 4px", fontSize: "15px", color: "#f97316" }}>Bedrock-First · Python Bot + TypeScript Dashboard</h3>
            <p style={{ margin: 0, fontSize: "13px", color: "#94a3b8", lineHeight: 1.6 }}>
              Fork Polymarket/agents (ChromaDB RAG, superforecaster, py-clob-client). Route paid LLM inference through <strong style={{color:"#f97316"}}>AWS Bedrock</strong> (same-region, IAM auth, single bill, EU data residency). Fallback: OpenAI → DeepSeek → Groq. Free local inference via Ollama. Dashboard in Next.js/TypeScript on Vercel.
            </p>
          </div>
          <div style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "12px", padding: "16px", fontFamily: "monospace", fontSize: "10px", lineHeight: 1.4, overflowX: "auto" }}>
            <pre style={{ margin: 0, color: "#94a3b8" }}>{`┌───────── AWS EC2 c6a.xlarge · eu-west-1 · $45/mo spot ─────────────────────────┐
│ Elastic IP (Irish) · IAM: BedrockFullAccess · Docker Compose                    │
│                                                                                  │
│ ┌─── POLYMARKET/AGENTS (forked, Python) ──────────────────────────────────────┐  │
│ │ GammaClient · CLOB Trading · ChromaDB RAG · Superforecaster · LangGraph    │  │
│ └────────────────────────┬────────────────────────────────────────────────────┘  │
│                           │ extended with ↓                                      │
│ ┌────────────┐ ┌─────────┐ ┌────────┐ ┌────────┐ ┌──────────────────────────┐   │
│ │  LiteLLM   │ │ 7 Data  │ │ Signal │ │ Risk & │ │ Monitoring + FastAPI     │   │
│ │  Gateway   │ │ Collect │ │ Filter │ │ Kelly  │ │ /portfolio /trades       │   │
│ │            │ │         │ │        │ │ Sizing │ │ /signals /calibration    │   │
│ │ PRIMARY:   │ │ GDELT   │ │ Edge   │ │ Paper  │ │ /models /config         │   │
│ │  Bedrock   │ │ FRED    │ │ Liquid │ │ Trade  │ │                          │   │
│ │  (Claude,  │ │ Reddit  │ │ Time   │ │ Gate   │ │ Telegram · Calibration  │   │
│ │   Llama)   │ │ 538     │ │ Corr   │ │ Breaker│ │ S3 Training Logger      │   │
│ │ FALLBACK:  │ │ Dune    │ │ Conf   │ │        │ │                          │   │
│ │  OpenAI    │ │ Tavily  │ │        │ │        │ │                          │   │
│ │  DeepSeek  │ │ WSocket │ │ ~80%   │ │ Max10% │ │                          │   │
│ │  Groq      │ │         │ │ reject │ │ single │ │                          │   │
│ │ LOCAL:     │ │         │ │        │ │        │ │                          │   │
│ │  Ollama    │ │         │ │        │ │        │ │                          │   │
│ └────────────┘ └─────────┘ └────────┘ └────────┘ └────────────┬─────────────┘   │
│                                                                │                 │
│ ┌─── Docker ──────────────────────────────────────────────────┐│                 │
│ │ Ollama (Qwen3-8B, Mistral) · ChromaDB · PostgreSQL · Redis ││                 │
│ └─────────────────────────────────────────────────────────────┘│                 │
│ ┌─── S3 ──────────────┐  ┌─── GPU spot (future) ────────────┐ │                 │
│ │ Training JSONL       │  │ g4dn.xlarge → QLoRA → weights    │ │                 │
│ └──────────────────────┘  └──────────────────────────────────┘ │                 │
└────────────────────────────────────────────────────────────────┘                 │
                                      │ HTTPS                                      │
                                      ▼                                            │
┌─── VERCEL ────────────────────────────────────────────────────────────────────┐  │
│ Next.js Dashboard (TypeScript + Tailwind + shadcn + Recharts)                 │  │
│ Portfolio · Trades · Signals · Calibration · Markets · LLM Metrics · Config   │  │
│ Auth: Supabase (single user → SaaS)                                           │  │
└───────────────────────────────────────────────────────────────────────────────┘`}</pre>
          </div>
          <div style={{ marginTop: "16px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
            <div style={{ background: "#12121a", border: "1px solid #22c55e33", borderRadius: "10px", padding: "16px" }}>
              <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#22c55e" }}>✅ Keep from base repo</h4>
              <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: "12px", color: "#94a3b8", lineHeight: 1.8 }}>
                <li>ChromaDB RAG (competence filtering)</li>
                <li>Superforecaster prompting (Tetlock)</li>
                <li>GammaMarketClient + py-clob-client</li>
                <li>LangGraph orchestration</li>
                <li>FastAPI (extended for dashboard)</li>
              </ul>
            </div>
            <div style={{ background: "#12121a", border: "1px solid #f9731633", borderRadius: "10px", padding: "16px" }}>
              <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#f97316" }}>🆕 Add / Replace</h4>
              <ul style={{ margin: 0, padding: "0 0 0 16px", fontSize: "12px", color: "#94a3b8", lineHeight: 1.8 }}>
                <li><strong style={{color:"#f97316"}}>Bedrock-first</strong> LiteLLM routing</li>
                <li>Ollama + multi-agent debate</li>
                <li>7 data collectors + enrichment</li>
                <li>Kelly + risk engine + signal filtering</li>
                <li><strong style={{color:"#06b6d4"}}>Next.js dashboard</strong> (TypeScript/Vercel)</li>
                <li>Monitoring + QLoRA training pipeline</li>
              </ul>
            </div>
          </div>
          <div style={{ marginTop: "12px", background: "#12121a", border: "1px solid #f9731633", borderRadius: "10px", padding: "16px" }}>
            <h4 style={{ margin: "0 0 8px", fontSize: "13px", color: "#f97316" }}>🔶 Why Bedrock Primary</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: "12px", fontSize: "11px", color: "#94a3b8" }}>
              <div><strong style={{color:"#f1f5f9"}}>Same-Region</strong><br/>~5-15ms vs ~100-200ms external</div>
              <div><strong style={{color:"#f1f5f9"}}>Single Bill</strong><br/>Compute + inference on one AWS invoice</div>
              <div><strong style={{color:"#f1f5f9"}}>EU Data</strong><br/>All inference stays in eu-west-1</div>
              <div><strong style={{color:"#f1f5f9"}}>IAM Auth</strong><br/>No API keys. EC2 role auto-detected.</div>
            </div>
          </div>
        </div>
      )}

      {activeView === "phases" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {PHASES.map(phase => (
            <div key={phase.id} style={{ background: "#12121a", border: `1px solid ${phase.color}33`, borderRadius: "10px", overflow: "hidden" }}>
              <div onClick={() => setExpandedPhase(expandedPhase === phase.id ? null : phase.id)} style={{ padding: "12px 16px", cursor: "pointer", display: "flex", alignItems: "center", gap: "12px" }}>
                <div style={{ background: phase.color, color: "#fff", width: "26px", height: "26px", borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "13px", fontWeight: 700, flexShrink: 0 }}>{phase.id}</div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: "8px" }}>
                    <span style={{ fontSize: "14px", fontWeight: 700, color: "#f1f5f9" }}>{phase.title}</span>
                    <span style={{ fontSize: "11px", color: "#64748b" }}>Weeks {phase.weeks}</span>
                  </div>
                  <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>{phase.goal}</div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>{phase.tasks.length}</span>
                  <span style={{ fontSize: "10px", color: phase.color, background: `${phase.color}15`, padding: "2px 8px", borderRadius: "4px" }}>{phase.tasks.filter(t => t.priority === "CRITICAL").length} crit</span>
                  <span style={{ color: "#475569", fontSize: "14px" }}>{expandedPhase === phase.id ? "▾" : "▸"}</span>
                </div>
              </div>
              {expandedPhase === phase.id && (
                <div style={{ padding: "0 16px 14px", borderTop: "1px solid #1e293b" }}>
                  <div style={{ display: "grid", gap: "3px", marginTop: "10px" }}>
                    {phase.tasks.map((task, i) => (
                      <div key={i} style={{ display: "flex", alignItems: "center", gap: "8px", padding: "5px 8px", borderRadius: "5px", background: "#0a0a0f" }}>
                        <span style={{ fontSize: "9px", fontWeight: 700, padding: "2px 6px", borderRadius: "3px", flexShrink: 0, background: task.priority === "CRITICAL" ? "#ef444420" : task.priority === "HIGH" ? "#f9731620" : "#64748b15", color: task.priority === "CRITICAL" ? "#ef4444" : task.priority === "HIGH" ? "#f97316" : "#64748b" }}>{task.priority}</span>
                        <span style={{ fontSize: "11.5px", color: "#cbd5e1" }}>{task.name}</span>
                      </div>
                    ))}
                  </div>
                  <div style={{ marginTop: "10px", padding: "8px 12px", background: `${phase.color}08`, border: `1px solid ${phase.color}20`, borderRadius: "6px" }}>
                    <span style={{ fontSize: "10px", fontWeight: 600, color: phase.color }}>DELIVERABLE: </span>
                    <span style={{ fontSize: "11px", color: "#94a3b8" }}>{phase.deliverable}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
          <div style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "10px", padding: "14px" }}>
            <h4 style={{ margin: "0 0 10px", fontSize: "12px", color: "#94a3b8" }}>Timeline (Phases 5-6 overlap)</h4>
            <div style={{ display: "flex", gap: "2px", height: "28px" }}>
              {PHASES.map(p => {
                const weeks = parseInt(p.weeks.split("-")[1]) - parseInt(p.weeks.split("-")[0]) + 1;
                return (<div key={p.id} style={{ flex: weeks, background: `${p.color}30`, border: `1px solid ${p.color}50`, borderRadius: "4px", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "9px", fontWeight: 600, color: p.color }}>P{p.id}</div>);
              })}
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "4px", fontSize: "9px", color: "#475569" }}><span>Week 1</span><span>Week 11</span><span>Week 22</span></div>
          </div>
        </div>
      )}

      {activeView === "routing" && (
        <div>
          <div style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "10px", padding: "16px", marginBottom: "16px" }}>
            <h3 style={{ margin: "0 0 8px", fontSize: "15px", color: "#f97316" }}>Bedrock-First LLM Routing via LiteLLM</h3>
            <p style={{ margin: 0, fontSize: "12px", color: "#94a3b8", lineHeight: 1.6 }}>
              <strong style={{color:"#f1f5f9"}}>Priority:</strong> Ollama (free) → Bedrock (same-region, IAM) → DeepSeek ($0.28/M) → Groq (free) → OpenAI (safety net). Identical <code style={{background:"#1e293b", padding:"1px 4px", borderRadius:"3px", fontSize:"11px"}}>router.acompletion()</code> syntax for all.
            </p>
          </div>
          <div style={{ display: "flex", gap: "8px", marginBottom: "12px", flexWrap: "wrap" }}>
            {Object.entries(TIER_COLORS).map(([tier, color]) => (
              <span key={tier} style={{ fontSize: "10px", padding: "3px 10px", borderRadius: "4px", background: `${color}15`, color, fontWeight: 600, textTransform: "capitalize" }}>{tier}</span>
            ))}
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: "5px" }}>
            {MODEL_ROUTING.map((r, i) => (
              <div key={i} style={{ background: "#12121a", border: `1px solid ${TIER_COLORS[r.tier]}20`, borderRadius: "8px", padding: "10px 12px", display: "grid", gridTemplateColumns: "110px 1fr 1fr 1fr 1.2fr", gap: "8px", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: "12px", fontWeight: 600, color: "#f1f5f9" }}>{r.stage}</div>
                  <span style={{ fontSize: "8px", padding: "1px 5px", borderRadius: "3px", background: `${TIER_COLORS[r.tier]}15`, color: TIER_COLORS[r.tier], fontWeight: 600 }}>{r.tier}</span>
                </div>
                <div><div style={{ fontSize: "9px", color: "#64748b" }}>PRIMARY</div><div style={{ fontSize: "11px", color: "#22c55e", fontWeight: 600 }}>{r.primary}</div></div>
                <div><div style={{ fontSize: "9px", color: "#64748b" }}>FALLBACK 1</div><div style={{ fontSize: "11px", color: "#f97316", fontWeight: 600 }}>{r.fallback}</div></div>
                <div><div style={{ fontSize: "9px", color: "#64748b" }}>FALLBACK 2</div><div style={{ fontSize: "11px", color: "#64748b" }}>{r.fb2}</div></div>
                <div style={{ fontSize: "10px", color: "#94a3b8" }}>{r.reason}</div>
              </div>
            ))}
          </div>
          <div style={{ marginTop: "16px", background: "#12121a", border: "1px solid #1e293b", borderRadius: "10px", padding: "16px" }}>
            <h4 style={{ margin: "0 0 8px", fontSize: "12px", color: "#94a3b8" }}>Bedrock uses IAM role — no API key needed</h4>
            <pre style={{ margin: 0, fontSize: "10.5px", color: "#94a3b8", fontFamily: "monospace", lineHeight: 1.6, background: "#0a0a0f", padding: "12px", borderRadius: "6px", overflow: "auto" }}>{`router = Router(model_list=config["model_list"])

# Screening → Ollama local, falls to Bedrock/Llama, then Groq:
resp = await router.acompletion(model="screening", messages=[...])

# Analysis → Bedrock/Claude Haiku (same-region, IAM), falls to DeepSeek:
resp = await router.acompletion(model="analysis", messages=[...])

# Decision → Bedrock/Claude Sonnet (same-region), falls to OpenAI/GPT-4o:
resp = await router.acompletion(model="decision", messages=[...])`}</pre>
          </div>
        </div>
      )}

      {activeView === "stack" && (
        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {STACK_COMPONENTS.map((cat, ci) => (
            <div key={ci} style={{ background: "#12121a", border: "1px solid #1e293b", borderRadius: "10px", overflow: "hidden" }}>
              <div onClick={() => setExpandedStack(expandedStack === ci ? null : ci)} style={{ padding: "10px 16px", cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: "13px", fontWeight: 700, color: "#f1f5f9" }}>{cat.category}</span>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <span style={{ fontSize: "11px", color: "#64748b" }}>{cat.items.length}</span>
                  <span style={{ color: "#475569" }}>{expandedStack === ci ? "▾" : "▸"}</span>
                </div>
              </div>
              {expandedStack === ci && (
                <div style={{ padding: "0 16px 10px" }}>
                  {cat.items.map((item, ii) => (
                    <div key={ii} style={{ padding: "8px 10px", borderTop: "1px solid #1e293b" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
                        <span style={{ fontSize: "12px", fontWeight: 600, color: "#f1f5f9" }}>{item.name}</span>
                        <span style={{ fontSize: "11px", color: "#22c55e", fontWeight: 600 }}>{item.cost}</span>
                      </div>
                      <div style={{ fontSize: "11px", color: "#94a3b8", marginTop: "2px" }}>{item.detail}</div>
                      <div style={{ fontSize: "10px", color: "#64748b", marginTop: "3px", fontStyle: "italic" }}>Why: {item.why}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          <div style={{ background: "#12121a", border: "1px solid #22c55e33", borderRadius: "10px", padding: "16px" }}>
            <h4 style={{ margin: "0 0 10px", fontSize: "13px", color: "#22c55e" }}>Monthly Cost</h4>
            <div style={{ display: "grid", gridTemplateColumns: "1fr auto", gap: "3px 16px", fontSize: "11px" }}>
              {[
                ["EC2 c6a.xlarge spot (Ireland)", "$45"], ["EBS 100GB gp3", "$8"], ["S3 training data", "$1"],
                ["Bedrock Claude Haiku (~300/day)", "$3-8"], ["Bedrock Claude Sonnet (~50/day)", "$5-15"],
                ["Bedrock Llama 3.3 70B (debate)", "$1-3"], ["OpenAI GPT-4o (fallback)", "$0-5"],
                ["DeepSeek V3 (overflow)", "$0-3"], ["Groq free tier", "$0"],
                ["Ollama local", "$0"], ["7 data sources", "$0"], ["Vercel dashboard", "$0"], ["Telegram", "$0"],
              ].map(([n, c], i) => (<div key={i} style={{ display: "contents" }}><span style={{ color: "#94a3b8" }}>{n}</span><span style={{ color: "#f1f5f9", fontWeight: 600, textAlign: "right" }}>{c}</span></div>))}
              <div style={{ gridColumn: "1 / -1", borderTop: "1px solid #1e293b", margin: "4px 0" }} />
              <span style={{ color: "#22c55e", fontWeight: 700, fontSize: "13px" }}>TOTAL</span>
              <span style={{ color: "#22c55e", fontWeight: 700, fontSize: "13px", textAlign: "right" }}>$65-90/mo</span>
              <span style={{ color: "#64748b", fontSize: "10px" }}>Buffer remaining</span>
              <span style={{ color: "#64748b", fontSize: "10px", textAlign: "right" }}>$110-135</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
