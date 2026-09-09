"""Compare renderer revisions on the bundled samples, without GPS network requests."""
import argparse
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output-dir', type=Path, default=Path('output/benchmark'))
    parser.add_argument('--label', default='current')
    parser.add_argument('--iterations', type=int, default=3)
    args = parser.parse_args()
    if args.iterations < 1 or Path(args.label).name != args.label:
        parser.error('iterations must be positive and label must be a filename')
    root = args.project_root.resolve()
    sys.path.insert(0, str(root / 'src'))
    from watermark_tool.config import LayoutConfig
    from watermark_tool.renderer import make_canvas
    from watermark_tool.utils import LOGGER

    LOGGER.disabled = True
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cases = {
        'phone1': ['phone1.jpg'],
        'phone2': ['phone2.jpg'],
        'three': ['phone2.jpg', 'vertical1.jpg', 'vertical2.jpg'],
    }
    results = {}
    for name, photos in cases.items():
        paths = [root / 'samples' / filename for filename in photos]
        output = args.output_dir / f'{args.label}-{name}.jpg'
        with tempfile.TemporaryDirectory(prefix='watermark-bench-cache-') as cache:
            os.environ['WATERMARK_CACHE_DIR'] = cache
            timings = []
            for _ in range(args.iterations + 1):
                start = time.perf_counter()
                make_canvas(paths, output, LayoutConfig(include_gps_location=False))
                timings.append(time.perf_counter() - start)
        results[name] = {
            'first_call_seconds': timings[0],
            'repeat_seconds': timings[1:],
            'repeat_median_seconds': statistics.median(timings[1:]),
        }
        print(name, json.dumps(results[name]), flush=True)
    (args.output_dir / f'{args.label}.json').write_text(json.dumps(results, indent=2) + '\n')


if __name__ == '__main__':
    main()
