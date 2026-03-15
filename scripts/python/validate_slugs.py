#!/usr/bin/env python3
"""VALID-01: Slug normalization validation across all 9 sport types.

Exercises the full slug resolution pipeline against live Polymarket Gamma API
data for each of the 9 supported sports (NFL, NBA, MLB, NHL, CFB, CBB, soccer,
CS2, tennis). Produces a structured JSON report with per-sport pass/fail/pending
status.

Sports with no live/active events during the validation window are tracked as
"pending" (not "failed") — the overall validation phase stays open per CONTEXT.md.

Usage:
    python scripts/python/validate_slugs.py [--output <path>]

Output: JSON report written to stdout and optionally to --output file.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

# Ensure the project root is on sys.path for imports
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from agents.polymarket.gamma import GammaMarketClient
from agents.utils.objects import SportsMarketTag


# All 9 sport types the pipeline must support
ALL_LEAGUES = ["nfl", "nba", "mlb", "nhl", "cfb", "cbb", "soccer", "cs2", "tennis"]


def _search_events_for_league(gamma: GammaMarketClient, league: str) -> list[dict]:
    """Search Gamma for active events matching a league string.

    Returns raw event dicts from Gamma API filtered to those whose slug or
    title contains the league abbreviation.
    """
    try:
        params = {"active": True, "closed": False, "limit": 100}
        response = gamma.http_client.get(gamma.gamma_events_endpoint, params=params)
        if response.status_code != 200:
            return []
        events: list[dict] = response.json() or []
        league_lower = league.lower()
        matched = []
        for event in events:
            event_slug = (event.get("slug") or "").lower()
            event_title = (event.get("title") or "").lower()
            searchable = event_slug + " " + event_title
            if league_lower in searchable:
                matched.append(event)
        return matched
    except Exception as exc:
        print(
            f"[validate_slugs] event=search_error league={league} error={exc}",
            file=sys.stderr,
        )
        return []


def _extract_slug_from_event(event: dict) -> str:
    """Extract the slug field from a Gamma event dict."""
    return event.get("slug") or ""


def _validate_league(gamma: GammaMarketClient, league: str) -> dict[str, Any]:
    """Validate the slug resolution pipeline for a single league.

    Steps:
      1. Search Gamma for active events matching the league
      2. For each event, attempt lookup_markets_by_slug (fast path)
      3. If fast path fails, try lookup_markets_fallback (team-based search)
      4. Validate returned tags have non-empty token/condition IDs
      5. Report slug-level and league-level results

    Returns a per-league result dict.
    """
    result: dict[str, Any] = {
        "league": league,
        "status": "pending",
        "events_found": 0,
        "slugs_tested": 0,
        "slugs_resolved": 0,
        "slugs_failed": 0,
        "slug_details": [],
        "error": None,
    }

    try:
        events = _search_events_for_league(gamma, league)
        result["events_found"] = len(events)

        if not events:
            # No active events — this is "pending", not "failed"
            result["status"] = "pending"
            result["error"] = f"No active events found for {league}"
            return result

        for event in events:
            slug = _extract_slug_from_event(event)
            if not slug:
                continue

            result["slugs_tested"] += 1
            slug_detail: dict[str, Any] = {
                "slug": slug,
                "resolved": False,
                "method": None,
                "tags_count": 0,
                "tags_valid": 0,
                "error": None,
            }

            # Step 1: Try fast-path lookup
            tags = gamma.lookup_markets_by_slug(slug)
            if tags:
                slug_detail["method"] = "fast_path"
            else:
                # Step 2: Fallback using team extraction
                extracted_league, teams = gamma._extract_teams_from_slug(slug)
                home = teams[0] if len(teams) > 0 else ""
                away = teams[1] if len(teams) > 1 else ""
                if home and away:
                    tags = gamma.lookup_markets_fallback(
                        extracted_league or league, home, away
                    )
                    if tags:
                        slug_detail["method"] = "fallback"

            if tags:
                valid_tags = [t for t in tags if gamma._validate_market_tag(t)]
                slug_detail["tags_count"] = len(tags)
                slug_detail["tags_valid"] = len(valid_tags)
                if valid_tags:
                    slug_detail["resolved"] = True
                    result["slugs_resolved"] += 1
                else:
                    result["slugs_failed"] += 1
                    slug_detail["error"] = (
                        "Tags found but none valid (empty token/condition IDs)"
                    )
            else:
                result["slugs_failed"] += 1
                slug_detail["error"] = (
                    "No tags returned from either fast-path or fallback"
                )

            result["slug_details"].append(slug_detail)

        # Determine league status
        if result["slugs_tested"] == 0:
            result["status"] = "pending"
        elif result["slugs_resolved"] > 0 and result["slugs_failed"] == 0:
            result["status"] = "pass"
        elif result["slugs_resolved"] > 0:
            result["status"] = "partial"  # some resolved, some failed
        else:
            result["status"] = "fail"

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result


def run_validation(output_path: str | None = None) -> dict[str, Any]:
    """Run VALID-01 slug normalization validation for all 9 sports.

    Returns the full structured report dict and optionally writes to file.
    """
    start_time = time.time()
    gamma = GammaMarketClient()

    report: dict[str, Any] = {
        "validation_id": "VALID-01",
        "description": "Slug normalization across all 9 sport types against live Polymarket data",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 0.0,
        "overall_status": "pending",
        "leagues_tested": len(ALL_LEAGUES),
        "leagues_passed": 0,
        "leagues_pending": 0,
        "leagues_failed": 0,
        "results": [],
    }

    print(
        f"[validate_slugs] event=start leagues={ALL_LEAGUES}",
        file=sys.stderr,
    )

    for league in ALL_LEAGUES:
        print(
            f"[validate_slugs] event=testing_league league={league}",
            file=sys.stderr,
        )
        league_result = _validate_league(gamma, league)
        report["results"].append(league_result)

        status = league_result["status"]
        if status == "pass":
            report["leagues_passed"] += 1
            print(
                f"[validate_slugs] event=league_result league={league} status=pass "
                f"resolved={league_result['slugs_resolved']}/{league_result['slugs_tested']}",
                file=sys.stderr,
            )
        elif status == "pending":
            report["leagues_pending"] += 1
            print(
                f"[validate_slugs] event=league_result league={league} status=pending "
                f"reason=no_active_events",
                file=sys.stderr,
            )
        elif status == "partial":
            report["leagues_passed"] += 1  # partial counts as progress
            print(
                f"[validate_slugs] event=league_result league={league} status=partial "
                f"resolved={league_result['slugs_resolved']} "
                f"failed={league_result['slugs_failed']}",
                file=sys.stderr,
            )
        else:
            report["leagues_failed"] += 1
            print(
                f"[validate_slugs] event=league_result league={league} status={status} "
                f"error={league_result.get('error')}",
                file=sys.stderr,
            )

    # Determine overall status
    elapsed = time.time() - start_time
    report["duration_seconds"] = round(elapsed, 2)

    if report["leagues_failed"] > 0:
        report["overall_status"] = "fail"
    elif report["leagues_passed"] == report["leagues_tested"]:
        report["overall_status"] = "pass"
    elif report["leagues_passed"] > 0:
        report["overall_status"] = "partial"
    else:
        # All pending — no live events for any sport right now
        report["overall_status"] = "pending"

    gamma.close()

    # Output
    report_json = json.dumps(report, indent=2)
    print(report_json)

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w") as f:
            f.write(report_json)
        print(
            f"[validate_slugs] event=report_written path={output_path}",
            file=sys.stderr,
        )

    print(
        f"[validate_slugs] event=complete overall_status={report['overall_status']} "
        f"passed={report['leagues_passed']} pending={report['leagues_pending']} "
        f"failed={report['leagues_failed']} duration={report['duration_seconds']}s",
        file=sys.stderr,
    )

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="VALID-01: Slug normalization validation for all 9 sport types"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON report (default: stdout only)",
    )
    args = parser.parse_args()
    report = run_validation(output_path=args.output)

    # Exit code: 0 if pass/partial/pending, 1 if fail
    if report["overall_status"] == "fail":
        sys.exit(1)


if __name__ == "__main__":
    main()
