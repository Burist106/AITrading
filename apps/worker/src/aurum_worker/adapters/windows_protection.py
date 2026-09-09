"""Current-user Windows DPAPI only; no password, machine-wide or plaintext fallback."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

MAX_PROTECTED_BYTES = 32_768


class ProtectionError(Exception):
    def __init__(self) -> None:
        super().__init__("PROFILE_PROTECTION_FAILED")


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]


class WindowsDataProtection:
    def protect(self, data: bytes) -> bytes:
        return self._transform(data, decrypt=False)

    def unprotect(self, data: bytes) -> bytes:
        return self._transform(data, decrypt=True)

    def _transform(self, data: bytes, *, decrypt: bool) -> bytes:
        if sys.platform != "win32" or not 0 < len(data) <= MAX_PROTECTED_BYTES:
            raise ProtectionError()
        try:
            # Search System32 only. Never load a DLL from the working directory.
            crypt = ctypes.WinDLL("crypt32.dll", winmode=0x00000800)
            kernel = ctypes.WinDLL("kernel32.dll", winmode=0x00000800)
            blob_pointer = ctypes.POINTER(_Blob)
            crypt.CryptProtectData.argtypes = [
                blob_pointer,
                ctypes.c_void_p,
                blob_pointer,
                ctypes.c_void_p,
                ctypes.c_void_p,
                wintypes.DWORD,
                blob_pointer,
            ]
            crypt.CryptProtectData.restype = wintypes.BOOL
            crypt.CryptUnprotectData.argtypes = crypt.CryptProtectData.argtypes
            crypt.CryptUnprotectData.restype = wintypes.BOOL
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree.restype = ctypes.c_void_p
            source_buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
            source = _Blob(len(data), source_buffer)
            domain = b"aurum-local-demo-profile-v1"
            entropy_buffer = (ctypes.c_ubyte * len(domain)).from_buffer_copy(domain)
            entropy = _Blob(len(domain), entropy_buffer)
            target = _Blob()
            try:
                # UI_FORBIDDEN only; LOCAL_MACHINE is deliberately never set.
                if decrypt:
                    success = crypt.CryptUnprotectData(
                        ctypes.byref(source),
                        None,
                        ctypes.byref(entropy),
                        None,
                        None,
                        0x1,
                        ctypes.byref(target),
                    )
                else:
                    success = crypt.CryptProtectData(
                        ctypes.byref(source),
                        None,
                        ctypes.byref(entropy),
                        None,
                        None,
                        0x1,
                        ctypes.byref(target),
                    )
                if not success or not 0 < target.size <= MAX_PROTECTED_BYTES:
                    raise ProtectionError()
                return ctypes.string_at(target.data, target.size)
            finally:
                ctypes.memset(source_buffer, 0, len(data))
                if target.data:
                    ctypes.memset(target.data, 0, target.size)
                    kernel.LocalFree(target.data)
        except Exception:
            raise ProtectionError() from None
