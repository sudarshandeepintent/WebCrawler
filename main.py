# entry point — uvicorn needs to find `app` at module level, so I import
# everything here and let create_app() do the actual wiring.
# keeping this file tiny makes it easy to swap the factory later if needed.

from crawler.app_factory import create_app
from crawler.infrastructure.cache import cache
from crawler.services.batch_service import crawl_batch

app = create_app()
