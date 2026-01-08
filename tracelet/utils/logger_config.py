import logging
import sys

class ColoredFormatter(logging.Formatter):
    # ANSI escape codes for colors
    GREEN = "\x1b[38;2;0;255;0m"
    BLUE = "\x1b[34;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"


    LOG_FORMAT = "%(asctime)s - [%(name)s: %(levelname)s] - %(message)s"

    FORMATS = {
        logging.DEBUG: GREEN + LOG_FORMAT + RESET,
        logging.INFO: BLUE + LOG_FORMAT + RESET,
        logging.WARNING: YELLOW + LOG_FORMAT + RESET,
        logging.ERROR: RED + LOG_FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + LOG_FORMAT + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(fmt=log_fmt, datefmt='%Y-%m-%d %H:%M:%S')
        return formatter.format(record)

def setup_logger():
    """Configures the logger once and returns it."""
    logger = logging.getLogger("tracelet")
    
    # CRITICAL: Only add handlers if they don't exist yet
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredFormatter())
        
        logger.addHandler(console_handler)
        logger.propagate = False 
        
    return logger

logger = setup_logger()