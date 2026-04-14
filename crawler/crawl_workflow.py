from crawler.domain.errors import UpstreamCrawlError
from crawler.services import crawl_service

crawl_url = crawl_service.crawl_url
fetch_page = crawl_service.fetch_page

__all__ = ["UpstreamCrawlError", "crawl_url", "fetch_page"]
