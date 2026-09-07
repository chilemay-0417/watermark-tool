import logging
import sys


LOGGER = logging.getLogger("watermark_tool")


def configure_logging(quiet=False, verbose=False):
    """Configure CLI logging once, without taking over host applications."""
    if not LOGGER.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)

    if quiet:
        LOGGER.setLevel(logging.WARNING)
    elif verbose:
        LOGGER.setLevel(logging.DEBUG)
    else:
        LOGGER.setLevel(logging.INFO)

    LOGGER.propagate = False


configure_logging()


def info(message):
    LOGGER.info(message)


def error(message):
    LOGGER.error("错误：%s", message)


def warn(message):
    """统一输出警告信息到 stderr，避免和正常导出信息混在一起。"""
    LOGGER.warning("警告：%s", message)
