from crawler.app_factory import create_app
from crawler.infrastructure.cache import cache
from crawler.services.batch_service import crawl_batch

app = create_app()
