import os
import re
import shutil
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import unquote, urlparse

from agents.application.executor import Executor as Agent, canonicalize_category
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
        self.default_include_news = (
            str(os.getenv("TRADE_INCLUDE_NEWS", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        self.default_exclude_sports = (
            str(os.getenv("TRADE_EXCLUDE_SPORTS", "false")).strip().lower()
            in ("1", "true", "yes", "on")
        )
        try:
            min_order_amount = float(os.getenv("TRADE_MIN_ORDER_AMOUNT_USDC", "1.0"))
        except (TypeError, ValueError):
            min_order_amount = 1.0
        self.min_order_amount_usdc = max(0.0, min_order_amount)

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

    def _market_category_bucket(self, market_obj) -> str:
        market_doc = market_obj[0] if isinstance(market_obj, (list, tuple)) else None
        metadata = getattr(market_doc, "metadata", {}) or {}
        description = str(getattr(market_doc, "page_content", "") or "")
        return canonicalize_category(
            explicit_category=str(metadata.get("category", "")),
            tags=str(metadata.get("tags", "")),
            question=str(metadata.get("question", "")),
            description=description,
        )

    def _exclude_sports_markets(self, filtered_markets: List[tuple]) -> List[tuple]:
        return [
            market_obj
            for market_obj in filtered_markets
            if self._market_category_bucket(market_obj) != "sports"
        ]

    def _apply_minimum_order_constraints(
        self,
        selected_candidates: List[CandidateTrade],
        usdc_balance: float,
    ) -> List[CandidateTrade]:
        if not selected_candidates:
            return selected_candidates

        if self.min_order_amount_usdc <= 0:
            self.agent.allocate_selected_candidates(selected_candidates, usdc_balance)
            return selected_candidates

        working = list(selected_candidates)
        while working:
            self.agent.allocate_selected_candidates(working, usdc_balance)

            below_min = [
                candidate
                for candidate in working
                if candidate.allocation_amount_usdc < self.min_order_amount_usdc
            ]
            if not below_min:
                break

            below_ids = {id(candidate) for candidate in below_min}
            drop_candidate = None
            for candidate in reversed(working):
                if id(candidate) in below_ids:
                    drop_candidate = candidate
                    break
            if drop_candidate is None:
                break

            attempted_amount = float(drop_candidate.allocation_amount_usdc)
            drop_candidate.allocation_amount_usdc = 0.0
            drop_candidate.allocation_fraction = 0.0
            drop_candidate.execution_status = "SKIPPED_BELOW_MIN_ORDER"
            drop_candidate.execution_response = (
                f"allocation={attempted_amount:.6f} below min_order_amount_usdc="
                f"{self.min_order_amount_usdc:.6f}"
            )
            print(
                f"[allocation] skipped market_id={drop_candidate.market_id} "
                f"allocation={attempted_amount:.6f} "
                f"min_order={self.min_order_amount_usdc:.6f}"
            )
            working.remove(drop_candidate)

        return selected_candidates

    def _summarize_execution_outcomes(self, candidates: List[CandidateTrade]) -> Dict[str, int]:
        status_counts: Dict[str, int] = {}
        for candidate in candidates:
            status = candidate.execution_status or "UNKNOWN"
            status_counts[status] = status_counts.get(status, 0) + 1
        return status_counts

    def _extract_min_order_error_details(self, error_text: str) -> Optional[Dict[str, float]]:
        match = re.search(
            r"order\s+\(\$([0-9]*\.?[0-9]+)\),\s*min size:\s*\$([0-9]*\.?[0-9]+)",
            str(error_text or ""),
            flags=re.IGNORECASE,
        )
        if not match:
            return None
        try:
            return {
                "attempted_amount_usdc": float(match.group(1)),
                "minimum_amount_usdc": float(match.group(2)),
            }
        except (TypeError, ValueError):
            return None

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

    def _build_market_news_keywords(
        self,
        market_obj,
        target_event: Optional[SimpleEvent] = None,
    ) -> str:
        market_doc = market_obj[0] if isinstance(market_obj, (list, tuple)) else None
        metadata = getattr(market_doc, "metadata", {}) or {}

        tags = [tag.strip() for tag in str(metadata.get("tags", "")).split(",") if tag.strip()]
        event_title = target_event.title if target_event and target_event.title else ""
        event_slug = target_event.slug if target_event and target_event.slug else ""
        metadata_event_title = str(metadata.get("event_title", "")).strip()
        metadata_event_slug = str(metadata.get("event_slug", "")).strip()

        base_keywords = self._normalize_keywords(
            [
                event_title,
                event_slug.replace("-", " "),
                metadata_event_title,
                metadata_event_slug.replace("-", " "),
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
        news_limit: int,
        news_days: int,
        news_relevance: bool,
        target_event: Optional[SimpleEvent] = None,
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

            keywords = self._build_market_news_keywords(
                market_obj,
                target_event=target_event,
            )
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

        balance_report = {
            "wallet_address": "",
            "collateral_address": "",
            "balance_source": "unknown",
            "available_usdc_balance": 0.0,
            "balances_by_token": {},
            "warnings": [],
            "errors": [],
        }
        try:
            balance_report = self.polymarket.get_usdc_balance_report()
        except Exception as err:
            balance_report["errors"].append(f"balance_report_failed error={err}")

        usdc_balance = float(balance_report.get("available_usdc_balance", 0.0))
        wallet_address = balance_report.get("wallet_address", "") or "n/a"
        signer_address = balance_report.get("signer_address", "") or "n/a"
        funder_address = balance_report.get("funder_address", "") or "n/a"
        signature_type = balance_report.get("signature_type", "n/a")
        collateral_address = balance_report.get("collateral_address", "") or "n/a"
        balance_source = balance_report.get("balance_source", "unknown")
        print(
            "[portfolio] "
            f"wallet={wallet_address} "
            f"signer={signer_address} "
            f"funder={funder_address} "
            f"signature_type={signature_type} "
            f"collateral_token={collateral_address} "
            f"source={balance_source} "
            f"usdc_balance={usdc_balance:.6f}"
        )

        balances_by_token = balance_report.get("balances_by_token") or {}
        if balances_by_token:
            formatted_balances = []
            for token_address, token_data in balances_by_token.items():
                balance_value = float(token_data.get("balance_usdc", 0.0))
                formatted_balances.append(f"{token_address}:{balance_value:.6f}")
            print("[portfolio] onchain_token_balances=" + ", ".join(formatted_balances))

        for warning in balance_report.get("warnings", []) or []:
            print(f"[portfolio] warning={warning}")
        for error in balance_report.get("errors", []) or []:
            print(f"[portfolio] error={error}")

        selected_candidates = self._apply_minimum_order_constraints(
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
            print(
                f"{completion_step}. LIVE MODE aborted: available collateral USDC balance is zero."
            )
            print(
                "[portfolio] verify POLYGON_WALLET_PRIVATE_KEY, POLYGON_RPC_URL, "
                "and that funds are on the configured collateral token."
            )
            return

        self._execute_candidates(selected_candidates)
        self._print_trade_summary_table(selected_candidates, mode="EXECUTED")
        status_counts = self._summarize_execution_outcomes(selected_candidates)
        executed_count = status_counts.get("EXECUTED", 0)
        failed_count = (
            status_counts.get("FAILED", 0)
            + status_counts.get("FAILED_MIN_ORDER_SIZE", 0)
        )
        skipped_count = sum(
            count
            for status, count in status_counts.items()
            if status.startswith("SKIPPED_")
        )
        print(
            "[execution] summary "
            f"executed={executed_count} failed={failed_count} skipped={skipped_count} "
            f"status_counts={status_counts}"
        )
        if failed_count > 0:
            print(f"{completion_step}. LIVE RUN completed with execution failures.")
            return
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

            if candidate.allocation_amount_usdc < self.min_order_amount_usdc:
                candidate.execution_status = "SKIPPED_BELOW_MIN_ORDER"
                candidate.execution_response = (
                    "allocation_amount_usdc below configured minimum order size "
                    f"{self.min_order_amount_usdc:.6f}"
                )
                print(
                    f"[execution] skipped rank={idx} market_id={candidate.market_id} "
                    f"reason=below_min_order allocation={candidate.allocation_amount_usdc:.6f} "
                    f"min_order={self.min_order_amount_usdc:.6f}"
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
                error_text = str(err)
                min_order_details = self._extract_min_order_error_details(error_text)
                if min_order_details is not None:
                    candidate.execution_status = "FAILED_MIN_ORDER_SIZE"
                    candidate.execution_response = {
                        "error": error_text,
                        **min_order_details,
                    }
                    print(
                        f"[execution] failed rank={idx} market_id={candidate.market_id} "
                        "reason=min_order_size "
                        f"attempted={min_order_details['attempted_amount_usdc']:.6f} "
                        f"minimum={min_order_details['minimum_amount_usdc']:.6f}"
                    )
                else:
                    candidate.execution_status = "FAILED"
                    candidate.execution_response = error_text
                    print(
                        f"[execution] failed rank={idx} market_id={candidate.market_id} error={error_text}"
                    )
                if not self.continue_on_execution_error:
                    print("[execution] aborting_due_to_failure TRADE_CONTINUE_ON_EXECUTION_ERROR=false")
                    break

    def one_best_trade(
        self,
        include_news: Optional[bool] = None,
        news_limit: Optional[int] = None,
        news_days: Optional[int] = None,
        news_relevance: Optional[bool] = None,
        exclude_sports: Optional[bool] = None,
    ) -> None:
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

            resolved_exclude_sports = (
                self.default_exclude_sports if exclude_sports is None else bool(exclude_sports)
            )
            if resolved_exclude_sports:
                before_count = len(filtered_markets)
                filtered_markets = self._exclude_sports_markets(filtered_markets)
                excluded_count = before_count - len(filtered_markets)
                print(
                    f"[markets] exclude_sports=true excluded={excluded_count} "
                    f"remaining={len(filtered_markets)}"
                )
                if not filtered_markets:
                    print("No non-sports markets survived filtering. Exiting run.")
                    return

            resolved_include_news = (
                self.default_include_news if include_news is None else bool(include_news)
            )
            context_by_market_id = None
            if resolved_include_news:
                resolved_news_limit = (
                    self.default_news_limit if news_limit is None else max(1, int(news_limit))
                )
                resolved_news_days = (
                    self.default_news_days if news_days is None else max(1, int(news_days))
                )
                resolved_news_relevance = (
                    self.default_news_relevance
                    if news_relevance is None
                    else bool(news_relevance)
                )
                print(
                    "[news] config "
                    f"limit={resolved_news_limit} days={resolved_news_days} relevance={resolved_news_relevance}"
                )
                context_by_market_id = self._build_news_context_by_market_id(
                    filtered_markets=filtered_markets,
                    news_limit=resolved_news_limit,
                    news_days=resolved_news_days,
                    news_relevance=resolved_news_relevance,
                )
            else:
                print("[news] disabled for autonomous run")

            candidates_payload = self.agent.build_trade_candidates(
                filtered_markets,
                supplemental_context_by_market_id=context_by_market_id,
            )
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
        exclude_sports: Optional[bool] = None,
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

            resolved_exclude_sports = (
                self.default_exclude_sports if exclude_sports is None else bool(exclude_sports)
            )
            if resolved_exclude_sports:
                before_count = len(filtered_markets)
                filtered_markets = self._exclude_sports_markets(filtered_markets)
                excluded_count = before_count - len(filtered_markets)
                print(
                    f"[markets] exclude_sports=true excluded={excluded_count} "
                    f"remaining={len(filtered_markets)}"
                )
                if not filtered_markets:
                    print("No non-sports markets survived filtering. Exiting run.")
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
