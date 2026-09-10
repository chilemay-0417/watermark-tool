"""Check Python discovery when Finder has no activated Conda environment."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SETUP = ROOT / 'scripts/finder_setup.zsh'


class PythonDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.user_home = self.root / 'user'
        self.user_home.mkdir()
        self.project = self.root / 'project'
        self.project.mkdir()
        self.environment = {**os.environ, 'PATH': '/usr/bin:/bin',
                            'SCRIPT_DIR': str(self.project)}
        for key in ('CONDA_PREFIX', 'CONDA_EXE', 'CONDA_PYTHON_EXE', 'WATERMARK_PYTHON_BIN'):
            self.environment.pop(key, None)

    def candidates(self):
        result = subprocess.run(
            ['/bin/zsh', '-c', 'source "$1"; watermark_python_candidates "$2"',
             'test', str(SETUP), str(self.user_home)],
            env=self.environment, capture_output=True, text=True, check=True,
        )
        return result.stdout.splitlines()

    def fake_python(self, *, pip=True):
        prefix = self.root / 'conda 中文 "quoted"'
        executable = prefix / 'bin/python3'
        executable.parent.mkdir(parents=True)
        capture = self.root / 'capture.json'
        executable.write_text(
            f'#!{sys.executable}\n'
            'import sys,json; from pathlib import Path\n'
            'if sys.argv[1] == "-c":\n'
            f'    raise SystemExit(0 if {pip!r} or sys.argv[-1] == "uninstall" else 2)\n'
            f'Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))\n'
        )
        executable.chmod(0o755)
        return prefix, executable, capture

    def run_setup(self, operation='install'):
        return subprocess.run(
            ['/bin/zsh', '-c', 'source "$1"; setup_finder "$2"',
             'test', str(SETUP), operation],
            env=self.environment, capture_output=True, text=True, timeout=15,
        )

    def test_unactivated_conda_registered_at_custom_path_is_discovered(self):
        registry = self.user_home / '.conda/environments.txt'
        registry.parent.mkdir()
        prefix = self.root / 'custom location 中文' / 'my conda'
        registry.write_bytes((str(prefix) + '\r\n' + str(prefix / 'envs/work')).encode())
        found = self.candidates()
        self.assertIn(str(prefix / 'bin/python3'), found)
        self.assertIn(str(prefix / 'envs/work/bin/python'), found)
        self.assertIn(str(self.user_home / 'miniconda3/bin/python'), found)
        self.assertEqual(found[0], 'python3')

    def test_conda_command_in_condabin_reveals_its_base_python(self):
        prefix = self.root / 'custom conda'
        executable = prefix / 'condabin/conda'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\nexit 0\n')
        executable.chmod(0o755)
        self.environment['PATH'] = str(executable.parent) + ':/usr/bin:/bin'
        self.assertIn(str(prefix / 'bin/python3'), self.candidates())

    def test_python_org_framework_is_discovered_without_path_symlinks(self):
        versions = self.root / 'Python.framework/Versions'
        executable = versions / '3.13/bin/python3'
        executable.parent.mkdir(parents=True)
        executable.touch()
        result = subprocess.run(
            ['/bin/zsh', '-c', 'source "$1"; watermark_python_candidates "$2" "$3"',
             'test', str(SETUP), str(self.user_home), str(versions)],
            env=self.environment, capture_output=True, text=True, check=True,
        )
        self.assertIn(str(executable), result.stdout.splitlines())

    def test_explicit_unsupported_python_does_not_fall_back(self):
        _, executable, capture = self.fake_python()
        executable.write_text('#!/bin/sh\nexit 1\n')
        self.environment['WATERMARK_PYTHON_BIN'] = str(executable)
        result = self.run_setup()
        self.assertEqual(result.returncode, 1)
        self.assertIn('未找到 Python 3.10', result.stderr)
        self.assertFalse(capture.exists())

    def test_conda_prefix_is_used_with_minimal_finder_path(self):
        prefix, _, capture = self.fake_python()
        self.environment['CONDA_PREFIX'] = str(prefix)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(capture.read_text()),
                         [str(self.project / 'scripts/install_finder.py')])

    def test_conda_python_hint_is_used_without_activation(self):
        _, executable, capture = self.fake_python()
        self.environment['CONDA_PYTHON_EXE'] = str(executable)
        result = self.run_setup()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(capture.exists())

    def test_missing_pip_is_explained_without_running_installer(self):
        _, executable, capture = self.fake_python(pip=False)
        self.environment['WATERMARK_PYTHON_BIN'] = str(executable)
        result = self.run_setup()
        self.assertEqual(result.returncode, 1)
        self.assertIn('缺少 pip', result.stderr)
        self.assertIn('conda install pip', result.stderr)
        self.assertFalse(capture.exists())
        result = self.run_setup('uninstall')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(capture.read_text())[-1], '--uninstall')
