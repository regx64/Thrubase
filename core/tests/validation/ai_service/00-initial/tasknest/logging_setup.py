import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger("tasknest")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level)
    return logger
