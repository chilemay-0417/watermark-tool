"""Compatibility entry point for Finder quick actions.

The implementation lives in ``src/watermark_tool``. Keeping this file in the
project root avoids breaking existing Automator / Finder workflows that call
``layout.py`` directly.
"""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from watermark_tool.cli import (  # noqa: E402
    build_parser,
    config_from_args,
    main,
    make_output_path_from_original,
    parse_bool,
    run,
)
from watermark_tool.config import *  # noqa: F401,F403,E402
from watermark_tool.drawing import *  # noqa: F401,F403,E402
from watermark_tool.exif_gps import *  # noqa: F401,F403,E402
from watermark_tool.brands import *  # noqa: F401,F403,E402
from watermark_tool.assets import *  # noqa: F401,F403,E402
from watermark_tool.layout import *  # noqa: F401,F403,E402
from watermark_tool.annotations import *  # noqa: F401,F403,E402
from watermark_tool.renderer import *  # noqa: F401,F403,E402
from watermark_tool.utils import warn  # noqa: F401,E402


if __name__ == "__main__":
    run()
