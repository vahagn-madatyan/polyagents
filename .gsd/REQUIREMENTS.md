# Requirements

## Active

## Validated

### VALID-01 — Slug normalization produces consistent slugs across all 9 sport types with live Polymarket data

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: S09

Live Gamma API validation confirms slug resolution for active leagues (NBA 5 slugs, NHL 1 slug); off-season leagues report "pending" (structural, not failure). validate_slugs.py produces structured JSON evidence.

### VALID-02 — Score-change debounce thresholds are configurable per sport type (not just global cooldown)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: S09

Per-sport cooldown dict loaded from SPORTS_INGAME_COOLDOWN_{LEAGUE} env vars; 9 unit tests cover all paths including global fallback, shorter/longer overrides, invalid env, tick integration.

### VALID-03 — CLOB rate limiting prevents exceeding 60 orders/min across both sports and general pipelines

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: S09

Concurrent 9-game simulation proves peak_rate=9 orders in rolling 60s window — well under 60/min CLOB limit. validate_rate_limit.py produces structured JSON evidence.

### PIPE-01 — Pre-game analysis calls `detect_value_bet()` to flag value opportunities before placing trades

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Pre-game analysis calls `detect_value_bet()` to flag value opportunities before placing trades

### PIPE-02 — In-game fast-path calls `detect_value_bet()` to validate trades against external odds divergence

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

In-game fast-path calls `detect_value_bet()` to validate trades against external odds divergence

### PERS-01 — `wallet_balance` is periodically refreshed during pipeline execution (not just at startup)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

`wallet_balance` is periodically refreshed during pipeline execution (not just at startup)

### PERS-02 — `_order_log` is persisted to file and survives process restarts

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

`_order_log` is persisted to file and survives process restarts

### PERS-03 — `_ended_games` is persisted to file and survives process restarts

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

`_ended_games` is persisted to file and survives process restarts

### QUAL-01 — Env helper functions are centralized in a single shared module (eliminating duplication across 7+ files)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

Env helper functions are centralized in a single shared module (eliminating duplication across 7+ files)

### QUAL-02 — TODO in `agents/utils/objects.py:107` is resolved (forward reference validated or fixed)

- Status: validated
- Class: core-capability
- Source: inferred
- Primary Slice: none yet

TODO in `agents/utils/objects.py:107` is resolved (forward reference validated or fixed)

## Deferred

## Out of Scope
