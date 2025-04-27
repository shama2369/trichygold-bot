import logging
import os
import time

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

logger.info("Minimal app started successfully!")

if __name__ == "__main__":
    try:
        PORT = int(os.getenv("PORT", 8080))
        logger.info(f"Using port: {PORT}")
        # Simulate a running server (we'll use a simple loop instead of a web server for now)
        while True:
            logger.info("Container is running...")
            time.sleep(60)
    except Exception as e:
        logger.error(f"Error in main block: {str(e)}")
        raise