from contextlib import contextmanager
import logging
import os
from pathlib import Path
import tempfile
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


@contextmanager
def atomic_output_path(output_path):
    """Encode beside the destination; replace it only after a successful write."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".watermark-", suffix=output_path.suffix,
        dir=output_path.parent, delete=False,
    ) as temporary:
        temp_path = Path(temporary.name)
    try:
        yield temp_path
        os.replace(temp_path, output_path)
    finally:
        temp_path.unlink(missing_ok=True)


_LAST_PROGRESS_NOTIFICATION = float("-inf")


def progress(message):
    """Flush stage logs and optionally notify Finder; UI failure cannot fail an export."""
    import subprocess
    import time

    global _LAST_PROGRESS_NOTIFICATION
    info(message)
    if (os.environ.get("WATERMARK_FINDER_PROGRESS") != "1" or sys.platform != "darwin"
            or not LOGGER.isEnabledFor(logging.INFO) or LOGGER.disabled):
        return
    now = time.monotonic()
    if now - _LAST_PROGRESS_NOTIFICATION < 2:
        return
    _LAST_PROGRESS_NOTIFICATION = now
    script = ('on run argv\n'
              'display notification (item 1 of argv) with title "照片加水印"\n'
              'end run')
    try:
        subprocess.run(
            ["osascript", "-e", script, message],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
