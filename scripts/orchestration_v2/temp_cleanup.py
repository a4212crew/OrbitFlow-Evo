"""Bounded cleanup of the controller-owned external temporary directory."""
import os
from pathlib import Path
import stat
import re
import sys
import tempfile
from contextlib import contextmanager
import time

from models import FailureCategory, OrchestrationError


def cleanup_temp(target: Path) -> None:
    target = target.absolute()

    def validate(path: Path):
        info = path.lstat()
        # Fail closed for reparse points, including junctions. Validate each
        # object before touching it; no ACL reset or elevation is attempted.
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise OSError(f'Refusing temporary reparse point: {path}')
        if target != path and target not in path.parents:
            raise OSError(f'Temporary path escaped owned directory: {path}')
        if path != target and target not in path.resolve().parents:
            raise OSError(f'Temporary path escaped owned directory: {path}')
        return info

    def remove(path: Path) -> None:
        for attempt in range(3):
            info = validate(path)
            try:
                if stat.S_ISDIR(info.st_mode):
                    # Materialize/close the directory handle before deleting.
                    children = list(path.iterdir())
                    for child in children:
                        remove(child)
                    path.rmdir()
                else:
                    path.unlink()
                return
            except PermissionError:
                validate(path)
                os.chmod(path, stat.S_IRWXU)
                if attempt == 2:
                    raise
            except OSError:
                if attempt == 2:
                    raise
            time.sleep(0.1)

    try:
        try:
            target.lstat()
        except FileNotFoundError:
            return
        remove(target)
    except OSError as exc:
        raise OrchestrationError(FailureCategory.CONTROLLER,
                                 f'Temporary cleanup failed at {target}: {exc}') from exc


@contextmanager
def controller_temp(worktree: Path, purpose: str):
    """Own one unique OS-temp directory; cleanup warnings never gate Git work."""
    root = Path(tempfile.gettempdir()).resolve()
    worktree = worktree.resolve()
    # Reject environment overrides pointing into any Git checkout, before mkdir.
    if root == worktree or worktree in root.parents or any(
        (parent / '.git').exists() for parent in (root, *root.parents)
    ):
        raise OrchestrationError(FailureCategory.CONTROLLER,
                                 f'OS temporary directory must be outside Git worktrees: {root}')
    task = re.sub(r'[^A-Za-z0-9_-]', '-', worktree.name)[:64]
    target = Path(tempfile.mkdtemp(prefix=f'orbitflow-{task}-{purpose}-', dir=root))
    try:
        yield target
    finally:
        try:
            cleanup_temp(target)
        except OrchestrationError as exc:
            print(f'WARNING: {exc}. External artifacts retained; Git operations remain available.',
                  file=sys.stderr)
