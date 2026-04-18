from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from main import app
from crawler.parsing.extract import parse_page
from crawler.domain.fetch_result import FetchResult
from crawler.classification.topics import _tokenize, classify_page

SAMPLE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Best Python Tutorials for Developers</title>
  <meta name="description" content="Learn Python programming with hands-on tutorials.">
  <meta name="keywords" content="python, programming, tutorial, developer">
  <meta name="author" content="Jane Doe">
  <meta name="robots" content="index, follow">
  <link rel="canonical" href="https://example.com/python-tutorial">
  <meta property="og:title" content="Python Tutorial">
  <meta property="og:description" content="Learn Python fast.">
  <meta property="og:image" content="https://example.com/img/python.jpg">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="Python Tutorial">
</head>
<body>
  <h1>Python Programming for Developers</h1>
  <h2>Getting Started</h2>
  <p>Python is a powerful programming language used in software development,
     data science, and machine learning. Developers love it for its clean syntax.</p>
  <h2>Advanced Topics</h2>
  <p>Explore algorithms, database access, and cloud APIs with Python.</p>
  <a href="/another-page">Internal link</a>
  <a href="https://other.com/article">External link</a>
  <img src="/img/banner.png" alt="Python banner">
</body>
</html>"""


def _fetch_fixture(html: str = SAMPLE_HTML, url: str = "https://example.com/python-tutorial"):
    return FetchResult(
        url=url,
        final_url=url,
        status_code=200,
        html=html,
        content_type="text/html; charset=utf-8",
    )


class TestParser:
    def setup_method(self):
        self.meta = parse_page(_fetch_fixture())

    def test_title(self):
        assert self.meta.title == "Best Python Tutorials for Developers"

    def test_description(self):
        assert "Python programming" in (self.meta.description or "")

    def test_keywords(self):
        assert "python" in (self.meta.keywords or "")

    def test_author(self):
        assert self.meta.author == "Jane Doe"

    def test_robots(self):
        assert self.meta.robots == "index, follow"

    def test_language(self):
        assert self.meta.language == "en"

    def test_charset(self):
        assert (self.meta.charset or "").upper() == "UTF-8"

    def test_canonical(self):
        assert self.meta.canonical == "https://example.com/python-tutorial"

    def test_og_tags(self):
        assert self.meta.og.get("title") == "Python Tutorial"
        assert "python.jpg" in self.meta.og.get("image", "")

    def test_twitter_tags(self):
        assert self.meta.twitter.get("card") == "summary_large_image"

    def test_headings(self):
        assert "Python Programming for Developers" in self.meta.headings.get("h1", [])
        assert len(self.meta.headings.get("h2", [])) == 2

    def test_links(self):
        hrefs = [l.href for l in self.meta.links]
        assert any("another-page" in h for h in hrefs)
        assert any("other.com" in h for h in hrefs)

    def test_external_links(self):
        assert any(l.is_external and "other.com" in l.href for l in self.meta.links)

    def test_images(self):
        assert len(self.meta.images) == 1
        assert "banner.png" in self.meta.images[0].src
        assert self.meta.images[0].alt == "Python banner"

    def test_body_text_not_empty(self):
        assert len(self.meta.body_text) > 50

    def test_word_count(self):
        assert self.meta.word_count > 10

    def test_empty_html(self):
        meta = parse_page(_fetch_fixture(html="<html></html>"))
        assert meta.title is None
        assert meta.body_text == ""


class TestClassifier:
    def setup_method(self):
        self.meta = classify_page(parse_page(_fetch_fixture()))

    def test_technology_in_topics(self):
        assert "technology" in self.meta.topics

    def test_education_in_topics(self):
        assert "education" in self.meta.topics

    def test_topics_sorted_by_score(self):
        scores = list(self.meta.topic_scores.values())
        assert scores == sorted(scores, reverse=True)

    def test_category_not_unknown(self):
        assert self.meta.page_category != "unknown"

    def test_no_zero_score_topics(self):
        assert all(s > 0 for s in self.meta.topic_scores.values())


class TestTokenize:
    def test_bigrams(self):
        assert "machine learning" in _tokenize("machine learning is great")

    def test_trigrams(self):
        assert "artificial intelligence ai" in _tokenize("artificial intelligence ai")

    def test_case_insensitive(self):
        tokens = _tokenize("Python PROGRAMMING")
        assert "python" in tokens and "programming" in tokens


client = TestClient(app)


class TestAPI:
    def test_index(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")
        assert "Web Crawler" in r.text

    def test_health(self):
        assert client.get("/health").json()["status"] == "ok"

    def test_crawl_success(self):
        with patch("crawler.services.crawl_service.fetch_page", return_value=_fetch_fixture()):
            r = client.post("/crawl", json={"url": "https://example.com/python-tutorial"})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "Best Python Tutorials for Developers"
        assert isinstance(data["topics"], list)
        assert data["page_category"] != "unknown"

    def test_crawl_network_error(self):
        err = FetchResult("https://bad.example.com", "https://bad.example.com", 0, "", "", error="Connection refused")
        with patch("crawler.services.crawl_service.fetch_page", return_value=err):
            assert client.post("/crawl", json={"url": "https://bad.example.com"}).status_code == 502

    def test_crawl_404(self):
        not_found = FetchResult(
            "https://example.com/gone",
            "https://example.com/gone",
            404,
            "<html><body>Not Found</body></html>",
            "text/html",
        )
        with patch("crawler.services.crawl_service.fetch_page", return_value=not_found):
            assert client.post("/crawl", json={"url": "https://example.com/gone"}).status_code == 404

    def test_invalid_url(self):
        assert client.post("/crawl", json={"url": "not-a-url"}).status_code == 422

    def test_response_schema(self):
        with patch("crawler.services.crawl_service.fetch_page", return_value=_fetch_fixture()):
            data = client.post("/crawl", json={"url": "https://example.com/python-tutorial"}).json()
        for field in [
            "url",
            "final_url",
            "status_code",
            "title",
            "description",
            "og",
            "twitter",
            "headings",
            "links",
            "images",
            "body_text",
            "word_count",
            "page_category",
            "topics",
            "topic_scores",
        ]:
            assert field in data, f"missing {field}"


INTEGRATION = pytest.mark.skipif(
    os.getenv("RUN_INTEGRATION") != "1",
    reason="set RUN_INTEGRATION=1 for live HTTP",
)


@INTEGRATION
def test_live_wikipedia():
    r = client.post("/crawl", json={"url": "https://en.wikipedia.org/wiki/Python_(programming_language)"})
    assert r.status_code == 200
    data = r.json()
    assert data["title"] is not None
    assert "technology" in data["topics"] or "science" in data["topics"]


@INTEGRATION
def test_live_hn():
    r = client.post("/crawl", json={"url": "https://news.ycombinator.com"})
    assert r.status_code == 200
    assert len(r.json()["links"]) > 0
