# Phase 9: Live Validation - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Validate the sports pipeline under real Polymarket conditions by confirming slug normalization across all 9 supported sports, tuning score-change debounce behavior per sport type, and proving the combined sports + general pipelines stay safely under the shared CLOB order-rate ceiling.

</domain>

<decisions>
## Implementation Decisions

### Validation Safety Mode
- Default to observe-first validation: dry-run is the baseline for live windows, and real execution should be used only when a requirement truly needs it.
- When live execution is necessary during validation, use the minimum practical live order size rather than normal production sizing.
- Concurrent sports + general pipeline validation should stay below the 60 orders/minute ceiling with margin; do not intentionally probe the cap.
- If a live validation window becomes noisy, unsafe, or otherwise degrades mid-run, immediately drop to dry-run-only and continue collecting evidence instead of continuing live orders.

### Evidence and Completion Standard
- Phase 9 is not complete until all 9 supported sports are validated against real live Polymarket windows; a representative subset is not enough.
- If a sport does not have a suitable live market during the validation window, keep the phase open rather than closing it with partial coverage.
- Each validation run should produce a structured pass/fail report with observed conditions and captured evidence; short summary-only signoff is not sufficient.
- VALID-03 requires one clean concurrent sports + general pipeline run with captured order-count evidence and clear margin under the cap; repeated or near-limit stress runs are not required.

### Debounce Tuning Posture
- Tune debounce thresholds per sport type, not as one shared global cooldown.
- Use a conservative tuning bias: prefer fewer, cleaner in-game reactions over maximum responsiveness.
- If some sports receive the shortest debounce despite the conservative posture, that responsiveness should be reserved for low-scoring swing sports where a single score materially changes the game state.
- Near-resolution and other high-leverage late-game situations should become more cautious, not more aggressive.

### Claude's Discretion
- Exact structure of the validation report and evidence artifacts.
- Order in which the 9 sports are scheduled for live validation windows.
- Specific per-sport debounce values and how they are represented in configuration.
- Instrumentation details for counting concurrent orders, provided the output supports the required structured signoff.

</decisions>

<specifics>
## Specific Ideas

- "Observe first" is the default posture for the whole phase; live execution is a narrow exception, not the baseline.
- If live conditions degrade, keep the run useful by switching to dry-run evidence gathering instead of forcing a risky continuation.
- Completion should wait for all 9 sports rather than accepting partial or proxy coverage.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GammaMarketClient` in `agents/polymarket/gamma.py`: already provides slug lookup, fallback lookup, retry, and slug-table build paths that can be exercised and observed against live Polymarket data for VALID-01.
- `InGameTrader` in `agents/application/ingame_trader.py`: already has score-change classification, cooldown gating, near-resolution heuristics, and fast/slow-path routing that Phase 9 can tune and validate for VALID-02.
- `BudgetCoordinator` in `agents/application/budget.py`: already centralizes shared sports budget state and wallet refresh behavior, which gives Phase 9 a natural place to observe cross-pipeline spend/rate behavior.
- `agents/sports.py`: already wires websocket intake, slug refresh, pre-game analysis, and in-game trading together in the production loop, making it the natural live-validation entry point.
- Existing regression suites in `tests/test_sports_market_discovery.py`, `tests/test_ingame_trader.py`, `tests/test_sports_pipeline.py`, and `tests/test_budget_coordinator.py` provide a strong safety net around any validation instrumentation or debounce configuration changes.

### Established Patterns
- Structured logging uses `[component] event=... key=value` prints throughout the sports pipeline; Phase 9 evidence capture should extend that pattern rather than inventing a separate reporting style.
- Dry-run and live behavior are already gated through `SPORTS_EXECUTE_TRADES` / `EXECUTE_TRADES`, which supports the chosen observe-first posture.
- Slug resolution already follows exact lookup -> fallback search -> retry of unmapped slugs; live validation should measure and document how that behaves across real sports windows.
- Current in-game debounce behavior is global (`SPORTS_INGAME_COOLDOWN_SECONDS`) plus near-resolution heuristics; Phase 9 should preserve those safety concepts while making the thresholds sport-specific.

### Integration Points
- `agents/sports.py`: live validation runs, slug refresh loop, and concurrent pipeline coordination.
- `agents/polymarket/gamma.py`: live slug normalization evidence and unmapped-slug reporting.
- `agents/application/ingame_trader.py`: per-sport debounce configuration and late-game caution behavior.
- `agents/application/budget.py` plus the existing sports/general execution paths: shared-rate observation for VALID-03 evidence.

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 09-live-validation*
*Context gathered: 2026-03-14*
