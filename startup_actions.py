import logging
import subprocess
from actions.open_app import open_app

logger = logging.getLogger("startup_actions")

def main():
    logger.info("Running automatic actions...")
    open_app({"app_name": "Claude"})
    logger.info("Automatic actions completed.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
