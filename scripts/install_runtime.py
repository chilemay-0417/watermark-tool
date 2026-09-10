"""Install project-local packages and a user command with an existing Python."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import uuid

from scripts.python_runtime import dependency_dir


COMMAND_MARKER = '# watermark-tool managed command v1'
PATH_MARKER = '# watermark-tool command path'
PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'


def validate_dependencies(project, directory, svg=False):
    """Check fresh imports from the target directory, independent of user-site packages."""
    source = (
        'import sys; from pathlib import Path; '
        'root = Path(sys.argv[1]).resolve(); '
        'sys.path.insert(0, str(root)); sys.path.insert(0, sys.argv[2]); '
        'import PIL, numpy, pillow_heif, png, watermark_tool; '
        'assert all(Path(module.__file__).resolve().is_relative_to(root) '
        'for module in (PIL, numpy, pillow_heif, png)), "依赖未安装到工具目录"'
    )
    if svg:
        source += ('; import cairosvg; '
                   'assert Path(cairosvg.__file__).resolve().is_relative_to(root), '
                   '"SVG 依赖未安装到工具目录"; '
                   'cairosvg.svg2png(bytestring=b\'<svg xmlns="http://www.w3.org/2000/svg" '
                   'width="1" height="1"/>\')')
    subprocess.run([sys.executable, '-I', '-c', source, str(directory),
                    str(Path(project) / 'src')], check=True, capture_output=True, text=True)


def ensure_dependencies(project, svg=False):
    """Stage pip --target output, validate it, then replace this tool's dependencies."""
    project = Path(project).resolve()
    if sys.version_info < (3, 10):
        raise RuntimeError('需要 Python 3.10 或更新版本。')
    target = dependency_dir(project)
    if target.is_symlink() or target.parent.is_symlink():
        raise RuntimeError(f'依赖目录不能是符号链接：{target}')
    fingerprint = hashlib.sha256(
        (project / 'pyproject.toml').read_bytes()
        + (project / 'requirements.txt').read_bytes()
        + sys.version.encode()
    ).hexdigest()
    manifest = target / '.watermark-install.json'
    saved = {}
    try:
        saved = json.loads(manifest.read_text())
    except (OSError, ValueError):
        pass
    print(f'使用本机 Python：{sys.executable}', flush=True)
    if isinstance(saved, dict):
        svg = svg or bool(saved.get('svg', False))
    if (isinstance(saved, dict) and saved.get('fingerprint') == fingerprint
            and (not svg or saved.get('svg'))):
        try:
            validate_dependencies(project, target, svg)
        except (OSError, subprocess.SubprocessError):
            pass
        else:
            print('工具依赖已就绪。', flush=True)
            return target
    target.parent.mkdir(parents=True, exist_ok=True)
    print('正在安装工具依赖（首次安装需要联网）…', flush=True)
    with tempfile.TemporaryDirectory(prefix='.install-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'packages'
        staged.mkdir()
        package = str(project) + ('[svg]' if svg else '')
        # Override destination settings without discarding private indexes, proxies or CAs.
        environment = dict(os.environ, PIP_USER='0', PIP_PREFIX='', PIP_ROOT='',
                           PIP_REQUIRE_VIRTUALENV='0')
        try:
            subprocess.run([sys.executable, '-m', 'pip', 'install',
                            '--disable-pip-version-check', '--ignore-installed',
                            '--target', str(staged), package], check=True, env=environment)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                '依赖安装失败，已有右键操作和依赖保持不变。'
                '请检查上方的网络或下载错误，然后重新双击安装。'
            ) from exc
        try:
            validate_dependencies(project, staged, svg)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or '')[-3000:]
            raise RuntimeError(f'依赖验证失败，已有安装保持不变。\n{detail}') from exc
        (staged / '.watermark-install.json').write_text(
            json.dumps({'fingerprint': fingerprint, 'svg': svg}), encoding='utf-8',
        )
        previous = Path(temporary) / 'previous'
        if target.exists():
            target.rename(previous)
        try:
            staged.rename(target)
        except OSError:
            if previous.exists():
                previous.rename(target)
            raise
    return target


def command_text(project, python=None):
    python = python or sys.executable
    return (f'#!/bin/sh\n{COMMAND_MARKER}\n'
            f'exec {shlex.quote(str(python))} '
            f'{shlex.quote(str(Path(project).resolve() / "layout.py"))} "$@"\n')


def command_paths(home=None):
    home = Path.home() if home is None else Path(home)
    # Only consult ZDOTDIR for the real user, keeping injected test homes self-contained.
    shell_home = Path(os.environ.get('ZDOTDIR') or home) if home == Path.home() else home
    return home / '.local/bin/watermark-tool', shell_home / '.zshrc'


def validate_command_target(home=None):
    command, _ = command_paths(home)
    if command.is_symlink() or (command.exists() and (
            not command.is_file() or COMMAND_MARKER not in command.read_text())):
        raise RuntimeError(f'已有其他同名命令，请先备份再重试：{command}')


def atomic_text(path, text, mode):
    temporary = path.with_name(f'.{path.name}-{uuid.uuid4().hex}')
    try:
        temporary.write_text(text, encoding='utf-8')
        temporary.chmod(mode)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def install_command(project, home=None):
    """Register the launcher and PATH atomically, preserving existing shell configuration."""
    validate_command_target(home)
    command, shell_file = command_paths(home)
    shell_file = shell_file.resolve()  # Preserve a user's existing dotfile symlink.
    command.parent.mkdir(parents=True, exist_ok=True)
    shell_file.parent.mkdir(parents=True, exist_ok=True)
    shell_existed = shell_file.exists()
    original = shell_file.read_text() if shell_existed else ''
    shell_mode = shell_file.stat().st_mode & 0o777 if shell_existed else 0o644
    separator = '' if not original or original.endswith('\n') else '\n'
    addition = f'{separator}\n{PATH_MARKER}\n{PATH_LINE}\n'
    updated = original if PATH_LINE in original else original + addition
    if updated != original:
        if shell_existed:
            backup = shell_file.with_name(f'{shell_file.name}.watermark-backup')
            if not backup.exists():
                shutil.copy2(shell_file, backup)
        atomic_text(shell_file, updated, shell_mode)
    try:
        atomic_text(command, command_text(project), 0o755)
    except OSError:
        if updated != original:
            if shell_existed:
                atomic_text(shell_file, original, shell_mode)
            else:
                shell_file.unlink(missing_ok=True)
        raise
    return command


def is_managed_command(text):
    """Only recognize an intact launcher generated by this installer."""
    lines = text.splitlines()
    if len(lines) != 3 or lines[:2] != ['#!/bin/sh', COMMAND_MARKER]:
        return False
    try:
        tokens = shlex.split(lines[2])
    except ValueError:
        return False
    if (len(tokens) != 4 or tokens[0] != 'exec' or tokens[-1] != '$@'
            or not Path(tokens[2]).is_absolute() or Path(tokens[2]).name != 'layout.py'):
        return False
    return text == command_text(Path(tokens[2]).parent, python=tokens[1])


def without_managed_path(text):
    """Remove only unchanged, adjacent marker/PATH lines, preserving all other text."""
    lines = text.splitlines(keepends=True)
    kept = []
    index = 0
    while index < len(lines):
        if (lines[index].rstrip('\r\n') == PATH_MARKER and index + 1 < len(lines)
                and lines[index + 1].rstrip('\r\n') == PATH_LINE):
            index += 2
        else:
            kept.append(lines[index])
            index += 1
    return ''.join(kept)


def uninstall_command(home=None):
    """Remove our launcher and unused PATH block, retaining user edits and shared paths."""
    command, shell_file = command_paths(home)
    managed = False
    if command.is_file() and not command.is_symlink():
        try:
            managed = is_managed_command(command.read_text())
        except (OSError, UnicodeError):
            pass
    if (command.exists() or command.is_symlink()) and not managed:
        print(f'保留非托管或已修改的同名命令：{command}', flush=True)
        return False, False
    command_exists = command.exists()
    # The PATH addition may now be used by unrelated applications installed afterward.
    shared_bin = command.parent.exists() and any(
        entry != command for entry in command.parent.iterdir()
    )
    shell_file = shell_file.resolve()  # Preserve an existing dotfile symlink.
    original = shell_file.read_bytes().decode('utf-8') if shell_file.exists() else ''
    updated = original if shared_bin else without_managed_path(original)
    shell_mode = shell_file.stat().st_mode & 0o777 if shell_file.exists() else 0o644
    if updated != original:
        atomic_text(shell_file, updated, shell_mode)
    try:
        if command_exists:
            command.unlink()
    except OSError:
        if updated != original:
            atomic_text(shell_file, original, shell_mode)
        raise
    if shared_bin and PATH_MARKER in original:
        print('保留共用 PATH 设置：~/.local/bin 中还有其他命令。', flush=True)
    elif updated == original and PATH_MARKER in original:
        print('保留已修改的 PATH 设置，请按需手动清理。', flush=True)
    return command_exists, updated != original
