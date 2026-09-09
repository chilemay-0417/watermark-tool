import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZSH = shutil.which("zsh")


@unittest.skipUnless(ZSH, "Finder 入口需要 zsh")
class FinderEntrypointTests(unittest.TestCase):
    def run_entrypoint(self, script, *, fail=False, photo_count=1):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            fake_bin = base / "bin"
            fake_bin.mkdir()
            events = base / "events.jsonl"
            output = base / 'photo "quoted" 中文_watermark.jpg'
            fake_program = f"#!{sys.executable}\n" + '''import json
import os
import sys
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
source = sys.stdin.read() if args and args[0] == "-" else ""
with open(os.environ["FAKE_EVENTS"], "a") as stream:
    stream.write(json.dumps({"name": name, "args": args, "source": source}) + "\\n")
if name == "python":
    if args and args[0] == "-":
        if "make_default_output_path" in source:
            print(os.environ["FAKE_OUTPUT"])
    elif os.environ.get("FAKE_FAIL") == "1":
        sys.exit(1)
'''
            for name in ("python", "osascript", "open"):
                path = fake_bin / name
                path.write_text(fake_program)
                path.chmod(0o755)
            environment = {
                **os.environ,
                "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
                "WATERMARK_PYTHON_BIN": str(fake_bin / "python"),
                "TMPDIR": str(base),
                "FAKE_EVENTS": str(events), "FAKE_OUTPUT": str(output),
                "FAKE_FAIL": "1" if fail else "0",
            }
            result = subprocess.run(
                [ZSH, str(PROJECT_ROOT / script),
                 *[str(base / f'photo "quoted" 中文 {i}.jpg') for i in range(photo_count)]],
                env=environment, capture_output=True, text=True, timeout=20,
            )
            calls = [json.loads(line) for line in events.read_text().splitlines()]
            return result, calls, output.name

    def test_entrypoints_report_success_and_failure_with_correct_exit_status(self):
        for script in ("watermark_batch_each.sh", "watermark_combine_selected.sh"):
            for fail in (False, True):
                with self.subTest(script=script, fail=fail):
                    result, calls, _ = self.run_entrypoint(script, fail=fail)
                    self.assertEqual(result.returncode, 1 if fail else 0, result.stderr)
                    ui_calls = [call for call in calls if call["name"] == "osascript"]
                    self.assertEqual(len(ui_calls), 1)
                    self.assertIn("display dialog" if fail else "display notification",
                                  ui_calls[0]["source"])

    def test_batch_uses_one_render_process_for_all_photos(self):
        result, calls, _ = self.run_entrypoint("watermark_batch_each.sh", photo_count=3)
        self.assertEqual(result.returncode, 0)
        renders = [call for call in calls if call["name"] == "python"
                   and call["args"] and call["args"][0].endswith("layout.py")]
        self.assertEqual(len(renders), 1)
        self.assertEqual(renders[0]["args"][1:3], ["--batch", "--"])
        self.assertEqual(len(renders[0]["args"][3:]), 3)

    def test_quoted_unicode_filename_is_passed_as_data_to_applescript(self):
        result, calls, name = self.run_entrypoint("watermark_combine_selected.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        notification = next(call for call in calls if call["name"] == "osascript")
        self.assertIn(name, notification["args"][-1])
        self.assertNotIn(name, notification["source"])


if __name__ == "__main__":
    unittest.main()
