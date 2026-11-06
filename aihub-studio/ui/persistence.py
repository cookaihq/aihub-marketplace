"""Private, revision-checked local transactions. Locks coordinate cooperating UI writers.

Path and Git checks follow setup-api-key's local_config protocol. A private journal
allows a later page instance to recover an interrupted multi-file save. External
editors do not participate in the locks; hashes prevent overwriting their changes.
"""
import base64
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess

from skill_ui.contracts import UIError
from private_platform import private_permissions, verify_private_permissions, exclusive_lock, sync_replaced_file

MAX_FILE_BYTES = 1024 * 1024

def checked(path):
    target = Path(os.path.abspath(path))
    if any(c in str(target) for c in '\r\n\0'):
        raise UIError('path', '配置路径无效。')
    for part in reversed((target, *target.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise UIError('path', '保存路径含链接，请在实际配置文件所在位置修复。')
        if part != target and not stat.S_ISDIR(info.st_mode):
            raise UIError('path', '配置文件的父目录无效。')
    if target.exists() and (not target.is_file() or target.stat().st_nlink != 1):
        raise UIError('path', '保存目标必须是独立普通文件。')
    return target


def read(path):
    path = checked(path)
    if not path.exists():
        return None
    if path.stat().st_size > MAX_FILE_BYTES:
        raise UIError('size', '配置文件超过 1 MiB，请先检查文件。')
    return path.read_bytes()


def digest(raw):
    return hashlib.sha256(raw).hexdigest() if raw is not None else None


def git_safe(path):
    path = checked(path)
    directory = path.parent
    while not directory.exists():
        directory = directory.parent
    selectors = {'GIT_DIR', 'GIT_COMMON_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_OBJECT_DIRECTORY',
                 'GIT_ALTERNATE_OBJECT_DIRECTORIES', 'GIT_CEILING_DIRECTORIES', 'GIT_DISCOVERY_ACROSS_FILESYSTEM'}
    environment = {key: value for key, value in os.environ.items() if key not in selectors}
    environment['LC_ALL'] = 'C'
    def git(*args):
        return subprocess.run(['git', '-C', str(directory), *args], env=environment,
                              capture_output=True, timeout=10)
    try:
        probe = git('rev-parse', '--show-toplevel')
        if probe.returncode:
            if any((part / '.git').exists() for part in (directory, *directory.parents)) or b'not a git repository' not in probe.stderr.lower():
                raise ValueError()
            return
        root = Path(os.fsdecode(probe.stdout).strip()).resolve()
        relative = path.relative_to(root).as_posix()
        directory = root
        tracked = git('--literal-pathspecs', 'ls-files', '--error-unmatch', '--', relative)
        ignored = git('check-ignore', '--quiet', '--', relative)
        if tracked.returncode == 0:
            raise UIError('tracked', '目标配置已被 Git 跟踪；请先处理该文件，页面不会修改 Git 索引。')
        if tracked.returncode != 1 or ignored.returncode not in (0, 1):
            raise ValueError()
        if ignored.returncode:
            raise UIError('ignore', '目标配置或私有暂存目录未被 Git 忽略，请先添加忽略规则。')
    except UIError:
        raise
    except (ValueError, OSError, subprocess.SubprocessError):
        raise UIError('git', '无法确认配置文件的 Git 保护状态，未写入。') from None


def parents(path, owner_path=None):
    missing, parent = [], path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing):
        parent.mkdir(mode=0o700)
        private_permissions(parent, directory=True, owner_path=owner_path)


def replace(path, content, expected, owner_path=None):
    if len(content) > MAX_FILE_BYTES:
        raise UIError('size', '本次配置或恢复记录超过 1 MiB，请减少单次保存内容后重试。')
    path = checked(path)
    if digest(read(path)) != expected:
        raise UIError('conflict', '配置已被其他操作修改；草稿仍保留，请重新载入核对。', 409)
    git_safe(path)
    parents(path, owner_path)
    temporary = path.with_name(path.name + '.ui-' + secrets.token_hex(8) + '.tmp')
    descriptor = None
    try:
        git_safe(temporary)
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        private_permissions(temporary, fd=descriptor, owner_path=owner_path)
        verify_private_permissions(temporary, owner_path=owner_path)
        with os.fdopen(descriptor, 'wb') as stream:
            descriptor = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        checked(path)
        if digest(read(path)) != expected:
            raise UIError('conflict', '配置已被其他操作修改，未覆盖新内容。', 409)
        os.replace(temporary, path)
        sync_replaced_file(path, content, owner_path=owner_path)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


@contextmanager
def lock(path, owner_path=None):
    path = checked(path)
    parents(path, owner_path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        private_permissions(path, fd=descriptor, owner_path=owner_path)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b'0')
        with exclusive_lock(descriptor, timeout=5):
            yield
    except TimeoutError:
        raise UIError('busy', '另一个配置页面正在保存，请稍后再试。', 409) from None
    finally:
        os.close(descriptor)


class Transaction:
    def __init__(self, directory, owner_path=None):
        self.directory = Path(directory)
        self.journal = self.directory / 'pending.json'
        self.owner_path = owner_path

    def _rollback(self, entries):
        for entry in reversed(entries):
            path = checked(entry['path'])
            current = digest(read(path))
            original = base64.b64decode(entry['before']) if entry['before'] is not None else None
            if current == digest(original):
                continue
            if current != entry['after']:
                raise UIError('recovery', '上次保存中断后文件又被修改，无法安全回滚。请保留私有事务记录并修复冲突。', 409)
            if original is None:
                git_safe(path)
                path.unlink()
            else:
                replace(path, original, current, self.owner_path)

    def _recover(self):
        raw = read(self.journal)
        if raw is None:
            return
        try:
            journal = json.loads(raw)
            entries = journal['entries']
            if journal['version'] != 1 or not isinstance(entries, list):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise UIError('recovery', '私有保存记录无法读取，请保留记录并修复。', 409) from None
        with ExitStack() as stack:
            for path in sorted({entry['path'] for entry in entries}):
                stack.enter_context(lock(path + '.ui.lock', self.owner_path))
            if not journal.get('committed'):
                self._rollback(entries)
            self.journal.unlink()

    def recover(self):
        if self.journal.exists():
            with lock(self.directory / 'transaction.lock', self.owner_path):
                self._recover()

    def apply(self, changes, verify):
        git_safe(self.journal)
        with lock(self.directory / 'transaction.lock', self.owner_path):
            self._recover()
            with ExitStack() as stack:
                for path in sorted(changes):
                    stack.enter_context(lock(path + '.ui.lock', self.owner_path))
                verify(False)
                entries = []
                for path, (before, after) in sorted(changes.items()):
                    git_safe(path)
                    if read(path) != before:
                        raise UIError('conflict', '配置已被其他操作修改。请重新载入核对。', 409)
                    entries.append({'path': path, 'before': base64.b64encode(before).decode() if before is not None else None,
                                    'after': digest(after)})
                journal = {'version': 1, 'entries': entries, 'committed': False}
                encode = lambda: json.dumps(journal, ensure_ascii=False).encode('utf-8')
                replace(self.journal, encode(), None, self.owner_path)
                try:
                    for path, (before, after) in sorted(changes.items()):
                        replace(path, after, digest(before), self.owner_path)
                    result = verify(True)
                    journal['committed'] = True
                    replace(self.journal, encode(), digest(read(self.journal)), self.owner_path)
                except BaseException:
                    self._rollback(entries)
                    self.journal.unlink()
                    raise
                self.journal.unlink()
                return result
