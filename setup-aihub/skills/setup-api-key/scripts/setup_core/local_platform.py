# Adapted from cookaihq/secret-book v2.4.0 (MIT), published commit 1a91198.
"""Local file primitives for POSIX and native Windows; no third-party runtime."""

import contextlib
import errno
import os
import time


if os.name == "nt":
    import ctypes
    from ctypes import wintypes
    import msvcrt

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _security = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel.LocalFree.restype = ctypes.c_void_p
    _security.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD,
                                            ctypes.POINTER(wintypes.HANDLE)]
    _security.GetTokenInformation.argtypes = [wintypes.HANDLE, ctypes.c_int,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _security.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _security.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    _security.SetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.c_void_p]
    _security.GetFileSecurityW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    _security.GetSecurityDescriptorDacl.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(wintypes.BOOL), ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]
    _security.GetSecurityDescriptorControl.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    _security.GetSecurityDescriptorOwner.argtypes = [ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.BOOL)]

    def _checked(ok):
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

    def _current_sid():
        token = wintypes.HANDLE()
        _checked(_security.OpenProcessToken(_kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)))
        try:
            size = wintypes.DWORD()
            _security.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))  # TokenUser
            if not size.value:
                raise ctypes.WinError(ctypes.get_last_error())
            data = ctypes.create_string_buffer(size.value)
            _checked(_security.GetTokenInformation(token, 1, data, size, ctypes.byref(size)))
            sid = ctypes.cast(data, ctypes.POINTER(ctypes.c_void_p))[0]
            text = wintypes.LPWSTR()
            _checked(_security.ConvertSidToStringSidW(sid, ctypes.byref(text)))
            try:
                return text.value
            finally:
                _kernel.LocalFree(text)
        finally:
            _kernel.CloseHandle(token)

    def _dacl_bytes(descriptor):
        present, defaulted = wintypes.BOOL(), wintypes.BOOL()
        acl = ctypes.c_void_p()
        _checked(_security.GetSecurityDescriptorDacl(
            descriptor, ctypes.byref(present), ctypes.byref(acl), ctypes.byref(defaulted)))
        if not present.value or not acl.value:
            raise OSError("Windows 文件缺少限制访问的 DACL")
        # ACL header: revision/zero (2 bytes), AclSize (WORD), AceCount, zero.
        size = ctypes.c_ushort.from_address(acl.value + 2).value
        return ctypes.string_at(acl.value, size)

    def _read_security(path, information=0x0004):
        size = wintypes.DWORD()
        _security.GetFileSecurityW(str(path), information, None, 0, ctypes.byref(size))
        if not size.value:
            raise ctypes.WinError(ctypes.get_last_error())
        data = ctypes.create_string_buffer(size.value)
        _checked(_security.GetFileSecurityW(str(path), information, data, size, ctypes.byref(size)))
        return data

    def _owner_sid(path):
        security = _read_security(path, 0x0001)
        owner, defaulted = ctypes.c_void_p(), wintypes.BOOL()
        _checked(_security.GetSecurityDescriptorOwner(security, ctypes.byref(owner), ctypes.byref(defaulted)))
        text = wintypes.LPWSTR()
        _checked(_security.ConvertSidToStringSidW(owner, ctypes.byref(text)))
        try:
            return text.value
        finally:
            _kernel.LocalFree(text)

    @contextlib.contextmanager
    def _private_descriptor(directory, owner_path=None):
        flags = "OICI" if directory else ""
        # UI files remain readable by the selected project's owner when a
        # sandbox account writes them. Other callers retain their original ACL.
        owners = {_current_sid(), _owner_sid(owner_path) if owner_path is not None else 'SY'}
        sddl = 'D:P' + ''.join('(A;%s;FA;;;%s)' % (flags, sid) for sid in sorted(owners))
        descriptor = ctypes.c_void_p()
        _checked(_security.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(descriptor), None))
        try:
            yield descriptor
        finally:
            _kernel.LocalFree(descriptor)

    def _verify_private(path, expected):
        actual = _read_security(path)
        control, revision = wintypes.WORD(), wintypes.DWORD()
        _checked(_security.GetSecurityDescriptorControl(actual, ctypes.byref(control), ctypes.byref(revision)))
        if not control.value & 0x1000 or _dacl_bytes(actual) != _dacl_bytes(expected):
            raise OSError("Windows 文件权限回读不一致；拒绝写入凭证")

    def verify_private_permissions(path, *, directory=False, owner_path=None):
        with _private_descriptor(directory, owner_path) as descriptor:
            _verify_private(path, descriptor)

else:
    import fcntl

    def verify_private_permissions(path, *, directory=False, owner_path=None):
        import stat
        if stat.S_IMODE(path.stat().st_mode) != (0o700 if directory else 0o600):
            raise OSError("文件权限不是仅当前用户可访问")


def private_permissions(path, *, directory=False, fd=None, owner_path=None):
    """Apply and verify permissions before writing any secret bytes."""
    if os.name == "nt":
        with _private_descriptor(directory, owner_path) as descriptor:
            _checked(_security.SetFileSecurityW(str(path), 0x80000004, descriptor))
            _verify_private(path, descriptor)
    elif fd is not None:
        os.fchmod(fd, 0o700 if directory else 0o600)
    else:
        os.chmod(path, 0o700 if directory else 0o600)


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    private_permissions(path, directory=True)


@contextlib.contextmanager
def exclusive_lock(fd, *, timeout=30):
    """Lock a stable sidecar file across processes, with bounded Windows contention."""
    if os.name != "nt":
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待本地配置写入锁超时；未执行本次写入")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
        return
    deadline = time.monotonic() + timeout
    while True:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            break
        except OSError as exc:
            if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise
            if time.monotonic() >= deadline:
                raise TimeoutError("等待本地配置写入锁超时；未执行本次写入") from exc
            time.sleep(0.05)
    try:
        yield
    finally:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def sync_replaced_file(path, expected, *, owner_path=None):
    if os.name == "nt":
        # Windows cannot open/fsync a directory using POSIX os.open. The temp
        # file was already flushed before rename; verify content and ACL after it.
        verify_private_permissions(path, owner_path=owner_path)
        if path.read_bytes() != expected:
            raise OSError("本地文件替换后回读不一致")
    else:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        verify_private_permissions(path, owner_path=owner_path)
        if path.read_bytes() != expected:
            raise OSError("本地文件替换后回读不一致")
