"""Exercise installation transactions and real Automator argument delivery in temporary folders."""

import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('install_finder', ROOT / 'scripts/install_finder.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class FinderInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / 'project 中文 "quote" \' $x `test`'
        self.project.mkdir()
        for _, script, _ in installer.ACTIONS:
            (self.project / script).write_text('printf "%s\\n" "$@"\n')
        self.services = self.root / 'Services'
        self.backups = self.root / 'Backups'

    def install(self):
        return installer.install_workflows(self.project, self.services, self.backups)

    def test_plists_filter_finder_images_and_quote_multiple_paths(self):
        files = ['photo 中文.jpg', 'a "quote" $HOME `id`.png', '-dash.jpg']
        for workflow in self.install():
            contents = workflow / 'Contents'
            info = plistlib.loads((contents / 'Info.plist').read_bytes())
            document = plistlib.loads((contents / 'document.wflow').read_bytes())
            service = info['NSServices'][0]
            self.assertEqual(service['NSSendFileTypes'], ['public.image'])
            self.assertEqual(service['NSRequiredContext']['NSApplicationIdentifier'],
                             'com.apple.finder')
            parameters = document['actions'][0]['action']['ActionParameters']
            self.assertEqual(parameters['inputMethod'], 1)
            result = subprocess.run(
                ['/bin/zsh', '-c', parameters['COMMAND_STRING'], 'test', *files],
                capture_output=True, text=True, check=True, timeout=10,
            )
            self.assertEqual(result.stdout.splitlines(), files)

    def test_reinstall_updates_moved_project_and_uninstall_restores_existing_action(self):
        self.services.mkdir()
        previous = self.services / '添加水印.workflow'
        previous.mkdir()
        (previous / 'custom-data').write_text('user workflow')
        unrelated = self.services / '批量加水印.workflow'
        unrelated.mkdir()
        self.install()
        moved = self.root / 'moved project'
        self.project.rename(moved)
        self.project = moved
        self.install()
        self.assertEqual(len(list(self.backups.glob('*/*.workflow'))), 1)
        document = plistlib.loads((previous / 'Contents/document.wflow').read_bytes())
        command = document['actions'][0]['action']['ActionParameters']['COMMAND_STRING']
        self.assertIn(str(moved), command)
        removed = installer.uninstall_workflows(self.services, self.backups)
        self.assertEqual(len(removed), 2)
        self.assertEqual((previous / 'custom-data').read_text(), 'user workflow')
        self.assertTrue(unrelated.is_dir())
        self.assertEqual(installer.uninstall_workflows(self.services, self.backups), [])

    def test_migration_failure_rolls_back_unified_and_legacy_workflows(self):
        self.services.mkdir()
        for name, _, _ in installer.ACTIONS:
            target = self.services / f'{name}.workflow'
            target.mkdir()
            (target / 'custom-data').write_text(name)
        legacy = self.services / '批量加水印.workflow'
        (legacy / 'Contents').mkdir(parents=True)
        info, document = installer.workflow_documents(
            self.project, '批量加水印', 'watermark_batch_each.sh', 'batch',
        )
        (legacy / 'Contents/Info.plist').write_bytes(plistlib.dumps(info))
        (legacy / 'Contents/document.wflow').write_bytes(plistlib.dumps(document))
        original_rename = Path.rename

        def rename(source, destination):
            if source == legacy:
                raise OSError('simulated disk failure')
            return original_rename(source, destination)

        with patch.object(Path, 'rename', rename), self.assertRaises(OSError):
            self.install()
        for name, _, _ in installer.ACTIONS:
            self.assertEqual((self.services / f'{name}.workflow/custom-data').read_text(), name)
        self.assertTrue(legacy.is_dir())
        self.assertFalse(list(self.services.glob('.watermark-*')))

    def test_install_retires_old_entries_and_keeps_both_actions_after_reinstall(self):
        self.services.mkdir()
        for name, script, kind in installer.LEGACY_ACTIONS:
            contents = self.services / f'{name}.workflow/Contents'
            contents.mkdir(parents=True)
            info, document = installer.workflow_documents(self.project, name, script, kind)
            # Simulate old hand-created workflows without our ownership marker.
            info.pop(installer.MANAGED_KEY)
            parameters = document['actions'][0]['action']['ActionParameters']
            parameters['COMMAND_STRING'] = parameters['COMMAND_STRING'].splitlines()[-1]
            (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
            (contents / 'document.wflow').write_bytes(plistlib.dumps(document))
        self.install()
        self.install()
        self.assertEqual({path.name for path in self.services.glob('*.workflow')},
                         {'添加水印.workflow', '批量添加水印.workflow'})
        self.assertEqual(
            len(list(self.backups.glob('*/*.workflow'))), len(installer.LEGACY_ACTIONS),
        )
        installer.uninstall_workflows(self.services, self.backups)
        self.assertEqual(list(self.services.glob('*.workflow')), [])

    def test_upgrade_preserves_original_backup_across_action_kind_change(self):
        previous = self.services / '添加水印.workflow'
        previous.mkdir(parents=True)
        (previous / 'custom-data').write_text('original user workflow')
        old_actions = (
            ('添加水印', 'watermark_batch_each.sh', 'batch'),
            ('合成水印照片', 'watermark_combine_selected.sh', 'combine'),
        )
        with (patch.object(installer, 'ACTIONS', old_actions),
              patch.object(installer, 'LEGACY_ACTIONS', ())):
            self.install()
        self.install()
        self.install()
        self.assertEqual({path.name for path in self.services.glob('*.workflow')},
                         {'添加水印.workflow', '批量添加水印.workflow'})
        self.assertIsNotNone(installer.managed_info(previous, 'combine'))
        self.assertEqual(len(list(self.backups.glob('*/*.workflow'))), 2)
        self.assertEqual(len(installer.uninstall_workflows(self.services, self.backups)), 2)
        self.assertEqual((previous / 'custom-data').read_text(), 'original user workflow')
        self.assertFalse((self.services / '合成水印照片.workflow').exists())

    def test_upgrade_from_batch_only_changes_behavior_and_adds_batch_action(self):
        with patch.object(installer, 'ACTIONS', (
            ('添加水印', 'watermark_batch_each.sh', 'batch'),
        )):
            self.install()
        self.install()
        self.install()
        self.assertEqual({path.name for path in self.services.glob('*.workflow')},
                         {'添加水印.workflow', '批量添加水印.workflow'})
        document = plistlib.loads(
            (self.services / '添加水印.workflow/Contents/document.wflow').read_bytes(),
        )
        self.assertIn('watermark_combine_selected.sh',
                      document['actions'][0]['action']['ActionParameters']['COMMAND_STRING'])
        self.assertEqual(list(self.backups.glob('*/*.workflow')), [])
        self.assertEqual(len(installer.uninstall_workflows(self.services, self.backups)), 2)
        self.assertEqual(list(self.services.glob('*.workflow')), [])

    def test_uninstall_keeps_current_action_when_backup_restore_fails(self):
        self.services.mkdir()
        previous = self.services / '添加水印.workflow'
        previous.mkdir()
        self.install()
        original_rename = Path.rename

        def rename(source, destination):
            if source.is_relative_to(self.backups):
                raise OSError('cannot restore')
            return original_rename(source, destination)

        with patch.object(Path, 'rename', rename), self.assertRaises(OSError):
            installer.uninstall_workflows(self.services, self.backups)
        self.assertIsNotNone(installer.managed_info(previous, 'combine'))

    def test_symlink_conflict_never_replaces_external_directory(self):
        self.services.mkdir()
        external = self.root / 'external'
        external.mkdir()
        (self.services / '添加水印.workflow').symlink_to(external, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.install()
        self.assertTrue(external.exists())
        self.assertEqual(installer.uninstall_workflows(self.services, self.backups), [])

    def test_uninstall_does_not_restore_backup_outside_backup_directory(self):
        workflow = self.install()[0]
        path = workflow / 'Contents/Info.plist'
        info = plistlib.loads(path.read_bytes())
        external = self.root / workflow.name
        external.mkdir()
        info[installer.PREVIOUS_KEY] = str(external)
        path.write_bytes(plistlib.dumps(info))
        with self.assertRaises(ValueError):
            installer.uninstall_workflows(self.services, self.backups)
        self.assertTrue(workflow.is_dir())
        self.assertTrue(external.is_dir())

    def test_dependency_failure_does_not_change_services(self):
        with (patch.object(installer.sys, 'platform', 'darwin'),
              patch.object(installer, 'ensure_environment', side_effect=RuntimeError('pip')),
              patch.object(installer, 'install_workflows') as install,
              self.assertRaises(RuntimeError)):
            installer.main([])
        install.assert_not_called()

    def test_workflow_keeps_selected_python_with_special_path_characters(self):
        selected = str(self.root / 'Python 中文 "quote" $x `test`' / 'python3')
        script = self.project / installer.ACTIONS[0][1]
        script.write_text('printf "%s\\n" "$WATERMARK_PYTHON_BIN"\n')
        with patch.object(installer.sys, 'executable', selected):
            _, document = installer.workflow_documents(self.project, *installer.ACTIONS[0])
        command = document['actions'][0]['action']['ActionParameters']['COMMAND_STRING']
        result = subprocess.run(['/bin/zsh', '-c', command],
                                env={**os.environ, 'WATERMARK_PYTHON_BIN': '/wrong/python'},
                                capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), selected)

    def test_explicit_unavailable_python_does_not_fall_back(self):
        setup = ROOT / 'scripts/finder_setup.zsh'
        common = ROOT / 'scripts/finder_common.zsh'
        for source, invocation in ((setup, 'setup_finder install'),
                                   (common, 'find_python_bin')):
            with self.subTest(script=source.name):
                result = subprocess.run(
                    ['/bin/zsh', '-c', 'source "$1"; ' + invocation, 'test', str(source)],
                    env={**os.environ, 'WATERMARK_PYTHON_BIN': '/missing/python',
                         'PYTHON_BIN': '/missing/python', 'SCRIPT_DIR': str(ROOT)},
                    capture_output=True, text=True, timeout=10,
                )
                self.assertEqual(result.returncode, 1)

    def test_uninstall_does_not_need_image_dependencies(self):
        with (patch.object(installer.sys, 'platform', 'darwin'),
              patch.object(installer, 'ensure_environment') as setup,
              patch.object(installer, 'uninstall_workflows', return_value=[]),
              patch.object(installer, 'refresh_services')):
            installer.main(['--uninstall'])
        setup.assert_not_called()

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS required')
    def test_double_click_launchers_find_python_and_forward_operation(self):
        (self.project / 'scripts').mkdir()
        shutil.copy(ROOT / 'scripts/finder_setup.zsh', self.project / 'scripts')
        capture = self.root / 'bootstrap.json'
        fake = self.root / 'python3'
        fake.write_text(f'#!{sys.executable}\n' +
                        'import json,sys; from pathlib import Path\n'
                        'if sys.argv[1] != "-c":\n'
                        f'    Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))\n')
        fake.chmod(0o755)
        for launcher, explicit in (('右键操作安装.command', True),
                                   ('右键操作卸载.command', True),
                                   ('右键操作安装.command', False)):
            shutil.copy(ROOT / launcher, self.project / launcher)
            environment = {**os.environ, 'PATH': str(self.root) + os.pathsep + os.environ['PATH']}
            environment.pop('WATERMARK_PYTHON_BIN', None)
            if explicit:
                environment['WATERMARK_PYTHON_BIN'] = str(fake)
            result = subprocess.run(
                ['/bin/zsh', str(self.project / launcher)],
                env=environment,
                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            expected = [str(self.project / 'scripts/install_finder.py')]
            if launcher == '右键操作卸载.command':
                expected.append('--uninstall')
            self.assertEqual(json.loads(capture.read_text()), expected)

    @unittest.skipUnless(sys.platform == 'darwin', 'macOS required')
    def test_actions_export_single_batch_and_combined_photos(self):
        from PIL import Image

        photos = [self.root / name for name in ('single 中文.png', 'first.png', 'second.png')]
        for photo in photos:
            Image.new('RGB', (200, 240), (50, 100, 150)).save(photo)
        fake_bin = self.root / 'bin'
        fake_bin.mkdir()
        for name in ('osascript', 'open'):
            stub = fake_bin / name
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)
        cases = (
            (0, [photos[0]], {'single 中文_watermark.jpg'}),
            (0, photos[1:], {'first_second_watermark.jpg'}),
            (1, photos[1:], {'first_watermark.jpg', 'second_watermark.jpg'}),
        )
        for action_index, inputs, expected in cases:
            with self.subTest(action=installer.ACTIONS[action_index][0], count=len(inputs)):
                before = set(self.root.glob('*_watermark.jpg'))
                _, document = installer.workflow_documents(ROOT, *installer.ACTIONS[action_index])
                command = document['actions'][0]['action']['ActionParameters']['COMMAND_STRING']
                result = subprocess.run(
                    ['/bin/zsh', '-c', command, 'test', *map(str, inputs)],
                    env={**os.environ,
                         'PATH': str(fake_bin) + os.pathsep + os.environ['PATH'],
                         'WATERMARK_FINDER_PROGRESS': '0'},
                    capture_output=True, text=True, timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                created = set(self.root.glob('*_watermark.jpg')) - before
                self.assertEqual({p.name for p in created}, expected)
                for output in created:
                    with Image.open(output) as image:
                        image.verify()
        self.assertEqual(len(list(self.root.glob('*_watermark.jpg'))), 4)
        self.assertTrue(all(photo.exists() for photo in photos))

    @unittest.skipUnless(sys.platform == 'darwin' and shutil.which('automator'), 'macOS required')
    def test_generated_workflow_runs_in_native_automator(self):
        photo = self.root / 'photo 中文 "quoted".jpg'
        photo.write_text('fixture pathname only')
        capture = self.project / 'arguments.json'
        # The generated action invokes this inert script, never a user's workflow or photographs.
        import shlex
        script = ('exec ' + shlex.quote(sys.executable) + ' -c ' + shlex.quote(
            'import json,sys; from pathlib import Path; '
            f'Path({str(capture)!r}).write_text(json.dumps(sys.argv[1:]))'
        ) + ' "$@"\n')
        (self.project / installer.ACTIONS[0][1]).write_text(script)
        workflow = self.install()[0]
        result = subprocess.run(['/usr/bin/automator', '-i', str(photo), str(workflow)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(capture.read_text()), [str(photo)])
