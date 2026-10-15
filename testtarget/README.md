# TestTarget — a fake game for end-to-end testing

`target_game.c` builds a tiny console "game" that mimics the memory layout of
a real game: a **5-level pointer chain where every level shows its own
distinguishable number**. Use it to verify Pointer Finder (or your CE build)
end to end.

```
target_game.exe+0x9080  (.bss, g_game)  — STATIC ANCHOR
  +0x00 → Game   Game.Value = 1111      — level 1 (heap, permanent)
    +0x10 → L1     L1.Value = 2222      — level 2 (heap, GC)
      +0x10 → L2   L2.Value = 3333      — level 3 (heap, GC)
        +0x10 → L3 L3.Value = MONEY     — level 4 (heap, GC)
          +0x10 → L4 L4.Value = MONEY  — mirror (heap, GC)
```

Node layout: `+0x00` double `Value`, `+0x10` pointer `Next`, `+0x18` double
`Marker` (9001–9005). The GC (every `gc_ms`, default 15 s) rebuilds L1..L4 —
addresses change, values stay. The module base changes on every process
start, so only the `target_game.exe+9080` anchor survives a restart.

## Build

```
gcc -O0 -static -Wall -Wextra -o target_game.exe target_game.c
```

Any MinGW-w64 works (e.g. `winget install BrechtSanders.WinLibs.POSIX.UCRT`).

## Run

```
target_game.exe [money_ms] [gc_ms]    ; defaults: 2000 and 15000
```

Attach CE: File → Open Process → `target_game.exe` (re-attach after every
game restart!). Keys: `[space]` +100 money, `[g]` run GC, `[p]` print chain,
`[q]` quit. The live money address is on the `[MONEY] ... (L3=0x...)` line.

Tip: start with a long GC interval, e.g. `target_game.exe 4000 120000` —
otherwise nodes move mid-search.

## Manual pointer-record matrix

Add Address Manually → Pointer → Address `target_game.exe+9080` → Double.
Offsets top-to-bottom, hex. Every record must show ITS number:

| Offsets (top-to-bottom) | Expected          | Depth |
|---|---|---|
| `0`                     | `1111`            | 1 |
| `0`, `0`                | `1111`            | 2 |
| `0`, `10`, `0`          | `2222`            | 3 |
| `0`, `10`, `10`, `0`    | `3333`            | 4 |
| `0`, `10`, `10`, `10`, `0`             | money (grows) | 5 |
| `0`, `10`, `10`, `10`, `10`, `0`       | money (grows) | 6 |

The depth where `??` appears instead of a number is the pointer-record
evaluation limit of your CE build (these records are created by hand —
Pointer Finder is not involved). If `??` shows up at 3+ offsets even after a
full CE restart, the CE build is defective — use an official installer from
cheatengine.org.

Note: with the default money start (100) the money value *passes through*
1111/2222/3333 early on, which can be confusing during scans. Starting with
`target_game.exe 4000 ...` avoids that.

## Pointer Finder run

Take the address from `[MONEY] ... (L3=0x...)` (or any address your own CE
scan finds) → paste into the tool → **Start**. Expected result in ~20 s:

```
[★] BASE ADDRESS FOUND: [[[[[target_game.exe+9080+0]+10]+10]+10]+0]
[✓] control read [...] = <money> matches the current value
```

and one pointer record with offsets `{0, 10, 10, 10}` showing the growing
money value. The step-by-step chain verification is printed to the log and
duplicated into `%TEMP%\PointerFinder_selfcheck.txt`.
