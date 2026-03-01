from datetime import datetime, timedelta, timezone
import os

from newsapi import NewsApiClient

from agents.utils.objects import Article


class News:
    def __init__(self) -> None:
        self.configs = {
            "language": "en",
            "country": "us",
            "top_headlines": "https://newsapi.org/v2/top-headlines?country=us&apiKey=",
            "base_url": "https://newsapi.org/v2/",
        }

        self.categories = {
            "business",
            "entertainment",
            "general",
            "health",
            "science",
            "sports",
            "technology",
        }

        self.API = NewsApiClient(os.getenv("NEWSAPI_API_KEY"))

    def get_articles_for_cli_keywords(
        self, keywords: str, limit: int = 10, days: int = 7, relevance: bool = False
    ) -> "tuple[list[Article], bool]":
        query_words = [word.strip() for word in keywords.split(",") if word.strip()]
        if not query_words:
            return [], False

        safe_limit = max(limit, 0)
        used_fallback = relevance
        safe_days = max(days, 1)
        date_end = datetime.now(timezone.utc).date()
        date_start = date_end - timedelta(days=safe_days)
        relevance_terms = self._expand_relevance_terms(query_words)

        if relevance:
            all_articles = self.get_articles_for_options(
                query_words,
                date_start=date_start.strftime("%Y-%m-%d"),
                date_end=date_end.strftime("%Y-%m-%d"),
                sort_by="relevancy",
            )
            article_objects = self._to_article_objects(all_articles)
            article_objects = self._filter_articles_by_body_relevance(
                article_objects, relevance_terms
            )
            article_objects = sorted(
                article_objects,
                key=lambda article: (
                    self._body_relevance_score(article, relevance_terms),
                    self._published_at_timestamp(article),
                ),
                reverse=True,
            )
        else:
            all_articles = self.get_articles_for_options(query_words)
            article_objects = self._to_article_objects(all_articles)
            if not article_objects:
                used_fallback = True
                all_articles = self.get_articles_for_options(
                    query_words,
                    date_start=date_start.strftime("%Y-%m-%d"),
                    date_end=date_end.strftime("%Y-%m-%d"),
                    sort_by="publishedAt",
                )
                article_objects = self._to_article_objects(all_articles)
            article_objects = sorted(
                article_objects, key=self._published_at_timestamp, reverse=True
            )

        article_objects = self._dedupe_articles(article_objects)
        return article_objects[:safe_limit], used_fallback

    def get_top_articles_for_market(self, market_object: dict) -> "list[Article]":
        return self.API.get_top_headlines(
            language="en", country="usa", q=market_object["description"]
        )

    def get_articles_for_options(
        self,
        market_options: "list[str]",
        date_start: str = None,
        date_end: str = None,
        sort_by: str = "publishedAt",
    ) -> "list[Article]":

        all_articles = {}
        # Default to top articles if no start and end dates are given for search
        if not date_start and not date_end:
            for option in market_options:
                response_dict = self.API.get_top_headlines(
                    q=option.strip(),
                    language=self.configs["language"],
                    country=self.configs["country"],
                )
                articles = response_dict["articles"]
                all_articles[option] = articles
        else:
            for option in market_options:
                response_dict = self.API.get_everything(
                    q=option.strip(),
                    language=self.configs["language"],
                    from_param=date_start,
                    to=date_end,
                    sort_by=sort_by,
                )
                articles = response_dict["articles"]
                all_articles[option] = articles

        return all_articles

    def _to_article_objects(self, all_articles: dict) -> "list[Article]":
        article_objects: list[Article] = []
        for _, articles in all_articles.items():
            for article in articles:
                article_objects.append(Article(**article))
        return article_objects

    def _dedupe_articles(self, articles: "list[Article]") -> "list[Article]":
        deduped_articles: list[Article] = []
        seen_keys: set = set()
        for article in articles:
            dedupe_key = article.url or f"{article.title}|{article.publishedAt}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped_articles.append(article)
        return deduped_articles

    def _published_at_timestamp(self, article: Article) -> float:
        if not article.publishedAt:
            return float("-inf")
        published_at = article.publishedAt
        if published_at.endswith("Z"):
            published_at = published_at[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(published_at).timestamp()
        except ValueError:
            return float("-inf")

    def _body_text_for_relevance(self, article: Article) -> str:
        parts = [article.description or "", article.content or ""]
        return " ".join(parts).lower()

    def _expand_relevance_terms(self, query_words: "list[str]") -> "list[str]":
        expanded_terms: list[str] = []
        for query in query_words:
            normalized = query.strip().lower()
            if not normalized:
                continue
            expanded_terms.append(normalized)
            for token in normalized.split():
                if len(token) > 1:
                    expanded_terms.append(token)
        # Preserve order while removing duplicates.
        return list(dict.fromkeys(expanded_terms))

    def _body_relevance_score(self, article: Article, query_terms: "list[str]") -> int:
        body_text = self._body_text_for_relevance(article)
        return sum(1 for query in query_terms if query in body_text)

    def _filter_articles_by_body_relevance(
        self, articles: "list[Article]", query_terms: "list[str]"
    ) -> "list[Article]":
        return [
            article
            for article in articles
            if self._body_relevance_score(article, query_terms) > 0
        ]

    def get_category(self, market_object: dict) -> str:
        news_category = "general"
        market_category = market_object["category"]
        if market_category in self.categories:
            news_category = market_category
        return news_category
