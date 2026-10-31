"""Windows 验收目录：只给新目录原所有者显式保留 Modify + WRITE_OWNER。

OWNER RIGHTS 的继承权限不能代替受限子进程的实际访问检查。该函数仅用于
验收夹具，不修改用户既有目录，不改变官方 sandbox 的限制 SID 或授权掩码。
"""
from pathlib import Path
import ctypes as c
from ctypes import wintypes as w
import os

OWNER_ACCESS = 0x1301BF | 0x80000  # Modify、同步及 WRITE_OWNER；无 WRITE_DAC。


class Trustee(c.Structure):
    _fields_ = [('multiple', c.c_void_p), ('operation', w.DWORD), ('form', w.DWORD),
                ('kind', w.DWORD), ('name', c.c_void_p)]


class Entry(c.Structure):
    _fields_ = [('mask', w.DWORD), ('mode', w.DWORD), ('inheritance', w.DWORD), ('trustee', Trustee)]


def prepare_directory(path, scope):
    if os.name != 'nt':
        raise OSError('只支持 Windows 验收目录')
    path, scope = Path(path).absolute(), Path(scope).resolve()
    if path.exists() or path.resolve() == scope or not path.resolve().is_relative_to(scope):
        raise ValueError('仅允许 scope 内尚不存在的新目录')
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError('验收路径不能含重解析点')
    api = c.WinDLL('advapi32', use_last_error=True)
    kernel = c.WinDLL('kernel32', use_last_error=True)
    api.GetNamedSecurityInfoW.argtypes = [w.LPWSTR, c.c_int, w.DWORD, *[c.POINTER(c.c_void_p)] * 5]
    api.GetNamedSecurityInfoW.restype = w.DWORD
    api.SetEntriesInAclW.argtypes = [w.ULONG, c.POINTER(Entry), c.c_void_p, c.POINTER(c.c_void_p)]
    api.SetEntriesInAclW.restype = w.DWORD
    api.SetNamedSecurityInfoW.argtypes = [w.LPWSTR, c.c_int, w.DWORD, *[c.c_void_p] * 4]
    api.SetNamedSecurityInfoW.restype = w.DWORD
    api.OpenProcessToken.argtypes = [w.HANDLE, w.DWORD, c.POINTER(w.HANDLE)]
    api.OpenProcessToken.restype = w.BOOL
    api.GetTokenInformation.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.POINTER(w.DWORD)]
    api.GetTokenInformation.restype = w.BOOL
    api.EqualSid.argtypes = [c.c_void_p, c.c_void_p]
    api.EqualSid.restype = w.BOOL
    kernel.GetCurrentProcess.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    kernel.LocalFree.argtypes = [c.c_void_p]
    kernel.LocalFree.restype = c.c_void_p

    def checked(code, name):
        if code:
            raise OSError(code, name)

    token, owner, acl, descriptor, new_acl = w.HANDLE(), c.c_void_p(), c.c_void_p(), c.c_void_p(), c.c_void_p()
    if not api.OpenProcessToken(kernel.GetCurrentProcess(), 8, c.byref(token)):
        raise OSError(c.get_last_error(), 'OpenProcessToken')
    try:
        size = w.DWORD()
        api.GetTokenInformation(token, 1, None, 0, c.byref(size))
        user = c.create_string_buffer(size.value)
        if not api.GetTokenInformation(token, 1, user, size.value, c.byref(size)):
            raise OSError(c.get_last_error(), 'GetTokenInformation')
        user_sid = c.cast(user, c.POINTER(c.c_void_p))[0]
        path.mkdir(parents=True, exist_ok=False)
        checked(api.GetNamedSecurityInfoW(str(path), 1, 5, c.byref(owner), None,
                                         c.byref(acl), None, c.byref(descriptor)), 'GetNamedSecurityInfoW')
        if not api.EqualSid(owner, user_sid):
            raise ValueError('新目录所有者不是当前调用者，拒绝修改权限')
        assert c.sizeof(Entry) == 48  # 本修复仅声明 Windows x64 验收。
        rule = Entry(OWNER_ACCESS, 1, 3, Trustee(None, 0, 0, 1, owner.value))
        checked(api.SetEntriesInAclW(1, c.byref(rule), acl, c.byref(new_acl)), 'SetEntriesInAclW')
        # 只合并原所有者 Allow ACE；其他 ACE、owner、group、继承与 SACL 均不改写。
        checked(api.SetNamedSecurityInfoW(str(path), 1, 4, None, None, new_acl, None), 'SetNamedSecurityInfoW')
    finally:
        if new_acl:
            kernel.LocalFree(new_acl)
        if descriptor:
            kernel.LocalFree(descriptor)
        kernel.CloseHandle(token)
    return {'path': str(path), 'ownerOnlyMask': hex(OWNER_ACCESS), 'existingDirectoryChanged': False,
            'ownerChanged': False, 'otherPrincipalsGranted': False, 'inheritanceDisabled': False}
