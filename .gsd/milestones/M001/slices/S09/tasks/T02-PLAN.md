# T02: 09-live-validation 02

**Slice:** S09 — **Milestone:** M001

## Description

Create live validation scripts for slug normalization (VALID-01) and concurrent CLOB rate limit compliance (VALID-03).

Purpose: VALID-01 requires evidence that slug normalization works for all 9 sport types against live Polymarket data. VALID-03 requires evidence that concurrent sports + general pipelines stay under 60 orders/min. Both produce structured JSON reports per CONTEXT.md evidence standard.

Output: Two standalone scripts in `scripts/python/` that exercise the production pipeline in observe-first mode and emit structured pass/fail JSON reports.

## Must-Haves

- [ ] "A validation script can exercise the full slug resolution pipeline against live Polymarket data and produce a structured JSON report per sport"
- [ ] "A validation script can run both sports and general pipelines concurrently, count order-rate log events, and produce a structured JSON report proving the system stays under 60 orders/min"
- [ ] "Sports with no live game during the validation window are tracked as pending (not failed) and the phase stays open per CONTEXT.md"

## Files

- `scripts/python/validate_slugs.py`
- `scripts/python/validate_rate_limit.py`
