"""Coordinate settings.json with the existing Node reminder writer."""
from contextlib import contextmanager
import os
from pathlib import Path

from skill_ui.contracts import UIError
from persistence import checked, git_safe, parents
from private_platform import private_permissions, verify_private_permissions


@contextmanager
def settings_lock(path, owner_path):
    if Path(path).name != 'settings.json':
        yield
        return
    target = checked(str(path) + '.default-skills.lock')
    git_safe(target, owner_path=owner_path)
    parents(target, owner_path)
    try:
        descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        raise UIError('busy', '其他操作正在保存全局偏好，请稍后再试。若持续失败，请先检查未完成的保存操作。', 409) from None
    try:
        private_permissions(target, fd=descriptor, owner_path=owner_path)
        verify_private_permissions(target, owner_path=owner_path)
        yield
    finally:
        os.close(descriptor)
        target.unlink()
