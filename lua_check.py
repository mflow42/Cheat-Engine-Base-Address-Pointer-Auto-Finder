#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка синтаксиса pointerfinder.lua настоящим Lua 5.3 из поставки CE
(lua53-64.dll / lua53-32.dll), без запуска кода: только компиляция чанка.
"""
import ctypes
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LUA_FILE = HERE / "pointerfinder.lua"


def ce_dirs():
    dirs = []
    if os.environ.get("CE_DIR"):
        dirs.append(Path(os.environ["CE_DIR"]))
    dirs.append(Path(r"C:\Program Files\Cheat Engine"))
    dirs.append(Path(r"C:\Program Files (x86)\Cheat Engine"))
    return dirs


def load_dll():
    import platform

    dll_names = ("lua53-64.dll", "lua53-32.dll")
    # 64-битный питон грузит 64-битную DLL первой, но пробуем обе
    if platform.architecture()[0] != "64bit":
        dll_names = ("lua53-32.dll", "lua53-64.dll")
    candidates = [d / n for d in ce_dirs() for n in dll_names]
    last = None
    for p in candidates:
        if not p.exists():
            continue
        try:
            dll = ctypes.CDLL(str(p))
            print(f"Загружена {p.name} ({p.parent})")
            return dll
        except OSError as e:
            last = e
    raise RuntimeError(
        "Не удалось загрузить lua53 dll из поставки CE "
        f"(задай CE_DIR=<путь к Cheat Engine>): {last}"
    )


def main() -> int:
    src = LUA_FILE.read_bytes()
    dll = load_dll()

    dll.luaL_newstate.restype = ctypes.c_void_p
    L = dll.luaL_newstate()
    if not L:
        print("FAIL: luaL_newstate вернул NULL")
        return 1

    # в Lua 5.3 luaL_loadbuffer — макрос над luaL_loadbufferx
    dll.luaL_loadbufferx.restype = ctypes.c_int
    dll.luaL_loadbufferx.argtypes = (
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
        ctypes.c_char_p,
    )
    rc = dll.luaL_loadbufferx(L, src, len(src), b"pointerfinder.lua", None)
    if rc == 0:
        print("SYNTAX OK: pointerfinder.lua компилируется Lua 5.3 без ошибок")
        dll.lua_close.argtypes = [ctypes.c_void_p]
        dll.lua_close(L)
        return 0

    dll.lua_tolstring.restype = ctypes.c_char_p
    dll.lua_tolstring.argtypes = (
        ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t),
    )
    size = ctypes.c_size_t(0)
    msg = dll.lua_tolstring(L, -1, ctypes.byref(size))
    print("SYNTAX FAIL:")
    print((msg or b"?").decode("utf-8", "replace"))
    dll.lua_close.argtypes = [ctypes.c_void_p]
    dll.lua_close(L)
    return 1


if __name__ == "__main__":
    sys.exit(main())
