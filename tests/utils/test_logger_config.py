import logging
import sys
import pytest
from tracelet.utils.logger_config import ColoredFormatter, setup_logger

def test_colored_formatter_formats():
    formatter = ColoredFormatter()
    # Create a dummy record
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="test message",
        args=(),
        exc_info=None
    )

    formatted = formatter.format(record)

    # Check if the colors are present (BLUE for INFO)
    assert ColoredFormatter.BLUE in formatted
    assert "test message" in formatted
    assert ColoredFormatter.RESET in formatted

def test_colored_formatter_different_levels():
    formatter = ColoredFormatter()

    levels = [
        (logging.DEBUG, ColoredFormatter.GREEN),
        (logging.INFO, ColoredFormatter.BLUE),
        (logging.WARNING, ColoredFormatter.YELLOW),
        (logging.ERROR, ColoredFormatter.RED),
        (logging.CRITICAL, ColoredFormatter.BOLD_RED),
    ]

    for level, color in levels:
        record = logging.LogRecord(
            name="test_logger",
            level=level,
            pathname="test.py",
            lineno=10,
            msg=f"test message {level}",
            args=(),
            exc_info=None
        )
        formatted = formatter.format(record)
        assert color in formatted
        assert f"test message {level}" in formatted
        assert ColoredFormatter.RESET in formatted

def test_setup_logger_initialization():
    # Use a fresh logger for testing if possible, but setup_logger uses "tracelet"
    # To test it properly, we might need to clear existing handlers first
    logger = logging.getLogger("tracelet")
    original_handlers = logger.handlers[:]
    logger.handlers = []

    try:
        new_logger = setup_logger()

        assert new_logger.name == "tracelet"
        assert new_logger.level == logging.INFO
        assert len(new_logger.handlers) == 1
        assert isinstance(new_logger.handlers[0], logging.StreamHandler)
        assert new_logger.handlers[0].stream == sys.stdout
        assert isinstance(new_logger.handlers[0].formatter, ColoredFormatter)
        assert new_logger.propagate is False

    finally:
        # Restore handlers
        logger.handlers = original_handlers

def test_setup_logger_idempotency():
    logger = logging.getLogger("tracelet")
    original_handlers = logger.handlers[:]
    logger.handlers = []

    try:
        # First call
        setup_logger()
        assert len(logger.handlers) == 1

        # Second call
        setup_logger()
        assert len(logger.handlers) == 1

    finally:
        logger.handlers = original_handlers
