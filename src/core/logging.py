from loguru import logger
import sys

# Remove default handler
logger.remove()

# Add custom handler with rich formatting
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    colorize=True
)

# Add file handler for errors
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="7 days",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}"
)

def get_logger(name: str):
    return logger.bind(name=name)
