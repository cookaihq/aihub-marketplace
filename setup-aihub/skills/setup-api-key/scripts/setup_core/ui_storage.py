"""Private metadata storage. Browser inputs never use this module."""
import contextlib
import json
import os
from pathlib import Path
import tempfile

from .local_config import checked_path
from .local_platform import private_directory, private_permissions, sync_replaced_file, exclusive_lock


def write_json(path, value):
    path = checked_path(path)
    private_directory(path.parent)
    data = (json.dumps(value, ensure_ascii=True, indent=2) + "\n").encode()
    fd, name = tempfile.mkstemp(prefix=".ui-", suffix=".tmp", dir=path.parent)
    try:
        private_permissions(Path(name), fd=fd)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        checked_path(path)
        os.replace(name, path)
        sync_replaced_file(path, data)
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


@contextlib.contextmanager
def instance_lock(directory):
    path = checked_path(Path(directory) / "server.lock")
    private_directory(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        private_permissions(path, fd=fd)
        with exclusive_lock(fd, timeout=0):
            yield
    finally:
        os.close(fd)
