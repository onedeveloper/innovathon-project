import logging
import os
import sys
from dotenv import load_dotenv

# Determine the root directory of the project
# Assumes this file is in /common and the root is one level up
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def setup_logging(logger_name: str = "MCP_Component"):
    """
    Configures logging for MCP components based on LOG_LEVEL in .env file.

    Args:
        logger_name: The name to use for the logger (e.g., 'gateway', 'datetime-server').
                     This helps identify the source of log messages.
    """
    # Load environment variables from .env file in the project root
    dotenv_path = os.path.join(PROJECT_ROOT, '.env')
    load_dotenv(dotenv_path=dotenv_path)

    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level_name, logging.INFO)

    # Define a consistent log format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure basic logging
    # Using stream=sys.stdout to ensure output goes to console
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        stream=sys.stdout # Explicitly set stream to stdout
    )

    # Get the specific logger for the component
    logger = logging.getLogger(logger_name)
    logger.setLevel(numeric_level) # Ensure the specific logger also respects the level

    # Optional: Prevent propagation if using multiple handlers later
    # logger.propagate = False

    # Test message to confirm setup (optional)
    # logger.info(f"Logging configured for {logger_name} with level {log_level_name}")

if __name__ == '__main__':
    # Example usage if run directly
    print(f"Project Root detected as: {PROJECT_ROOT}")
    setup_logging("TestLogger")
    logging.getLogger("TestLogger").debug("This is a debug message.")
    logging.getLogger("TestLogger").info("This is an info message.")
    logging.getLogger("TestLogger").warning("This is a warning message.")
    logging.getLogger("TestLogger").error("This is an error message.")