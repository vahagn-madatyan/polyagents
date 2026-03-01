import os
import re
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from agents.application.executor import Executor as Agent
from agents.connectors.news import News
from agents.polymarket.gamma import GammaMarketClient as Gamma
from agents.polymarket.polymarket import Polymarket
from agents.utils.objects import Article, CandidateTrade, SimpleEvent


class Trader:
    def __init__(self):
        self.polymarket = Polymarket()
        self.gamma = Gamma()
        self.agent = Agent()
        self.news = News()
        self.execute_trades = (
            str(os.getenv("EXECUTE_TRADES", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.continue_on_execution_error = (
            str(os.getenv("TRADE_CONTINUE_ON_EXECUTION_ERROR", "true")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.log_rationale = (
            str(os.getenv("TRADE_LOG_RATIONALE", "true")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.news_context_article_cap = max(1, int(os.getenv("TRADE_NEWS_CONTEXT_ARTICLE_CAP", "3")))
        self.default_news_limit = max(1, int(os.getenv("TRADE_NEWS_LIMIT", "5")))
        self.default_news_days = max(1, int(os.getenv("TRADE_NEWS_DAYS", "7")))
        self.default_news_relevance = (
            str(os.getenv("TRADE_NEWS_RELEVANCE", "true")).strip().lower()
            in ("1", "true", "yes", "on")
        )

    def pre_trade_logic(self) -> None:
        self.clear_local_dbs()

    def clear_local_dbs(self) -> None:
        for path in ("local_db_events", "local_db_markets"):
            try:
                shutil.rmtree(path)
            except FileNotFoundError:
                continue
            except Exception as err:
                print(f"[cleanup] unable_to_remove path={path} error={err}")

    def _truncate(self, value, max_len: int = 88) -> str:
        text = str(value)
        if len(text) <= max_len:
            return text
        return text[: max_len - 3] + "..."

    def _format_probabilities(self, probabilities: list) -> str:
        if not probabilities:
            return "n/a"
        parts = []
        for item in probabilities:
            outcome = item.get("outcome", "unknown")
            likelihood = item.get("likelihood")
            try:
                likelihood_str = f"{float(likelihood):.4f}"
            except (TypeError, ValueError):
                likelihood_str = str(likelihood)
            parts.append(f"{outcome}={likelihood_str}")
        return "; ".join(parts)

    def _format_book_prices(self, candidate: CandidateTrade) -> str:
        if not candidate.outcomes or not candidate.outcome_prices:
            return "n/a"
        pairs = []
        for idx, outcome in enumerate(candidate.outcomes):
            price = candidate.outcome_prices[idx] if idx < len(candidate.outcome_prices) else "n/a"
            pairs.append(f"{outcome}:{price}")
        return "; ".join(pairs)

    def _render_table(self, headers: List[str], rows: List[List[str]]) -> None:
        if not rows:
            return

        col_widths = []
        for idx, header in enumerate(headers):
            max_row_width = max(len(str(row[idx])) for row in rows)
            col_widths.append(max(len(header), max_row_width))

        border = "+" + "+".join("-" * (width + 2) for width in col_widths) + "+"

        print()
        print(border)
        print(
            "| "
            + " | ".join(headers[idx].ljust(col_widths[idx]) for idx in range(len(headers)))
            + " |"
        )
        print(border)
        for row in rows:
            print(
                "| "
                + " | ".join(str(row[idx]).ljust(col_widths[idx]) for idx in range(len(headers)))
                + " |"
            )
        print(border)
        print()

    def _print_trade_summary_table(self, candidates: List[CandidateTrade], mode: str) -> None:
        if not candidates:
            print("No selected candidates to summarize.")
            return

        headers = [
            "Rank",
            "Category",
            "Market",
            "Outcome",
            "Probabilities",
            "Gap",
            "Side",
            "Price",
            "Alloc %",
            "Alloc USDC",
            "Book Prices",
            "RAG",
            "Mode",
            "Status",
        ]

        rows = []
        for idx, candidate in enumerate(candidates, start=1):
            rows.append(
                [
                    str(idx),
                    candidate.category_bucket,
                    self._truncate(candidate.question, 64),
                    candidate.suggested_outcome or "n/a",
                    self._truncate(self._format_probabilities(candidate.probabilities), 46),
                    f"{candidate.confidence_gap:.4f}",
                    candidate.parsed_side or "BUY",
                    f"{candidate.parsed_price:.4f}" if candidate.parsed_price is not None else "n/a",
                    f"{candidate.allocation_fraction:.4f}",
                    f"{candidate.allocation_amount_usdc:.4f}",
                    self._truncate(self._format_book_prices(candidate), 40),
                    f"{candidate.rag_score:.6f}" if candidate.rag_score is not None else "n/a",
                    mode,
                    candidate.execution_status,
                ]
            )

        self._render_table(headers, rows)

    def _log_rationale(self, candidates: List[CandidateTrade]) -> None:
        if not self.log_rationale:
            return

        print("[rationale] logging concise rationale summaries only; hidden chain-of-thought is unavailable.")
        for idx, candidate in enumerate(candidates, start=1):
            print(
                f"[rationale] rank={idx} market_id={candidate.market_id} "
                f"category={candidate.category_bucket} outcome={candidate.suggested_outcome!r}"
            )
            print(f"[rationale] summary={candidate.rationale or 'n/a'}")
            print(
                "[rationale] risk_factors="
                + (", ".join(candidate.risk_factors) if candidate.risk_factors else "n/a")
            )
            print(f"[rationale] counter_case={candidate.counter_case or 'n/a'}")

    def _log_run_summary(
        self,
        candidates_payload: dict,
        selected_candidates: List[CandidateTrade],
    ) -> None:
        all_candidates = candidates_payload.get("all_candidates", [])
        categories_considered = sorted({candidate.category_bucket for candidate in all_candidates})
        categories_selected = sorted({candidate.category_bucket for candidate in selected_candidates})
        planned_allocation = sum(candidate.allocation_amount_usdc for candidate in selected_candidates)

        print(
            "[run] candidate_summary "
            f"input_markets={candidates_payload.get('input_markets', 0)} "
            f"deduped_markets={candidates_payload.get('deduped_markets', 0)} "
            f"evaluated_candidates={candidates_payload.get('evaluated_candidates', 0)} "
            f"selected={len(selected_candidates)}"
        )
        print(
            "[run] category_summary "
            f"considered={categories_considered or ['n/a']} "
            f"selected={categories_selected or ['n/a']}"
        )
        print(f"[run] planned_allocation_usdc={planned_allocation:.6f}")

    def _extract_event_slug_from_url(self, event_url: str) -> str:
        raw_value = str(event_url or "").strip()
        if not raw_value:
            raise ValueError("event_url is required")

        if "://" not in raw_value and "/" not in raw_value and " " not in raw_value:
            slug = raw_value.strip().strip("/")
            if slug:
                return slug

        parsed = urlparse(raw_value)
        path = unquote(parsed.path or "")
        segments = [segment for segment in path.split("/") if segment]
        if not segments:
            raise ValueError(f"Unable to parse event slug from URL: {event_url}")

        if "event" in segments:
            event_index = segments.index("event")
            if event_index + 1 < len(segments):
                slug = segments[event_index + 1].strip()
                if slug:
                    return slug

        if segments[-2:] and len(segments) >= 2 and segments[-2] == "event":
            slug = segments[-1].strip()
            if slug:
                return slug

        raise ValueError(f"URL must include /event/<slug>: {event_url}")

    def _resolve_event_by_slug(self, event_slug: str) -> Optional[SimpleEvent]:
        slug = str(event_slug or "").strip().lower()
        if not slug:
            return None

        raw_events = []
        try:
            raw_events = self.gamma.get_events(
                querystring_params={
                    "slug": slug,
                    "limit": 10,
                }
            )
        except Exception as err:
            print(f"[event] direct_lookup_failed slug={slug} error={err}")

        parsed_events: List[SimpleEvent] = []
        for raw_event in raw_events or []:
            try:
                parsed_events.append(SimpleEvent(**self.polymarket.map_api_to_event(raw_event)))
            except Exception as err:
                print(f"[event] parse_failed slug={slug} error={err}")

        direct_matches = [
            event
            for event in parsed_events
            if str(event.slug or "").strip().lower() == slug
        ]
        if direct_matches:
            # Prefer active/open/non-archived, but still return a slug match if only closed/archived exists.
            preferred = sorted(
                direct_matches,
                key=lambda event: (
                    not bool(event.active),
                    bool(event.closed),
                    bool(event.archived),
                ),
            )
            return preferred[0]

        print(f"[event] falling_back_to_full_scan slug={slug}")
        try:
            for event in self.polymarket.get_all_events():
                if str(event.slug or "").strip().lower() == slug:
                    return event
        except Exception as err:
            print(f"[event] fallback_scan_failed slug={slug} error={err}")
            return None

        return None

    def _article_published_date(self, article: Article) -> str:
        value = str(article.publishedAt or "").strip()
        if not value:
            return "n/a"
        value = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.date().isoformat()
        except ValueError:
            return str(article.publishedAt)

    def _normalize_keywords(self, keywords: List[str], max_keywords: int = 8) -> List[str]:
        normalized = []
        seen = set()
        for keyword in keywords:
            clean = re.sub(r"\s+", " ", str(keyword or "").strip())
            if not clean:
                continue
            lowered = clean.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(clean)
            if len(normalized) >= max_keywords:
                break
        return normalized

    def _build_market_news_keywords(self, market_obj, target_event: SimpleEvent) -> str:
        market_doc = market_obj[0] if isinstance(market_obj, (list, tuple)) else None
        metadata = getattr(market_doc, "metadata", {}) or {}

        tags = [tag.strip() for tag in str(metadata.get("tags", "")).split(",") if tag.strip()]
        base_keywords = self._normalize_keywords(
            [
                target_event.title,
                target_event.slug.replace("-", " "),
                str(metadata.get("event_title", "")),
                str(metadata.get("question", "")),
                str(metadata.get("category", "")),
            ]
            + tags[:3],
            max_keywords=8,
        )
        return ",".join(base_keywords[:4])

    def _format_news_context(self, articles: List[Article], article_cap: int) -> str:
        if not articles:
            return "No relevant recent news articles were found."

        lines = []
        for article in articles[:article_cap]:
            title = str(article.title or "Untitled article").strip()
            source = str(article.source.name if article.source else "Unknown source").strip()
            published = self._article_published_date(article)
            description = str(article.description or article.content or "").strip()
            compact_description = self._truncate(description, max_len=180) if description else ""
            url = str(article.url or "").strip()

            line = f"- {title} ({source}, {published})"
            if compact_description:
                line += f": {compact_description}"
            if url:
                line += f" [url: {url}]"
            lines.append(line)

        return "\n".join(lines)

    def _build_news_context_by_market_id(
        self,
        filtered_markets: List[tuple],
        target_event: SimpleEvent,
        news_limit: int,
        news_days: int,
        news_relevance: bool,
    ) -> Dict[int, str]:
        context_by_market_id: Dict[int, str] = {}
        article_cap = max(1, min(self.news_context_article_cap, news_limit))

        for market_obj in filtered_markets:
            market_doc = market_obj[0] if isinstance(market_obj, (list, tuple)) else None
            metadata = getattr(market_doc, "metadata", {}) or {}
            market_id_raw = metadata.get("id")
            try:
                market_id = int(market_id_raw)
            except (TypeError, ValueError):
                continue

            keywords = self._build_market_news_keywords(market_obj, target_event)
            if not keywords:
                continue

            try:
                articles, used_fallback = self.news.get_articles_for_cli_keywords(
                    keywords=keywords,
                    limit=max(1, news_limit),
                    days=max(1, news_days),
                    relevance=bool(news_relevance),
                )
            except Exception as err:
                print(f"[news] fetch_failed market_id={market_id} error={err}")
                continue

            print(
                f"[news] market_id={market_id} keywords={keywords!r} "
                f"articles={len(articles)} fallback={used_fallback}"
            )
            context = self._format_news_context(articles, article_cap=article_cap)
            context_by_market_id[market_id] = context

        return context_by_market_id

    def _finalize_candidates(
        self,
        candidates_payload: dict,
        completion_step: int,
    ) -> None:
        selected_candidates: List[CandidateTrade] = candidates_payload["selected_candidates"]
        print(f"{completion_step - 1}. SELECTED {len(selected_candidates)} TRADE CANDIDATES")
        if not selected_candidates:
            print("No candidate trades selected. Exiting run.")
            return

        try:
            usdc_balance = self.polymarket.get_usdc_balance()
        except Exception as err:
            usdc_balance = 0.0
            print(f"[portfolio] unable_to_fetch_usdc_balance error={err}")
        print(f"[portfolio] usdc_balance={usdc_balance:.6f}")

        selected_candidates = self.agent.allocate_selected_candidates(
            selected_candidates,
            usdc_balance,
        )

        self._log_run_summary(candidates_payload, selected_candidates)
        self._log_rationale(selected_candidates)

        mode = "DRY_RUN" if not self.execute_trades else "LIVE"
        self._print_trade_summary_table(selected_candidates, mode=mode)

        if not self.execute_trades:
            print(f"{completion_step}. DRY RUN complete (set EXECUTE_TRADES=true to place orders).")
            return

        if usdc_balance <= 0:
            print(f"{completion_step}. LIVE MODE aborted: no available USDC balance.")
            return

        self._execute_candidates(selected_candidates)
        self._print_trade_summary_table(selected_candidates, mode="EXECUTED")
        print(f"{completion_step}. LIVE RUN complete.")

    def _execute_candidates(self, candidates: List[CandidateTrade]) -> None:
        for idx, candidate in enumerate(candidates, start=1):
            if candidate.allocation_amount_usdc <= 0:
                candidate.execution_status = "SKIPPED_ZERO_ALLOCATION"
                candidate.execution_response = "allocation_amount_usdc <= 0"
                print(
                    f"[execution] skipped rank={idx} market_id={candidate.market_id} reason=zero_allocation"
                )
                continue

            try:
                token_map = self.polymarket.resolve_token_for_outcome(
                    outcomes=candidate.outcomes,
                    token_ids=candidate.token_ids,
                    selected_outcome=candidate.suggested_outcome,
                    side=candidate.parsed_side,
                )
                response = self.polymarket.execute_market_order_for_token(
                    token_id=token_map["token_id"],
                    amount=candidate.allocation_amount_usdc,
                )
                candidate.execution_status = "EXECUTED"
                candidate.execution_response = {
                    "response": response,
                    "token_id": token_map["token_id"],
                    "requested_side": token_map["requested_side"],
                    "execution_side": token_map["execution_side"],
                    "requested_outcome": token_map["requested_outcome"],
                    "execution_outcome": token_map["execution_outcome"],
                    "transform": token_map["transform"],
                }
                print(
                    f"[execution] success rank={idx} market_id={candidate.market_id} "
                    f"amount={candidate.allocation_amount_usdc:.6f} token_id={token_map['token_id']} "
                    f"transform={token_map['transform']}"
                )
            except Exception as err:
                candidate.execution_status = "FAILED"
                candidate.execution_response = str(err)
                print(
                    f"[execution] failed rank={idx} market_id={candidate.market_id} error={err}"
                )
                if not self.continue_on_execution_error:
                    print("[execution] aborting_due_to_failure TRADE_CONTINUE_ON_EXECUTION_ERROR=false")
                    break

    def one_best_trade(self) -> None:
        """
        one_best_trade runs the autonomous trading pipeline end-to-end.
        """
        try:
            self.pre_trade_logic()

            events = self.polymarket.get_all_tradeable_events()
            print(f"1. FOUND {len(events)} EVENTS")
            if not events:
                print("No tradeable events found. Exiting run.")
                return

            filtered_events = self.agent.filter_events_with_rag(events)
            print(f"2. FILTERED {len(filtered_events)} EVENTS")
            if not filtered_events:
                print("No events survived filtering. Exiting run.")
                return

            markets = self.agent.map_filtered_events_to_markets(filtered_events)
            print()
            print(f"3. FOUND {len(markets)} MARKETS")
            if not markets:
                print("No markets found for filtered events. Exiting run.")
                return

            print()
            filtered_markets = self.agent.filter_markets(markets)
            print(f"4. FILTERED {len(filtered_markets)} MARKETS")
            if not filtered_markets:
                print("No markets survived filtering. Exiting run.")
                return

            candidates_payload = self.agent.build_trade_candidates(filtered_markets)
            self._finalize_candidates(candidates_payload, completion_step=6)

        except Exception as e:
            print(f"Error {e} \n \n Aborting")
            return

    def analyze_event_url(
        self,
        event_url: str,
        news_limit: Optional[int] = None,
        news_days: Optional[int] = None,
        news_relevance: Optional[bool] = None,
    ) -> None:
        try:
            self.pre_trade_logic()

            resolved_news_limit = self.default_news_limit if news_limit is None else max(1, int(news_limit))
            resolved_news_days = self.default_news_days if news_days is None else max(1, int(news_days))
            resolved_news_relevance = (
                self.default_news_relevance if news_relevance is None else bool(news_relevance)
            )

            slug = self._extract_event_slug_from_url(event_url)
            print(f"1. RESOLVED EVENT SLUG {slug!r}")

            target_event = self._resolve_event_by_slug(slug)
            if not target_event:
                print(f"No event found for slug '{slug}'. Exiting run.")
                return

            print(
                "2. TARGET EVENT "
                f"id={target_event.id} title={target_event.title!r} slug={target_event.slug!r}"
            )

            if not target_event.active or target_event.closed or target_event.archived:
                print(
                    "[event] not_tradeable_state "
                    f"active={target_event.active} closed={target_event.closed} archived={target_event.archived}"
                )
                print("Target event is not currently tradeable. Exiting run.")
                return

            if target_event.restricted and not self.polymarket.allow_restricted_events:
                print(
                    "[event] restricted_event "
                    "ALLOW_RESTRICTED_EVENTS=false, so execution is blocked by current policy."
                )
                if self.execute_trades:
                    print(
                        "Set ALLOW_RESTRICTED_EVENTS=true if you are legally allowed and want to execute. Exiting run."
                    )
                    return
                print("Continuing as analysis-only dry run for restricted event.")

            markets = self.agent.map_filtered_events_to_markets([target_event])
            print()
            print(f"3. FOUND {len(markets)} MARKETS FOR EVENT")
            if not markets:
                print("No markets found for the target event. Exiting run.")
                return

            print()
            filtered_markets = self.agent.filter_markets(markets)
            print(f"4. FILTERED {len(filtered_markets)} MARKETS")
            if not filtered_markets:
                print("No markets survived filtering. Exiting run.")
                return

            print(
                "[news] config "
                f"limit={resolved_news_limit} days={resolved_news_days} relevance={resolved_news_relevance}"
            )
            context_by_market_id = self._build_news_context_by_market_id(
                filtered_markets=filtered_markets,
                target_event=target_event,
                news_limit=resolved_news_limit,
                news_days=resolved_news_days,
                news_relevance=resolved_news_relevance,
            )

            candidates_payload = self.agent.build_trade_candidates(
                filtered_markets,
                supplemental_context_by_market_id=context_by_market_id,
            )
            self._finalize_candidates(candidates_payload, completion_step=6)

        except Exception as e:
            print(f"Error {e} \n \n Aborting")
            return

    def maintain_positions(self):
        pass

    def incentive_farm(self):
        pass


if __name__ == "__main__":
    t = Trader()
    t.one_best_trade()
