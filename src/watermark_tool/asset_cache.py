"""Cache small, fully prepared watermark assets; never cache source photographs."""

from collections import OrderedDict
from hashlib import sha256
import os
from pathlib import Path
import sys

import numpy as np
from PIL import Image, __version__ as pillow_version

from .color import SRGB_ICC
from .utils import atomic_output_path


_MEMORY = OrderedDict()
CACHE_VERSION = f"prepared-v1-{sys.platform}-{pillow_version}-{np.__version__}"


def cache_directory():
    override = os.environ.get("WATERMARK_CACHE_DIR")
    if override == "off":
        return None
    if override:
        return Path(override).expanduser()
    base = (Path.home() / "Library/Caches" if sys.platform == "darwin" else
            Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")))
    return base / "watermark-tool" / "assets"


def prepared_asset(path, height, kind, prepare):
    """Invalidate on asset contents, dimensions, processing version, or runtime changes."""
    directory = cache_directory()
    if directory is None:
        return prepare()
    digest = sha256(Path(path).read_bytes())
    suffix = Path(path).suffix.lower()
    digest.update(f"{CACHE_VERSION}:{height}:{kind}:{suffix}:{directory}".encode())
    key = digest.hexdigest()
    cached = _MEMORY.get(key)
    if cached is not None:
        _MEMORY.move_to_end(key)
        return cached.copy()
    filename = directory / f"{key}.png"
    try:
        with Image.open(filename) as image:
            if image.format != "PNG" or image.mode != "RGBA" or image.width != height:
                raise ValueError("Invalid prepared asset cache")
            cached = image.copy()
    except (OSError, ValueError, SyntaxError):
        cached = prepare()
        try:
            with atomic_output_path(filename) as temporary:
                cached.save(temporary, format="PNG", icc_profile=SRGB_ICC)
        except OSError:
            # A read-only or full cache must not prevent exporting a photo.
            pass
    _MEMORY[key] = cached
    if len(_MEMORY) > 32:
        _, old = _MEMORY.popitem(last=False)
        old.close()
    return cached.copy()
