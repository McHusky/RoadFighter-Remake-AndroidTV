#!/usr/bin/env python3
"""Apply Android-TV / SDL2 adaptations to a fresh Road Fighter checkout.

The upstream repository advertises SDL2, but CRoadFighter still contains a
small set of SDL 1.2-era APIs. This script keeps gameplay intact while fixing
those compatibility seams before the Android/NDK build. Keyboard handling is
kept in SDL 1.2 keycode semantics because Road Fighter stores numeric legacy
keycodes in its configuration.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RF = ROOT / "app" / "src" / "main" / "cpp" / "vendor" / "roadfighter"
SRC = RF / "src"
REPORT = ROOT / "upstream-patch-report.txt"

if not SRC.is_dir():
    raise SystemExit(f"Upstream source not found: {SRC}. Run tools/fetch-native-deps.sh first.")

changes: list[str] = []

# Rename upstream main() so android_entry.cpp can prepare app-private storage
# before entering the original game.
main_cpp = SRC / "main.cpp"
text = main_cpp.read_text(encoding="utf-8", errors="surrogateescape")
if "roadfighter_upstream_main" not in text:
    patched, count = re.subn(r"\bint\s+main\s*\(", "int roadfighter_upstream_main(", text, count=1)
    if count != 1:
        raise SystemExit("Could not find exactly one upstream int main(...) in src/main.cpp")
    main_cpp.write_text(patched, encoding="utf-8", errors="surrogateescape")
    changes.append("src/main.cpp: renamed main -> roadfighter_upstream_main")
else:
    changes.append("src/main.cpp: main already renamed")

# Android TV has no distro DejaVu path. Use the bundled redistributable DejaVu font instead.
font_re = re.compile(r'"/[^"\n]*DejaVu[^"\n]*\.ttf"')
font_count = 0
for path in sorted(SRC.rglob("*")):
    if path.suffix.lower() not in {".cpp", ".cc", ".c", ".h", ".hpp"}:
        continue
    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    patched, n = font_re.subn('"fonts/DejaVuSans-Bold.ttf"', original)
    patched, n2 = re.subn(r'"DejaVuSans(?:-Bold)?\.ttf"', '"fonts/DejaVuSans-Bold.ttf"', patched)
    if n + n2:
        path.write_text(patched, encoding="utf-8", errors="surrogateescape")
        font_count += n + n2
        changes.append(f"{path.relative_to(RF)}: replaced {n+n2} DejaVu font path(s)")

if font_count == 0:
    changes.append("No distro-specific DejaVu path found (upstream may already be portable)")

# The GNU/Linux upstream starts with graphics/gnugame.jpg ("press space to
# start"). The original desktop build used by this Android-TV port skips that
# first splash. Start the presentation at the Retro Remakes card instead while
# keeping its original duration (state_timmer 350..700).
presentation_cpp = SRC / "presentation_state.cpp"
presentation_text = presentation_cpp.read_text(encoding="utf-8", errors="surrogateescape")
old_presentation_init = """\tif (state_timmer==0) {
\t\tpresentation_state=0;
\t\tpresentation_timmer=0;
\t} /* if */"""
new_presentation_init = """\tif (state_timmer==0) {
\t\t// Android TV: skip the GNU 'press space to start' splash only.
\t\tpresentation_state=2;
\t\tpresentation_timmer=0;
\t\tstate_timmer=350;
\t} /* if */"""
if new_presentation_init in presentation_text:
    changes.append("src/presentation_state.cpp: GNU start splash already skipped")
elif old_presentation_init in presentation_text:
    presentation_text = presentation_text.replace(old_presentation_init, new_presentation_init, 1)
    presentation_cpp.write_text(presentation_text, encoding="utf-8", errors="surrogateescape")
    changes.append("src/presentation_state.cpp: skipped GNU 'press space to start' splash")
else:
    raise SystemExit("Could not find presentation-state initialization to skip GNU splash")

# SDL2 no longer exposes SDL 1.2's PixelFormat::colorkey fallback. The bundled
# SGE collision-map builder calls SDL_GetColorKey() but ignores its -1 result
# when no key is enabled, leaving an uninitialized key value. That can turn the
# black (transparent) half of a collision mask into solid pixels and produces
# phantom hits at road edges / around otherwise invisible sprite pixels. Make
# the intended transparent value explicit after the mask is binarized.
tile_cpp = SRC / "CTile.cpp"
tile_text = tile_cpp.read_text(encoding="utf-8", errors="surrogateescape")
old_collision_setup = """\t\tsurface_bw(mask_collision,128);
\t\tcollision_data=sge_make_cmap(mask_collision);"""
new_collision_setup = """\t\tsurface_bw(mask_collision,128);
\t\t// SDL2: SGE requires an explicit key; transparent mask pixels are RGBA(0,0,0,0).
\t\tconst Uint32 rf_collision_colorkey = SDL_MapRGBA(mask_collision->format,0,0,0,0);
\t\tif (SDL_SetColorKey(mask_collision,SDL_TRUE,rf_collision_colorkey)!=0) {
\t\t\tSDL_Log(\"Road Fighter: could not set collision-mask color key: %s\",SDL_GetError());
\t\t}
\t\tcollision_data=sge_make_cmap(mask_collision);"""
if new_collision_setup in tile_text:
    changes.append("src/CTile.cpp: SDL2 collision-mask color key already explicit")
elif old_collision_setup in tile_text:
    tile_text = tile_text.replace(old_collision_setup, new_collision_setup, 1)
    tile_cpp.write_text(tile_text, encoding="utf-8", errors="surrogateescape")
    changes.append("src/CTile.cpp: set explicit SDL2 collision-mask color key")
else:
    raise SystemExit("Could not find CTile collision-map setup to add SDL2 color key")

# ---- Residual SDL 1.2 -> SDL2 compatibility -------------------------------
# SDL1 SDL_GetKeyState returned a keycode-indexed table and Road Fighter stores
# those numeric SDL1 keycodes in its configuration. Keep legacy keycode semantics
# through rf_sdl12_get_key_state(); direct SDLK_* indexes are translated to their
# corresponding SDL1 numeric index as well.
source_suffixes = {".cpp", ".cc", ".c", ".h", ".hpp"}
legacy_counts = {
    "SDLK_LAST": 0,
    "SDL_GetKeyState": 0,
    "SDL_DisplayFormat": 0,
    "SDL_DisplayFormatAlpha": 0,
    "SDL_SetAlpha": 0,
    "SDL_HWSURFACE_lock_test": 0,
    "SDL_HWSURFACE_flag": 0,
    "key_index": 0,
    "dynamic_key_index": 0,
    "SDLKey": 0,
    "SDL_SetError_nonliteral": 0,
}

# Matches keyboard[SDLK_LEFT] and old_keyboard[SDLK_F1], while leaving event
# comparisons such as event.key.keysym.sym == SDLK_ESCAPE as keycodes.
key_index_re = re.compile(
    r"\b(keyboard|old_keyboard)\s*\[\s*(SDLK_[A-Za-z0-9_]+)\s*\]"
)

for path in sorted(SRC.rglob("*")):
    if path.suffix.lower() not in source_suffixes:
        continue

    original = path.read_text(encoding="utf-8", errors="surrogateescape")
    patched = original

    patched, n = re.subn(r"\bSDLK_LAST\b", "RF_SDL12_KEY_COUNT", patched)
    legacy_counts["SDLK_LAST"] += n

    patched, n = re.subn(r"\bSDL_GetKeyState\s*\(", "rf_sdl12_get_key_state(", patched)
    legacy_counts["SDL_GetKeyState"] += n

    # SDLKey disappeared in SDL2. Preserve keycode semantics for event/config
    # variables; keyboard-state indexes are handled separately below.
    patched, n = re.subn(r"\bSDLKey\b", "SDL_Keycode", patched)
    legacy_counts["SDLKey"] += n

    def repl_index(match: re.Match[str]) -> str:
        legacy_counts["key_index"] += 1
        array_name, key_name = match.group(1), match.group(2)
        return f"{array_name}[rf_sdl12_key_index({key_name})]"

    patched = key_index_re.sub(repl_index, patched)

    # Configuration variables may contain either original SDL1 numeric keycodes
    # (from RoadFighter.cfg) or modern SDL2 SDLK_* values (from upstream defaults).
    # Normalize simple variable/member indexes before accessing the legacy table.
    dynamic_index_re = re.compile(
        r"\b(keyboard|old_keyboard)\s*\[\s*"
        r"([A-Za-z_][A-Za-z0-9_]*(?:(?:->|\.)[A-Za-z_][A-Za-z0-9_]*)*)"
        r"\s*\]"
    )

    def repl_dynamic_index(match: re.Match[str]) -> str:
        array_name, expr = match.group(1), match.group(2)

        # Never rewrite the fixed-size legacy keyboard array declaration.
        # SDLK_LAST is replaced above with RF_SDL12_KEY_COUNT, which is a
        # compile-time macro. Wrapping that macro in rf_sdl12_binding_index()
        # would turn a class member array into an illegal variable-length array.
        if expr == "RF_SDL12_KEY_COUNT":
            return match.group(0)

        legacy_counts["dynamic_key_index"] += 1
        return f"{array_name}[rf_sdl12_binding_index({expr})]"

    patched = dynamic_index_re.sub(repl_dynamic_index, patched)

    # SDL 1.2 display-format helpers were removed in SDL2. Preserve the old
    # "new surface" ownership semantics and convert to the fixed 32-bit logical
    # display format expected by the original SGE-era pixel routines.
    patched, n = re.subn(r"\bSDL_DisplayFormatAlpha\s*\(", "rf_sdl_display_format_alpha(", patched)
    legacy_counts["SDL_DisplayFormatAlpha"] += n

    patched, n = re.subn(r"\bSDL_DisplayFormat\s*\(", "rf_sdl_display_format(", patched)
    legacy_counts["SDL_DisplayFormat"] += n

    # SDL_SetAlpha(flags, alpha) became surface blend mode + alpha modulation
    # in SDL2. Keep the original call sites readable but route them through a
    # small compatibility helper.
    patched, n = re.subn(r"\bSDL_SetAlpha\s*\(", "rf_sdl_set_alpha(", patched)
    legacy_counts["SDL_SetAlpha"] += n

    # SDL_HWSURFACE no longer exists in SDL2. For the legacy pixel-access
    # guards, SDL_MUSTLOCK(surface) is the semantic replacement. Any remaining
    # uses are creation flags, where SDL2 software surfaces use flag 0.
    hw_lock_re = re.compile(
        r"\(\s*([A-Za-z_][A-Za-z0-9_]*)->flags\s*&\s*SDL_HWSURFACE\s*\)\s*!=\s*0"
    )
    patched, n = hw_lock_re.subn(lambda m: f"SDL_MUSTLOCK({m.group(1)})", patched)
    legacy_counts["SDL_HWSURFACE_lock_test"] += n

    patched, n = re.subn(r"\bSDL_HWSURFACE\b", "0", patched)
    legacy_counts["SDL_HWSURFACE_flag"] += n

    # Android/NDK enables -Werror=format-security. Old SGE sometimes passes
    # a preformatted buffer directly to SDL_SetError(), which Clang rejects as
    # a non-literal format string. Preserve the text while using a literal format.
    patched, n = re.subn(
        r"\bSDL_SetError\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;",
        lambda m: f'SDL_SetError("%s", {m.group(1)});',
        patched,
    )
    legacy_counts["SDL_SetError_nonliteral"] += n

    if patched != original:
        path.write_text(patched, encoding="utf-8", errors="surrogateescape")
        changes.append(f"{path.relative_to(RF)}: applied SDL2 compatibility edits")

for name, count in legacy_counts.items():
    changes.append(f"SDL2 compatibility: {name} replacements = {count}")

# The upstream level loader returns false from many strict fscanf checks. The
# original CGame::init_game() reacts to a false result with a naked `throw;`,
# which terminates the process when no exception is active. Instrument every
# loadmg2.cpp failure return so Android logcat identifies the exact parser line
# if a packaged map ever drifts from the pinned source format again.
loadmg2_cpp = SRC / "loadmg2.cpp"
loadmg2_text = loadmg2_cpp.read_text(encoding="utf-8", errors="surrogateescape")
if "rf_android_log_map_failure(mapname, __LINE__)" not in loadmg2_text:
    loadmg2_patched, map_fail_count = re.subn(
        r"\breturn\s+false\s*;",
        "return (rf_android_log_map_failure(mapname, __LINE__), false);",
        loadmg2_text,
    )
    if map_fail_count == 0:
        raise SystemExit("Could not find load_map false-return sites to instrument")
    loadmg2_cpp.write_text(loadmg2_patched, encoding="utf-8", errors="surrogateescape")
    changes.append(f"src/loadmg2.cpp: instrumented {map_fail_count} map-parser failure return(s)")
else:
    changes.append("src/loadmg2.cpp: map-parser failure logging already instrumented")

# Report any legacy calls that should no longer survive. Do not reject normal
# SDL2 SDLK_* keycodes: those remain correct for event.key.keysym.sym.
legacy_patterns = {
    "SDLK_LAST": re.compile(r"\bSDLK_LAST\b"),
    "SDL_GetKeyState": re.compile(r"\bSDL_GetKeyState\s*\("),
    "SDL_DisplayFormat": re.compile(r"\bSDL_DisplayFormat\s*\("),
    "SDL_DisplayFormatAlpha": re.compile(r"\bSDL_DisplayFormatAlpha\s*\("),
    "SDL_SetAlpha": re.compile(r"\bSDL_SetAlpha\s*\("),
    "SDL_HWSURFACE": re.compile(r"\bSDL_HWSURFACE\b"),
    "SDLKey type": re.compile(r"\bSDLKey\b"),
}
leftovers: list[str] = []
for path in sorted(SRC.rglob("*")):
    if path.suffix.lower() not in source_suffixes:
        continue
    data = path.read_text(encoding="utf-8", errors="surrogateescape")
    for label, pattern in legacy_patterns.items():
        if pattern.search(data):
            leftovers.append(f"{path.relative_to(RF)}: still contains {label}")

if leftovers:
    changes.append("WARNING: residual SDL 1.2 symbols:")
    changes.extend(f"  {item}" for item in leftovers)
else:
    changes.append("Residual SDL 1.2 scan: clean for patched compatibility symbols")


# Count SDL 1.2 window/framebuffer APIs intentionally supplied by rf_sdl12_compat.h.
compat_video_symbols = [
    "SDL_VideoDriverName", "SDL_AudioDriverName", "SDL_WM_SetCaption", "SDL_SetVideoMode",
    "SDL_GetVideoSurface", "SDL_EnableUNICODE", "SDL_Flip",
    "SDL_UpdateRect", "SDL_UpdateRects", "SDL_FULLSCREEN", "SDLMod",
]
for symbol in compat_video_symbols:
    count = 0
    pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
    for path in sorted(SRC.rglob("*")):
        if path.suffix.lower() not in source_suffixes:
            continue
        data = path.read_text(encoding="utf-8", errors="surrogateescape")
        count += len(pattern.findall(data))
    changes.append(f"SDL1 video shim: {symbol} occurrences = {count}")

REPORT.write_text("\n".join(changes) + "\n", encoding="utf-8")
print(REPORT.read_text(encoding="utf-8"), end="")
