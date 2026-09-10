"""Exercise local package installation and command registration without global writes."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import install_runtime as runtime
from scripts.python_runtime import activate_project, dependency_dir


ROOT = Path(__file__).resolve().parents[1]


class LocalRuntimeTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / 'project 中文 "quote" $x `test`'
        self.project.mkdir()
        for name in ('pyproject.toml', 'requirements.txt'):
            (self.project / name).write_bytes((ROOT / name).read_bytes())
        self.home = self.root / 'user'
        self.home.mkdir()

    def install(self, **options):
        with patch.object(runtime.subprocess, 'run') as calls:
            result = runtime.ensure_dependencies(self.project, **options)
        return result, calls

    def test_uses_local_python_and_target_without_touching_existing_environment(self):
        existing = self.project / '.venv'
        existing.mkdir()
        (existing / 'user-data').write_text('keep')
        directory, calls = self.install()
        self.assertEqual(calls.call_count, 2)
        install = calls.call_args_list[0].args[0]
        self.assertEqual(install[:4], [sys.executable, '-m', 'pip', 'install'])
        self.assertIn('--target', install)
        self.assertIn('--ignore-installed', install)
        self.assertNotIn('--break-system-packages', install)
        self.assertNotIn('--user', install)
        staged = Path(install[install.index('--target') + 1])
        self.assertTrue(staged.is_relative_to(self.project / '.watermark-deps'))
        self.assertEqual(install[-1], str(self.project))
        self.assertTrue((directory / '.watermark-install.json').is_file())
        self.assertEqual((existing / 'user-data').read_text(), 'keep')
        self.assertEqual(list(self.home.iterdir()), [])

    def test_reuses_valid_dependencies_and_refreshes_changed_requirements(self):
        directory, _ = self.install()
        (directory / 'existing-data').write_text('keep')
        reused, calls = self.install()
        self.assertEqual(reused, directory)
        self.assertEqual(calls.call_count, 1)
        self.assertEqual(calls.call_args.args[0][1], '-I')
        self.assertTrue((directory / 'existing-data').is_file())
        with (self.project / 'requirements.txt').open('a') as stream:
            stream.write('\n# changed\n')
        _, calls = self.install()
        self.assertEqual(calls.call_count, 2)

    def test_pip_failure_preserves_previous_dependencies(self):
        directory, _ = self.install()
        marker = directory / 'user-data'
        marker.write_text('keep')
        # Invalidate the manifest so pip is attempted again.
        (self.project / 'pyproject.toml').write_text('changed')
        with (patch.object(runtime.subprocess, 'run', side_effect=
                           subprocess.CalledProcessError(1, ['pip'])),
              self.assertRaisesRegex(RuntimeError, '依赖安装失败')):
            runtime.ensure_dependencies(self.project)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertFalse(list(directory.parent.glob('.install-*')))

    def test_import_failure_preserves_previous_dependencies(self):
        directory, _ = self.install()
        marker = directory / 'user-data'
        marker.write_text('keep')
        (self.project / 'pyproject.toml').write_text('changed')
        failure = subprocess.CalledProcessError(1, ['python'], stderr='bad native library')
        with (patch.object(runtime.subprocess, 'run', side_effect=[None, failure]),
              self.assertRaisesRegex(RuntimeError, 'bad native library')):
            runtime.ensure_dependencies(self.project)
        self.assertEqual(marker.read_text(), 'keep')
        self.assertFalse(list(directory.parent.glob('.install-*')))

    def test_replacement_failure_restores_previous_dependencies(self):
        directory, _ = self.install()
        marker = directory / 'user-data'
        marker.write_text('keep')
        (self.project / 'pyproject.toml').write_text('changed')
        rename = Path.rename

        def fail_staged(source, destination):
            if source.name == 'packages' and destination == directory:
                raise OSError('cannot replace')
            return rename(source, destination)

        with (patch.object(Path, 'rename', fail_staged),
              patch.object(runtime.subprocess, 'run'), self.assertRaises(OSError)):
            runtime.ensure_dependencies(self.project)
        self.assertEqual(marker.read_text(), 'keep')

    def test_dependency_symlink_is_not_followed(self):
        external = self.root / 'external'
        external.mkdir()
        (self.project / '.watermark-deps').symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, '符号链接'):
            runtime.ensure_dependencies(self.project)
        self.assertEqual(list(external.iterdir()), [])

    def test_existing_svg_support_is_preserved_on_refresh(self):
        self.install(svg=True)
        (self.project / 'pyproject.toml').write_text('changed')
        _, calls = self.install()
        self.assertEqual(calls.call_args_list[0].args[0][-1], str(self.project) + '[svg]')

    def test_adding_svg_refreshes_a_valid_base_install(self):
        self.install()
        directory, calls = self.install(svg=True)
        self.assertEqual(calls.call_count, 2)
        self.assertEqual(calls.call_args_list[0].args[0][-1], str(self.project) + '[svg]')
        self.assertTrue(json.loads((directory / '.watermark-install.json').read_text())['svg'])

    def test_pip_destination_settings_do_not_escape_project(self):
        with patch.dict(os.environ, {'PIP_USER': '1', 'PIP_REQUIRE_VIRTUALENV': 'true',
                                    'PIP_PREFIX': '/unrelated', 'PIP_ROOT': '/unrelated',
                                    'PIP_INDEX_URL': 'https://example.invalid/simple'}):
            _, calls = self.install()
        environment = calls.call_args_list[0].kwargs['env']
        self.assertEqual(environment['PIP_USER'], '0')
        self.assertEqual(environment['PIP_REQUIRE_VIRTUALENV'], '0')
        self.assertEqual(environment['PIP_PREFIX'], '')
        self.assertEqual(environment['PIP_ROOT'], '')
        self.assertEqual(environment['PIP_INDEX_URL'], 'https://example.invalid/simple')

    def test_launcher_handles_special_paths_and_project_move(self):
        (self.project / 'layout.py').write_text(
            'import json,sys; print(json.dumps([__file__, *sys.argv[1:]]))\n',
        )
        command = runtime.install_command(self.project, home=self.home)
        photos = ['photo 中文.png', 'quote " $HOME `id`.jpg', '--help']
        result = subprocess.run([str(command), *photos], cwd=self.root,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [str(self.project / 'layout.py'), *photos])
        moved = self.root / 'moved project'
        self.project.rename(moved)
        runtime.install_command(moved, home=self.home)
        result = subprocess.run([str(command), '--help'], cwd=self.root,
                                capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [str(moved / 'layout.py'), '--help'])
        self.assertEqual(command.stat().st_mode & 0o777, 0o755)

    def test_shell_configuration_is_preserved_and_path_added_only_once(self):
        configuration = self.home / '.zshrc'
        original = '# 自己的配置\nexport MY_SETTING="keep"\n'
        configuration.write_text(original)
        runtime.install_command(self.project, home=self.home)
        runtime.install_command(self.project, home=self.home)
        self.assertTrue(configuration.read_text().startswith(original))
        self.assertEqual(configuration.read_text().count(runtime.PATH_LINE), 1)
        self.assertEqual((self.home / '.zshrc.watermark-backup').read_text(), original)

    def test_shell_configuration_symlink_and_zdotdir_are_preserved(self):
        settings = self.root / 'settings'
        settings.mkdir()
        actual = settings / 'real-zshrc'
        actual.write_text('# keep\n')
        (settings / '.zshrc').symlink_to(actual)
        with (patch.object(Path, 'home', return_value=self.home),
              patch.dict(os.environ, {'ZDOTDIR': str(settings)})):
            runtime.install_command(self.project)
        self.assertTrue((settings / '.zshrc').is_symlink())
        self.assertTrue(actual.read_text().startswith('# keep\n'))
        self.assertFalse((self.home / '.zshrc').exists())

    def test_command_write_failure_restores_shell_configuration(self):
        shell_file = self.home / '.zshrc'
        shell_file.write_text('# original\n')
        command = self.home / '.local/bin/watermark-tool'
        original_write = runtime.atomic_text

        def fail_command(path, text, mode):
            if path == command:
                raise OSError('simulated command write failure')
            original_write(path, text, mode)

        with (patch.object(runtime, 'atomic_text', side_effect=fail_command),
              self.assertRaises(OSError)):
            runtime.install_command(self.project, home=self.home)
        self.assertEqual(shell_file.read_text(), '# original\n')
        self.assertFalse(command.exists())

    def test_unrelated_command_is_never_overwritten(self):
        command = self.home / '.local/bin/watermark-tool'
        command.parent.mkdir(parents=True)
        command.write_text('my command')
        with self.assertRaisesRegex(RuntimeError, '同名命令'):
            runtime.install_command(self.project, home=self.home)
        self.assertEqual(command.read_text(), 'my command')
        self.assertFalse((self.home / '.zshrc').exists())

    def test_runtime_uses_live_source_and_matching_native_packages(self):
        source = self.project / 'src'
        source.mkdir()
        directory = dependency_dir(self.project)
        directory.mkdir(parents=True)
        (source / 'example_live_module.py').write_text('value = "live"\n')
        (directory / 'example_local_library.py').write_text('value = "local"\n')
        with patch.object(sys, 'path', [*sys.path, str(source)]):
            activate_project(self.project)
            self.assertEqual(sys.path[:2], [str(source), str(directory)])
            activate_project(self.project)
            self.assertEqual(sys.path.count(str(source)), 1)
            self.assertEqual(sys.path.count(str(directory)), 1)
