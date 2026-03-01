from datetime import datetime, timezone
from unittest.mock import MagicMock

from agents.connectors.news import News


def _article(url: str, title: str, published_at: str) -> dict:
    return {
        "source": {"id": None, "name": "Example"},
        "author": "Reporter",
        "title": title,
        "description": f"{title} description",
        "url": url,
        "urlToImage": None,
        "publishedAt": published_at,
        "content": f"{title} content",
    }


def _article_without_url(title: str, published_at: str) -> dict:
    return {
        "source": {"id": None, "name": "Example"},
        "author": "Reporter",
        "title": title,
        "description": f"{title} description",
        "url": None,
        "urlToImage": None,
        "publishedAt": published_at,
        "content": f"{title} content",
    }


def _news_with_mocked_api() -> tuple[News, MagicMock]:
    news = News()
    api_mock = MagicMock()
    news.API = api_mock
    return news, api_mock


def test_top_headlines_hit_skips_fallback() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.return_value = {
        "articles": [
            _article("https://example.com/older", "Older", "2026-02-20T10:00:00Z"),
            _article("https://example.com/newer", "Newer", "2026-02-21T12:00:00Z"),
        ]
    }

    articles, used_fallback = news.get_articles_for_cli_keywords("iran")

    assert used_fallback is False
    assert len(articles) == 2
    assert articles[0].url == "https://example.com/newer"
    assert articles[1].url == "https://example.com/older"
    api_mock.get_everything.assert_not_called()


def test_top_headlines_miss_fallback_hits() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.side_effect = [{"articles": []}, {"articles": []}]
    api_mock.get_everything.side_effect = [
        {"articles": [_article("https://example.com/one", "One", "2026-02-25T08:00:00Z")]},
        {"articles": [_article("https://example.com/two", "Two", "2026-02-26T08:00:00Z")]},
    ]

    articles, used_fallback = news.get_articles_for_cli_keywords("iran,bombing")

    assert used_fallback is True
    assert len(articles) == 2
    assert [a.url for a in articles] == [
        "https://example.com/two",
        "https://example.com/one",
    ]
    for call in api_mock.get_everything.call_args_list:
        assert call.kwargs["language"] == "en"
        assert "country" not in call.kwargs
        assert call.kwargs["sort_by"] == "publishedAt"


def test_both_endpoints_empty_returns_empty_list() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.return_value = {"articles": []}
    api_mock.get_everything.return_value = {"articles": []}

    articles, used_fallback = news.get_articles_for_cli_keywords("iran")

    assert used_fallback is True
    assert articles == []


def test_deduplicates_by_url_then_title_and_published_at() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.side_effect = [{"articles": []}, {"articles": []}]
    api_mock.get_everything.side_effect = [
        {
            "articles": [
                _article("https://example.com/shared", "Shared URL", "2026-02-26T08:00:00Z"),
                _article_without_url("No URL Same Key", "2026-02-26T09:00:00Z"),
            ]
        },
        {
            "articles": [
                _article("https://example.com/shared", "Shared URL Duplicate", "2026-02-26T10:00:00Z"),
                _article_without_url("No URL Same Key", "2026-02-26T09:00:00Z"),
            ]
        },
    ]

    articles, used_fallback = news.get_articles_for_cli_keywords("iran,bombing")

    assert used_fallback is True
    assert len(articles) == 2
    keys = {article.url or f"{article.title}|{article.publishedAt}" for article in articles}
    assert keys == {
        "https://example.com/shared",
        "No URL Same Key|2026-02-26T09:00:00Z",
    }


def test_limit_truncates_results() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.return_value = {
        "articles": [
            _article(
                f"https://example.com/{idx}",
                f"Article {idx}",
                f"2026-02-{idx:02d}T08:00:00Z",
            )
            for idx in range(1, 16)
        ]
    }

    articles, used_fallback = news.get_articles_for_cli_keywords("iran", limit=5)

    assert used_fallback is False
    assert len(articles) == 5


def test_fallback_date_window_uses_requested_days() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_top_headlines.return_value = {"articles": []}
    api_mock.get_everything.return_value = {"articles": []}

    before = datetime.now(timezone.utc).date()
    news.get_articles_for_cli_keywords("iran", days=7)
    after = datetime.now(timezone.utc).date()

    kwargs = api_mock.get_everything.call_args.kwargs
    date_start = datetime.strptime(kwargs["from_param"], "%Y-%m-%d").date()
    date_end = datetime.strptime(kwargs["to"], "%Y-%m-%d").date()
    assert before <= date_end <= after
    assert (date_end - date_start).days == 7


def test_relevance_mode_uses_everything_and_skips_top_headlines() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_everything.return_value = {
        "articles": [
            {
                **_article(
                    "https://example.com/relevant",
                    "Relevant",
                    "2026-02-26T09:00:00Z",
                ),
                "description": "The report describes Iran bombing developments",
            }
        ]
    }

    articles, used_fallback = news.get_articles_for_cli_keywords(
        "iran bombing", relevance=True
    )

    assert used_fallback is True
    assert len(articles) == 1
    assert articles[0].url == "https://example.com/relevant"
    api_mock.get_top_headlines.assert_not_called()
    kwargs = api_mock.get_everything.call_args.kwargs
    assert kwargs["sort_by"] == "relevancy"


def test_relevance_mode_filters_and_ranks_by_body_matches() -> None:
    news, api_mock = _news_with_mocked_api()
    api_mock.get_everything.return_value = {
        "articles": [
            {
                **_article(
                    "https://example.com/high-score",
                    "High Score",
                    "2026-02-22T09:00:00Z",
                ),
                "description": "Iran and bombing both mentioned here",
            },
            {
                **_article(
                    "https://example.com/low-score",
                    "Low Score",
                    "2026-02-27T09:00:00Z",
                ),
                "description": "Iran mentioned once",
            },
            {
                **_article(
                    "https://example.com/no-body-match",
                    "No Body Match",
                    "2026-02-28T09:00:00Z",
                ),
                "description": "Completely unrelated text",
                "content": "Still unrelated",
            },
        ]
    }

    articles, _ = news.get_articles_for_cli_keywords("iran,bombing", relevance=True)

    assert [a.url for a in articles] == [
        "https://example.com/high-score",
        "https://example.com/low-score",
    ]
