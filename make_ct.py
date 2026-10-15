#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build PointerFinder.CT — a SELF-CONTAINED Cheat Engine table.

The tool's Lua code (pointerfinder.lua) is embedded into the table, so the single
.CT file is the whole distribution: no absolute paths, no side files. Put it
anywhere and open it in Cheat Engine.

    python make_ct.py          -> PointerFinder.CT    (embeds pointerfinder.lua)
    python make_ct.py --dev    -> PointerFinder-dev.CT (loads pointerfinder.lua
                                 from this folder; local dev helper, do NOT
                                 publish)

Update without reopening CE: Ctrl+Alt+L (Lua Engine) -> abfReload() -> Execute.
"""
import ctypes
import os
import platform
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
LUA = HERE / "pointerfinder.lua"
OUT = HERE / "PointerFinder.CT"
OUT_DEV = HERE / "PointerFinder-dev.CT"


def ce_dll_candidates():
    env = Path(os.environ["CE_DIR"]) if os.environ.get("CE_DIR") else None
    base_names = ("lua53-64.dll", "lua53-32.dll")
    cands = []
    if env is not None:
        cands += [env / n for n in base_names]
    for base in (Path(r"C:\Program Files\Cheat Engine"),
                 Path(r"C:\Program Files (x86)\Cheat Engine")):
        cands += [base / n for n in base_names]
    return cands


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def long_bracket_level(src: str) -> int:
    """Pick a Lua long-bracket level whose closing seq doesn't occur in src."""
    for level in range(0, 16):
        closer = "]" + "=" * level + "]"
        if closer not in src:
            return level
    raise RuntimeError("cannot pick a long-bracket level")


def version_of(src: str) -> str:
    for line in src.splitlines():
        line = line.strip()
        if line.startswith("--") and "Pointer Finder v" in line:
            return line.split("v", 1)[1].split()[0].rstrip(",")
    return "?"


STOP_OLD = """\
local function stopOld()
  pcall(function()
    local A = _G.__PointerFinder
    if A ~= nil then
      pcall(function() if A.stopAll ~= nil then A.stopAll(false) end end)
      pcall(function() if A.timer ~= nil then A.timer.destroy() end end)
      pcall(function() if A.form ~= nil then A.form.destroy() end end)
    end
  end)
  _G.__PointerFinder = nil
end
"""

RELOAD_EMBEDDED = """\
function abfReload()
  stopOld()
  local f, err = load(_G.__PointerFinderSrc, '=pointerfinder.lua')
  if f == nil then
    print('Pointer Finder: embedded source error: ' .. tostring(err))
    return
  end
  f()
  print('Pointer Finder: loaded (embedded build)')
end
"""

RELOAD_DEV = """\
function abfReload()
  stopOld()
  local f, err = loadfile(_G.__PointerFinderDevPath)
  if f == nil then
    print('Pointer Finder: cannot load ' .. tostring(_G.__PointerFinderDevPath)
      .. ' (' .. tostring(err) .. ')')
    return
  end
  f()
  print('Pointer Finder: loaded ' .. tostring(_G.__PointerFinderDevPath))
end
"""


def wrap_ct(lua_body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<CheatTable CheatEngineVersion="7.4">\n'
        "  <CheatEntries>\n  </CheatEntries>\n"
        "  <UserdefinedSymbols/>\n"
        "  <LuaScript>" + xml_escape(lua_body) + "</LuaScript>\n"
        "</CheatTable>\n"
    )


def build_ct(src: str) -> str:
    version = version_of(src)
    level = long_bracket_level(src)
    opener = "[" + "=" * level + "["
    closer = "]" + "=" * level + "]"
    body = (
        "-- Pointer Finder v%s — Cheat Engine table.\n" % version
        + "-- The tool code is embedded; this single file is the whole\n"
        + "-- distribution. Update without reopening CE:\n"
        + "--   Ctrl+Alt+L (Lua Engine) -> abfReload() -> Execute.\n\n"
        + STOP_OLD
        + "__PointerFinderSrc = " + opener + "\n"
        + src.rstrip("\n") + "\n" + closer + "\n\n"
        + RELOAD_EMBEDDED
        + "\nabfReload()\n"
    )
    return wrap_ct(body)


def build_dev_ct(src_path: Path, version: str) -> str:
    body = (
        "-- Pointer Finder v%s — DEV table (do not publish).\n" % version
        + "-- Loads pointerfinder.lua from the project folder, so code edits only\n"
        + "-- need abfReload(), no rebuild.\n\n"
        + STOP_OLD
        + "_G.__PointerFinderDevPath = [[" + str(src_path) + "]]\n\n"
        + RELOAD_DEV
        + "\nabfReload()\n"
    )
    return wrap_ct(body)


def smoke_test(ct_path: Path) -> int:
    """XML valid + loader compiles with the real Lua 5.3 shipped with CE."""
    root = ET.parse(ct_path).getroot()
    script = root.find("LuaScript")
    if script is None or not (script.text or "").strip():
        print(f"FAIL: {ct_path.name}: LuaScript is empty")
        return 1
    dll_path = None
    for cand in ce_dll_candidates():
        if cand.exists():
            dll_path = cand
            break
    if dll_path is None:
        print(f"SMOKE: {ct_path.name}: XML OK (lua53 dll not found, compile skipped)")
        return 0
    dll = ctypes.CDLL(str(dll_path))
    dll.luaL_newstate.restype = ctypes.c_void_p
    L = dll.luaL_newstate()
    dll.luaL_loadbufferx.restype = ctypes.c_int
    dll.luaL_loadbufferx.argtypes = (
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p,
        ctypes.c_char_p,
    )
    src = (script.text or "").encode("utf-8")
    rc = dll.luaL_loadbufferx(L, src, len(src), b"bootstrap", None)
    dll.lua_close.argtypes = [ctypes.c_void_p]
    if rc != 0:
        dll.lua_tolstring.restype = ctypes.c_char_p
        dll.lua_tolstring.argtypes = (
            ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t),
        )
        size = ctypes.c_size_t(0)
        msg = dll.lua_tolstring(L, -1, size and ctypes.byref(size) or None)
        print(f"FAIL: {ct_path.name}: loader does not compile:")
        print((msg or b"?").decode("utf-8", "replace"))
        dll.lua_close(L)
        return 1
    dll.lua_close(L)
    print(f"SMOKE OK: {ct_path.name}: XML valid, loader compiles with Lua 5.3")
    return 0


def main() -> int:
    if not LUA.exists():
        print(f"FAIL: {LUA} not found")
        return 1
    src = LUA.read_text(encoding="utf-8")
    OUT.write_text(build_ct(src), encoding="utf-8", newline="\n")
    print(f"OK: {OUT.name} (v{version_of(src)}, embedded {len(src)} chars)")
    if "--dev" in sys.argv:
        OUT_DEV.write_text(build_dev_ct(LUA, version_of(src)),
                           encoding="utf-8", newline="\n")
        print(f"OK: {OUT_DEV.name} (dev loader, local only)")
    rc = smoke_test(OUT)
    if "--dev" in sys.argv and rc == 0:
        rc = smoke_test(OUT_DEV)
    return rc


if __name__ == "__main__":
    sys.exit(main())
