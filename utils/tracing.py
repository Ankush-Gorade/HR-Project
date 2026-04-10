"""
utils/tracing.py
Simple logger and trace decorator for all agents.
"""

import logging
import sys
import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given module name."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s → %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(console_handler)

    # File handler
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s → %(message)s"
    ))
    logger.addHandler(file_handler)

    return logger


def trace_agent(agent_name: str):
    """Decorator that logs entry/exit for every agent function call."""
    import time

    def decorator(func: Callable) -> Callable:
        logger = get_logger(agent_name)

        @wraps(func)
        def wrapper(state: dict, *args, **kwargs) -> Any:
            start = time.perf_counter()
            logger.info(f"▶ Starting | input keys: {list(state.keys())}")
            try:
                result = func(state, *args, **kwargs)
                elapsed = time.perf_counter() - start
                out_keys = list(result.keys()) if isinstance(result, dict) else "non-dict"
                logger.info(f"✔ Completed in {elapsed:.2f}s | output keys: {out_keys}")
                return result
            except Exception as exc:
                elapsed = time.perf_counter() - start
                logger.error(f"✘ Failed after {elapsed:.2f}s → {type(exc).__name__}: {exc}")
                raise

        return wrapper
    return decorator


def configure_langsmith() -> bool:
    """Set up LangSmith tracing if enabled."""
    api_key = os.getenv("LANGCHAIN_API_KEY", "")
    tracing = os.getenv("LANGCHAIN_TRACING_V2", "false").lower() == "true"
    if not tracing or not api_key:
        return False
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    return True
