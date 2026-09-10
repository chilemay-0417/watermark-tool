"""Use the local interpreter with project dependencies; never create an interpreter environment."""

from pathlib import Path
import platform
import sys
import sysconfig


def dependency_dir(project):
    """Keep native extensions separate across Python ABIs and CPU architectures."""
    abi = sysconfig.get_config_var('SOABI') or sys.implementation.cache_tag
    return Path(project) / '.watermark-deps' / f'{abi}-{platform.machine()}'


def activate_project(project, dependencies=None):
    """Prefer live project source and its libraries without changing global Python paths."""
    project = Path(project).resolve()
    libraries = Path(dependencies) if dependencies is not None else dependency_dir(project)
    for directory in (libraries, project / 'src'):
        entry = str(directory)
        if directory.is_dir():
            sys.path[:] = [item for item in sys.path if item != entry]
            sys.path.insert(0, entry)
