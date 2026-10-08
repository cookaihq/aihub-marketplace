"""Revision-checked, narrowly scoped local edits. Never accepts a credential value."""
import contextlib
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

from .errors import SetupError
from .consumers import path_id
from .local_platform import private_permissions, verify_private_permissions, sync_replaced_file

MAX_FILE_BYTES = 1024 * 1024
ASSIGNMENT = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")


def checked_path(path):
    """Do not resolve links away before inspecting the lexical path."""
    target = Path(os.path.abspath(path))
    if any(c in str(target) for c in "\r\n\x00"):
        raise SetupError("invalid_path")
    for part in reversed((target, *target.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SetupError("linked_path_refused")
        if part != target and not stat.S_ISDIR(info.st_mode):
            raise SetupError("invalid_parent")
    if target.exists() and not target.is_file():
        raise SetupError("target_not_file")
    return target


def snapshot(path):
    path = checked_path(path)
    ancestors = []
    for parent in reversed(path.parents):
        if parent.exists():
            info = parent.stat()
            ancestors.append([str(parent), info.st_dev, info.st_ino])
    try:
        info = path.stat()
        if info.st_nlink != 1:
            raise SetupError("hardlinked_target_refused")
        if info.st_size > MAX_FILE_BYTES:
            raise SetupError("configuration_too_large")
        content = path.read_bytes()
        return {"path": str(path), "revision": hashlib.sha256(content).hexdigest(),
                "file_id": [info.st_dev, info.st_ino], "ancestors": ancestors}
    except FileNotFoundError:
        return {"path": str(path), "revision": None, "file_id": None, "ancestors": ancestors}


def same_snapshot(expected, *, allow_new_parents=False):
    current = snapshot(expected["path"])
    if current["revision"] != expected["revision"] or current["file_id"] != expected["file_id"]:
        raise SetupError("target_changed")
    if allow_new_parents:
        if any(item not in current["ancestors"] for item in expected["ancestors"]):
            raise SetupError("path_changed")
    elif current["ancestors"] != expected["ancestors"]:
        raise SetupError("path_changed")
    return current


def git_safe(path):
    """Prove both untracked and ignored if this path is inside a Git worktree."""
    path = checked_path(path)
    directory = path.parent
    while not directory.exists():
        directory = directory.parent
    # The caller can be running from another Git worktree or hook. Probe the
    # actual target, independently of inherited repository/index selectors.
    selectors = {"GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY",
                 "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CEILING_DIRECTORIES", "GIT_DISCOVERY_ACROSS_FILESYSTEM"}
    # Preserve Git's configuration controls: a host sandbox may use these to
    # provide a readable config. They also define the user's actual ignore rules.
    environment = {key: value for key, value in os.environ.items() if key not in selectors}
    environment["LC_ALL"] = "C"
    try:
        probe = subprocess.run(["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
                               env=environment, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise SetupError("git_protection_unavailable") from None
    if probe.returncode:
        # A negative probe can mean dubious ownership or permissions. Accept only
        # an ordinary not-a-repository result with no .git marker on the path.
        if any((p / ".git").exists() for p in (directory, *directory.parents)):
            raise SetupError("git_protection_unavailable")
        if b"not a git repository" not in probe.stderr.lower():
            raise SetupError("git_protection_unavailable")
        return
    root = Path(os.fsdecode(probe.stdout).strip()).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        raise SetupError("git_protection_unavailable") from None
    try:
        tracked = subprocess.run(["git", "-C", str(root), "--literal-pathspecs", "ls-files", "--error-unmatch", "--", relative],
                                 env=environment, capture_output=True, timeout=10)
        ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "--quiet", "--", relative],
                                 env=environment, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        raise SetupError("git_protection_unavailable") from None
    if tracked.returncode == 0:
        raise SetupError("target_tracked")
    if tracked.returncode != 1 or ignored.returncode not in (0, 1):
        raise SetupError("git_protection_unavailable")
    if ignored.returncode != 0:
        raise SetupError("target_not_ignored")


def _content(path):
    if not path.exists():
        return b""
    raw = path.read_bytes()
    if len(raw) > MAX_FILE_BYTES:
        raise SetupError("configuration_too_large")
    return raw


def transform(raw, fields, operation):
    """Preserve bytes of unrelated UTF-8 lines, including BOM and CRLF."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        raise SetupError("unsupported_encoding") from None
    if any(char in text for char in ("\x00", "\ufeff", "\u2028", "\u2029", "\x85")) or "\r" in text.replace("\r\n", ""):
        raise SetupError("unsupported_file_format")
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    lines = text.splitlines(keepends=True)
    present, output = set(), []
    for line in lines:
        match = ASSIGNMENT.fullmatch(line.rstrip("\r\n"))
        if match:
            key, value = match.groups()
            # Multiline dotenv values are outside both loaders' grammar. Avoid
            # deleting just their opening line and leaving a secret continuation.
            if value[:1] in ("'", '"') and (len(value) < 2 or value[-1] != value[0]):
                raise SetupError("unsupported_multiline_assignment")
            present.add(key)
            if operation == "clear" and key in fields:
                continue
        output.append(line)
    if operation == "prepare":
        newline = "\r\n" if "\r\n" in text else "\n"
        missing = [field for field in fields if field not in present]
        if missing:
            if output and not output[-1].endswith("\n"):
                output.append(newline)
            output.append("# 在本机填写以下字段；保留 # 的示例不会生效。" + newline)
            output.extend("# " + field + "=" + newline for field in missing)
    return bom + "".join(output).encode("utf-8")


def validate_target(consumer, report, target, fields, operation):
    path = checked_path(target)
    if not fields or len(set(fields)) != len(fields) or not set(fields) <= consumer.adapter["fields"]:
        raise SetupError("unsupported_fields")
    if path_id(path) not in {path_id(layer["path"]) for layer in report["layers"]}:
        raise SetupError("target_not_read_by_consumer")
    if any(problem["reason"] == "unreadable" for problem in report["problems"]):
        raise SetupError("unreadable_configuration")
    if operation == "prepare":
        for key in fields:
            source = report["fields"][key]["source"]
            if source == "environment":
                raise SetupError("repair_environment_at_injection_source", field=key)
            if source not in ("missing", "built-in default") and path_id(source) != path_id(path):
                raise SetupError("repair_actual_source", field=key, source=source)
    git_safe(path)
    # Validate format during the preview as well as immediately before writing.
    transform(_content(path), fields, operation)
    current = snapshot(path)
    declared = next(layer for layer in report["layers"] if path_id(layer["path"]) == path_id(path))
    if current["revision"] != declared["revision"]:
        raise SetupError("target_changed")
    return current


def prepare_parents(path):
    missing = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for parent in reversed(missing):
        parent.mkdir(mode=0o700)
        private_permissions(parent, directory=True)


def edit(plan):
    """Caller holds a target lock and has rechecked the loader + confirmation."""
    expected = plan["target_snapshot"]
    path = checked_path(expected["path"])
    same_snapshot(expected)
    git_safe(path)
    raw = _content(path)
    content = transform(raw, plan["fields"], plan["action"])
    prepare_parents(path)
    same_snapshot(expected, allow_new_parents=True)
    if path.exists() and raw == content:
        private_permissions(path)
        verify_private_permissions(path)
        return {"changed": False, "path": str(path), "revision": expected["revision"]}
    # tempfile creates an empty file. Apply/verify access and Git protection BEFORE
    # writing bytes. No secret backup or editor snapshot is left behind.
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".setup-aihub-", suffix=".tmp")
    temporary = Path(name)
    try:
        git_safe(temporary)
        private_permissions(temporary, fd=fd)
        verify_private_permissions(temporary)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        same_snapshot(expected, allow_new_parents=True)
        git_safe(path)
        checked_path(temporary)
        os.replace(temporary, path)
        sync_replaced_file(path, content)
        return {"changed": True, "path": str(path), "revision": hashlib.sha256(content).hexdigest()}
    finally:
        if fd is not None:
            os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()
