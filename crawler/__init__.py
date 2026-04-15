from crawler.classification.topics import classify_page
from crawler.parsing.extract import parse_page
from crawler.services.batch_service import crawl_batch
from crawler.services.crawl_service import crawl_url, fetch_page
from crawler.services.deep_crawl_service import deep_crawl

__all__ = [
    "classify_page",
    "crawl_batch",
    "crawl_url",
    "deep_crawl",
    "fetch_page",
    "parse_page",
]
