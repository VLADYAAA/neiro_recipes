# run_waitress.py - БЕЗ ИЗМЕНЕНИЙ!
from waitress import serve
from app11 import app
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if __name__ == '__main__':
    logger.info("Starting Waitress on port 5000...")
    serve(
    app,
    host='127.0.0.1',  # Только локальный!
    port=5001,         # <-- ИЗМЕНИТЕ НА 5001
    threads=6,
    connection_limit=1000,
    channel_timeout=180,
    ident='YandexRecipeBot'
	)
