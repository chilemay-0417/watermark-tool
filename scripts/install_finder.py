"""Install reversible, per-user Finder Quick Actions using only the standard library."""

import argparse
from datetime import datetime
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid
from xml.parsers.expat import ExpatError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANAGED_KEY = 'WatermarkToolManagedVersion'
PREVIOUS_KEY = 'WatermarkToolPreviousWorkflow'
ACTIONS = (
    ('添加水印', 'watermark_combine_selected.sh', 'combine'),
    ('批量添加水印', 'watermark_batch_each.sh', 'batch'),
)
LEGACY_ACTIONS = (
    ('照片加水印', 'watermark_batch_each.sh', 'batch'),
    ('批量加水印', 'watermark_batch_each.sh', 'batch'),
    ('合成水印照片', 'watermark_combine_selected.sh', 'combine'),
)


def workflow_documents(project, name, script, kind, previous=None):
    """Build the same plist structure used by Automator's Run Shell Script action."""
    info = {
        MANAGED_KEY: 1,
        'CFBundleIdentifier': f'org.watermark-tool.finder.{kind}',
        'NSServices': [{
            'NSBackgroundColorName': 'background', 'NSIconName': 'NSActionTemplate',
            'NSMenuItem': {'default': name}, 'NSMessage': 'runWorkflowAsService',
            'NSRequiredContext': {'NSApplicationIdentifier': 'com.apple.finder'},
            'NSSendFileTypes': ['public.image'],
        }],
    }
    if previous:
        info[PREVIOUS_KEY] = str(previous)
    command = (f'export WATERMARK_PYTHON_BIN={shlex.quote(sys.executable)}\n'
               f'exec /bin/zsh {shlex.quote(str(project / script))} "$@"')
    action = {
        'AMAccepts': {'Container': 'List', 'Optional': True,
                      'Types': ['com.apple.cocoa.string']},
        'AMProvides': {'Container': 'List', 'Types': ['com.apple.cocoa.string']},
        'AMActionVersion': '2.0.3', 'AMApplication': ['Automator'],
        'AMParameterProperties': {key: {} for key in
                                  ('COMMAND_STRING', 'CheckedForUserDefaultShell',
                                   'inputMethod', 'shell', 'source')},
        'ActionBundlePath': '/System/Library/Automator/Run Shell Script.action',
        'ActionName': 'Run Shell Script',
        'ActionParameters': {'COMMAND_STRING': command, 'CheckedForUserDefaultShell': True,
                             'inputMethod': 1, 'shell': '/bin/zsh', 'source': ''},
        'BundleIdentifier': 'com.apple.RunShellScript', 'CFBundleVersion': '2.0.3',
        'CanShowSelectedItemsWhenRun': False, 'CanShowWhenRun': True,
        'Category': ['AMCategoryUtilities'], 'Class Name': 'RunShellScriptAction',
        'InputUUID': str(uuid.uuid4()), 'OutputUUID': str(uuid.uuid4()),
        'UUID': str(uuid.uuid4()), 'UnlocalizedApplications': ['Automator'],
        'isViewVisible': 1,
    }
    finder = '/System/Library/CoreServices/Finder.app'
    metadata = {
        'applicationBundleID': 'com.apple.finder', 'applicationPath': finder,
        'applicationBundleIDsByPath': {finder: 'com.apple.finder'},
        'applicationPaths': [finder],
        'inputTypeIdentifier': 'com.apple.Automator.fileSystemObject.image',
        'outputTypeIdentifier': 'com.apple.Automator.nothing',
        'presentationMode': 15, 'processesInput': False,
        'serviceApplicationBundleID': 'com.apple.finder', 'serviceApplicationPath': finder,
        'serviceInputTypeIdentifier': 'com.apple.Automator.fileSystemObject.image',
        'serviceOutputTypeIdentifier': 'com.apple.Automator.nothing',
        'serviceProcessesInput': False, 'systemImageName': 'NSActionTemplate',
        'useAutomaticInputType': False,
        'workflowTypeIdentifier': 'com.apple.Automator.servicesMenu',
    }
    workflow = {'AMApplicationVersion': '2.10', 'AMDocumentVersion': '2',
                'actions': [{'action': action, 'isViewVisible': 1}],
                'connectors': {}, 'workflowMetaData': metadata}
    return info, workflow


def managed_info(workflow, kind):
    try:
        info = plistlib.loads((workflow / 'Contents/Info.plist').read_bytes())
    except (OSError, ValueError, plistlib.InvalidFileException, ExpatError):
        return None
    if (isinstance(info, dict) and info.get(MANAGED_KEY) == 1
            and info.get('CFBundleIdentifier') == f'org.watermark-tool.finder.{kind}'):
        return info
    return None


def is_legacy_workflow(workflow, script, kind):
    """Recognize this project's old single-shell-action workflows, never by name alone."""
    if workflow.is_symlink() or not workflow.is_dir():
        return False
    if managed_info(workflow, kind) is not None:
        return True
    try:
        document = plistlib.loads((workflow / 'Contents/document.wflow').read_bytes())
        actions = document['actions']
        if len(actions) != 1:
            return False
        action = actions[0]['action']
        if action['BundleIdentifier'] != 'com.apple.RunShellScript':
            return False
        tokens = shlex.split(action['ActionParameters']['COMMAND_STRING'])
        if tokens[:2] == ['exec', '/bin/zsh']:
            tokens = tokens[2:]
        return (len(tokens) == 2 and tokens[1] == '$@'
                and tokens[0].endswith('/' + script))
    except (OSError, ValueError, TypeError, KeyError, plistlib.InvalidFileException, ExpatError):
        return False


def install_workflows(project, services, backups):
    """Install single/combine and batch actions, retiring old aliases in one transaction."""
    project = project.resolve()
    for _, script, _ in ACTIONS:
        if not (project / script).is_file():
            raise FileNotFoundError(f'项目不完整，缺少：{script}')
    services.mkdir(parents=True, exist_ok=True)
    backup_group = backups / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    plans = []
    with tempfile.TemporaryDirectory(prefix='.watermark-install-', dir=services) as temporary:
        staging = Path(temporary)
        for name, script, kind in ACTIONS:
            target = services / f'{name}.workflow'
            if target.is_symlink() or (target.exists() and not target.is_dir()):
                raise ValueError(f'同名路径不是普通工作流程目录，请先移走：{target}')
            existing = managed_info(target, kind) if target.exists() else None
            if existing is None and name == '添加水印':
                # Older installers used this name for batch. Preserve its original backup
                # across the kind change so uninstall never revives our obsolete action.
                existing = managed_info(target, 'batch')
            previous = existing.get(PREVIOUS_KEY) if existing else None
            old = None
            if target.exists():
                old = ((staging / 'old') if existing else backup_group) / target.name
                if not existing:
                    previous = str(old)
            info, document = workflow_documents(project, name, script, kind, previous)
            staged = staging / 'new' / target.name
            contents = staged / 'Contents'
            contents.mkdir(parents=True)
            (contents / 'Info.plist').write_bytes(plistlib.dumps(info))
            (contents / 'document.wflow').write_bytes(plistlib.dumps(document))
            plans.append((target, staged, old))
        for name, script, kind in LEGACY_ACTIONS:
            target = services / f'{name}.workflow'
            if is_legacy_workflow(target, script, kind):
                plans.append((target, None, backup_group / target.name))
        changed = []
        try:
            for target, staged, old in plans:
                if old is not None:
                    old.parent.mkdir(parents=True, exist_ok=True)
                    target.rename(old)
                changed.append((target, old))
                if staged is not None:
                    staged.rename(target)
        except OSError:
            for target, old in reversed(changed):
                if target.exists():
                    shutil.rmtree(target)
                if old is not None:
                    old.rename(target)
            raise
    return [target for target, staged, _ in plans if staged is not None]


def uninstall_workflows(services, backups):
    """Remove only installer-owned actions, restoring any originally replaced workflow."""
    removed = []
    for name, _, kind in ACTIONS:
        target = services / f'{name}.workflow'
        if target.is_symlink():
            continue
        info = managed_info(target, kind)
        if info is None:
            continue
        previous = Path(info[PREVIOUS_KEY]) if info.get(PREVIOUS_KEY) else None
        if previous is not None:
            if (not previous.resolve().is_relative_to(backups.resolve())
                    or previous.name != target.name or previous.is_symlink()
                    or not previous.is_dir()):
                raise ValueError(f'原工作流程备份不可用，保留当前操作：{target}')
        with tempfile.TemporaryDirectory(prefix='.watermark-uninstall-', dir=services) as temporary:
            saved = Path(temporary) / target.name
            target.rename(saved)
            try:
                if previous is not None:
                    previous.rename(target)
            except OSError:
                saved.rename(target)
                raise
        removed.append(target)
    return removed


def ensure_environment(project):
    """Install dependencies into the selected existing Python without creating an environment."""
    python = sys.executable
    if sys.version_info < (3, 10):
        raise RuntimeError('需要 Python 3.10 或更新版本。')
    print(f'使用 Python：{python}', flush=True)
    print('正在检查并安装依赖（首次安装需要联网）…', flush=True)
    try:
        subprocess.run([python, '-m', 'pip', 'install', '--disable-pip-version-check',
                        '-r', str(project / 'requirements.txt')], check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            '依赖安装失败，尚未修改右键操作。请查看上方错误；'
            '若提示 externally-managed-environment 或权限不足，请改用 Python 官网的 '
            'macOS 安装包，并按 docs/usage.md 指定 Python 后重试。'
        ) from exc
    try:
        subprocess.run([str(python), '-c',
                        'import sys; sys.path.insert(0, "src"); '
                        'import watermark_tool, pillow_heif, pyspng'],
                       cwd=project, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            '依赖验证失败，尚未修改右键操作。请查看上方错误；'
            '请按 docs/usage.md 的安装排错说明处理后重试。'
        ) from exc


def refresh_services():
    try:
        subprocess.run(['/System/Library/CoreServices/pbs', '-update'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        print('操作已保存；菜单未刷新时请重新登录 macOS。', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args(argv)
    if sys.platform != 'darwin':
        parser.error('Finder 快速操作安装器仅支持 macOS。')
    services = Path.home() / 'Library/Services'
    backups = Path.home() / 'Library/Application Support/watermark-tool/finder-backups'
    if args.uninstall:
        paths = uninstall_workflows(services, backups)
        print(f'已卸载 {len(paths)} 个自动安装的操作；同名旧操作已恢复（如有）。')
        print('项目、照片、Python 环境及其他快速操作均保留。')
    else:
        ensure_environment(PROJECT_ROOT)
        paths = install_workflows(PROJECT_ROOT, services, backups)
        print('安装完成。在 Finder 选中一张或多张照片 → 右键 → 快速操作：')
        for path in paths:
            print(f'  {path.stem}')
        print('添加水印：单张直接加水印，多张合成为一张水印照片。')
        print('批量添加水印：给选中的照片逐张添加水印，分别保存成片。')
        print(f'同名旧操作及已移除的旧入口备份目录：{backups}')
        print('项目移动或改名后，请在新位置重新双击安装。')
    refresh_services()


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f'安装/卸载失败：{exc}', file=sys.stderr)
        sys.exit(1)
