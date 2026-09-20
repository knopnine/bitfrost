"""Centralized logging and crash diagnostics module for Bitfrost."""

import logging
from logging.handlers import RotatingFileHandler
import os
import subprocess
import sys
import threading
from typing import Optional

LOG_FILENAME = "bitfrost.log"
_logging_initialized = False


def get_log_path() -> str:
    """Returns absolute path to bitfrost.log next to executable or script."""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, LOG_FILENAME)


def setup_logging(level: int = logging.INFO) -> str:
    """Initializes rotating file and console logging with global exception hooks."""
    global _logging_initialized
    log_path = get_log_path()

    if _logging_initialized:
        return log_path

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Format
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(threadName)-16s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 1. Rotating File Handler (Max 5 MB, 2 backup files)
    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"[Logging] Warning: could not initialize file handler: {e}")

    # 2. Console Handler (for CLI & debugging)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 3. Global exception hook for main thread
    def _uncaught_exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.critical(
            "FATAL: Uncaught exception in main thread:",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = _uncaught_exception_handler

    # 4. Global exception hook for background threads (Python 3.8+)
    def _thread_exception_handler(args):
        if issubclass(args.exc_type, KeyboardInterrupt):
            return
        thread_name = args.thread.name if args.thread else "UnknownThread"
        root_logger.critical(
            f"FATAL: Uncaught exception in thread [{thread_name}]:",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_exception_handler

    _logging_initialized = True
    root_logger.info(f"=== Bitfrost Logging Started (Log path: {log_path}) ===")
    return log_path


def open_log_file() -> None:
    """Opens bitfrost.log in Windows Notepad or default text editor."""
    log_path = get_log_path()
    if not os.path.exists(log_path):
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("=== Bitfrost Log Initialized ===\n")
        except Exception:
            pass

    try:
        os.startfile(log_path)
    except Exception:
        subprocess.Popen(["notepad.exe", log_path], shell=True)


# Default module logger
logger = logging.getLogger("Bitfrost")
