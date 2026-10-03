#!/usr/bin/env python3
"""Regression tests for SDL1->SDL2 text transformations used by prepare_upstream.py."""
import re
from pathlib import Path

sample = r'''
unsigned char *keyboard,old_keyboard[SDLK_LAST];
for(i=0;i<SDLK_LAST;i++) old_keyboard[i]=0;
sfc = SDL_DisplayFormat(konami1_sfc);
tmp = SDL_DisplayFormatAlpha(orig);
keyboard = (unsigned char *)SDL_GetKeyState(NULL);
if (keyboard[SDLK_LEFT] && !old_keyboard[SDLK_F1]) {}
if (keyboard[player_left_key]) {}
if (event.key.keysym.sym == SDLK_ESCAPE) {}
SDL_SetAlpha(orig,0,SDL_ALPHA_OPAQUE);
SDL_SetAlpha(orig,SDL_SRCALPHA,SDL_ALPHA_OPAQUE);
if ((surface->flags&SDL_HWSURFACE)!=0) SDL_LockSurface(surface);
sfc = SDL_CreateRGBSurface(SDL_HWSURFACE, w, h, 32, 0,0,0,AMASK);
char buf[128]; SDL_SetError(buf);
'''

text = re.sub(r"\bSDLK_LAST\b", "RF_SDL12_KEY_COUNT", sample)
text = re.sub(r"\bSDL_GetKeyState\s*\(", "rf_sdl12_get_key_state(", text)
text = re.sub(
    r"\b(keyboard|old_keyboard)\s*\[\s*(SDLK_[A-Za-z0-9_]+)\s*\]",
    lambda m: f"{m.group(1)}[rf_sdl12_key_index({m.group(2)})]",
    text,
)
def repl_dynamic_index(m):
    array_name, expr = m.group(1), m.group(2)
    if expr == "RF_SDL12_KEY_COUNT":
        return m.group(0)
    return f"{array_name}[rf_sdl12_binding_index({expr})]"

text = re.sub(
    r"\b(keyboard|old_keyboard)\s*\[\s*"
    r"([A-Za-z_][A-Za-z0-9_]*(?:(?:->|\.)[A-Za-z_][A-Za-z0-9_]*)*)"
    r"\s*\]",
    repl_dynamic_index,
    text,
)
text = re.sub(r"\bSDL_DisplayFormatAlpha\s*\(", "rf_sdl_display_format_alpha(", text)
text = re.sub(r"\bSDL_DisplayFormat\s*\(", "rf_sdl_display_format(", text)
text = re.sub(r"\bSDL_SetAlpha\s*\(", "rf_sdl_set_alpha(", text)
text = re.sub(
    r"\(\s*([A-Za-z_][A-Za-z0-9_]*)->flags\s*&\s*SDL_HWSURFACE\s*\)\s*!=\s*0",
    lambda m: f"SDL_MUSTLOCK({m.group(1)})",
    text,
)
text = re.sub(r"\bSDL_HWSURFACE\b", "0", text)
text = re.sub(
    r"\bSDL_SetError\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;",
    lambda m: f'SDL_SetError("%s", {m.group(1)});',
    text,
)

assert "SDLK_LAST" not in text
assert "old_keyboard[RF_SDL12_KEY_COUNT]" in text
assert "old_keyboard[rf_sdl12_binding_index(RF_SDL12_KEY_COUNT)]" not in text
assert "SDL_GetKeyState(" not in text
assert "SDL_GetKeyboardState(" not in text
assert "SDL_DisplayFormat(" not in text
assert "SDL_DisplayFormatAlpha(" not in text
assert "SDL_SetAlpha(" not in text
assert "SDL_HWSURFACE" not in text
assert "keyboard[rf_sdl12_key_index(SDLK_LEFT)]" in text
assert "old_keyboard[rf_sdl12_key_index(SDLK_F1)]" in text
# Dynamic configuration indexes must stay untouched: they already contain old SDL1 keycodes.
assert "keyboard[rf_sdl12_binding_index(player_left_key)]" in text
# Event keycodes must remain SDL2 keycodes.
assert "event.key.keysym.sym == SDLK_ESCAPE" in text
assert "SDL_MUSTLOCK(surface)" in text
assert "SDL_CreateRGBSurface(0, w, h" in text
assert "rf_sdl_display_format_alpha(orig)" in text
assert "rf_sdl_set_alpha(orig,SDL_SRCALPHA,SDL_ALPHA_OPAQUE)" in text
assert 'SDL_SetError("%s", buf);' in text
print("prepare_upstream SDL compatibility regression test: OK")

root = Path(__file__).resolve().parents[1]
compat_h = (root / "app/src/main/cpp/rf_sdl12_compat.h").read_text()
prepare = (root / "tools/prepare_upstream.py").read_text()
fetch = (root / "tools/fetch-native-deps.sh").read_text()
bridge = (root / "app/src/main/cpp/platform_bridge.cpp").read_text()
cmake = (root / "app/src/main/cpp/CMakeLists.txt").read_text()
activity = (root / "app/src/main/java/io/github/roadfighter/tv/RoadFighterActivity.java").read_text()
manifest = (root / "app/src/main/AndroidManifest.xml").read_text()
strings = (root / "app/src/main/res/values/strings.xml").read_text()
gradle = (root / "app/build.gradle.kts").read_text()
launcher_adaptive = (root / "app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml").read_text()

for symbol in [
    "rf_sdl12_get_key_state", "rf_sdl12_key_index", "rf_sdl12_binding_index", "RF_SDL12_KEY_COUNT",
    "SDL_VideoDriverName", "SDL_AudioDriverName", "SDL_WM_SetCaption", "SDL_SetVideoMode",
    "SDL_GetVideoSurface", "SDL_EnableUNICODE", "SDL_Flip",
    "SDL_UpdateRect", "SDL_UpdateRects", "SDLMod", "SDL_FULLSCREEN",
]:
    assert symbol in compat_h, f"missing compatibility declaration/constant: {symbol}"

for symbol in [
    "rf_sdl12_get_key_state", "rf_sdl12_key_index", "rf_sdl12_binding_index",
    "SDL_VideoDriverName", "SDL_AudioDriverName", "SDL_WM_SetCaption", "SDL_SetVideoMode",
    "SDL_GetVideoSurface", "SDL_EnableUNICODE", "SDL_Flip",
    "SDL_UpdateRect", "SDL_UpdateRects",
]:
    assert symbol in bridge, f"missing compatibility implementation: {symbol}"

assert "SDL_PIXELFORMAT_RGB888" in compat_h
assert "SDL_PIXELFORMAT_ARGB8888" in compat_h
assert "SDL_PIXELFORMAT_RGB888" in bridge
assert "logical framebuffer %dx%d RGB888(no alpha)" in bridge
assert "--wrap=SDL_GetKeyboardState" not in cmake
assert "rf_android_log_map_failure" in compat_h
assert "rf_android_log_map_failure" in bridge
assert "loadmg2.cpp: instrumented" in prepare
assert "presentation_state=2" in prepare
assert "state_timmer=350" in prepare
assert "skip the GNU 'press space to start' splash" in prepare
assert "SDL_MapRGBA(mask_collision->format,0,0,0,0)" in prepare
assert "SDL_SetColorKey(mask_collision,SDL_TRUE,rf_collision_colorkey)" in prepare
assert "maps graphics sound" in fetch
assert "Synced pinned upstream maps/graphics/sound" in fetch
assert "constexpr int kFallbackAndroidAudioChunkFrames = 1024;" in bridge
assert "g_androidPreferredSampleRate" in bridge
assert "g_androidPreferredFramesPerBuffer" in bridge
assert "std::min(requestedChunkFrames, kFallbackAndroidAudioChunkFrames)" in bridge
assert "Mix_OpenAudio requested=%dHz/%dfr native=%dHz/%dfr effective=%dHz/%dfr" in bridge
assert "__real_Mix_OpenAudio(\n            effectiveFrequency, format, channels, effectiveChunkFrames)" in bridge
assert "__real_Mix_OpenAudio(frequency, format, channels, 4096)" not in bridge
assert "PROPERTY_OUTPUT_SAMPLE_RATE" in activity
assert "PROPERTY_OUTPUT_FRAMES_PER_BUFFER" in activity
assert "nativeConfigureAudio" in activity
print("SDL 1.2 runtime compatibility + low-latency audio shim test: OK")

assert "nativeRequestQuit" in activity
assert "nativeRequestQuit" in bridge
assert "KEYCODE_BUTTON_14" in activity
assert "scanCode == 269 || scanCode == 301 || scanCode == 522" in activity
assert "KEYCODE_STAR" in activity
assert "public void finish()" in activity
assert "finishAndRemoveTask()" in activity
assert "System.exit(0)" in activity
assert "protected void main()" not in activity
assert "Road Fighter Remake" in strings
assert 'android:icon="@mipmap/ic_launcher"' in manifest
assert 'android:roundIcon=' not in manifest
assert 'android:appCategory="game"' in manifest
assert 'android:isGame="true"' in manifest
assert 'android.software.leanback" android:required="true"' in manifest
assert 'versionName = "1.0.0"' in gradle
assert 'versionCode = 23' in gradle
assert '"armeabi-v7a", "arm64-v8a"' in gradle
assert 'ndkVersion = "30.0.16248370"' in gradle
assert '@drawable/ic_launcher_foreground' in launcher_adaptive
assert (root / "app/src/main/res/drawable-nodpi/ic_launcher_foreground.png").is_file()
for density in ["mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi"]:
    assert (root / f"app/src/main/res/mipmap-{density}/ic_launcher.png").is_file()
print("Android TV quit/relaunch + launcher identity regression test: OK")

# v0.3.2 Android game-audio routing checks
entry = (root / "app/src/main/cpp/android_entry.cpp").read_text(encoding="utf-8")
assert 'SDL_SetHint(SDL_HINT_AUDIODRIVER, "AAudio,openslES")' in entry
audio_patch = (root / "tools/prepare_sdl_audio.py").read_text(encoding="utf-8")
assert "AAUDIO_PERFORMANCE_MODE_LOW_LATENCY" in audio_patch
assert "AAUDIO_SHARING_MODE_EXCLUSIVE" in audio_patch
assert "AAUDIO_USAGE_GAME" in audio_patch
assert "AAudio game path perf=%d sharing=%d usage=%d" in audio_patch
assert "AAudioStream_setBufferSizeInFrames" in audio_patch
assert "timeoutNanoseconds = 50LL * 1000LL * 1000LL" in audio_patch
assert "while (remaining > 0)" in audio_patch
assert "AAudio write timeout remaining=%d/%d xruns=%d" in audio_patch
fetch = (root / "tools/fetch-native-deps.sh").read_text(encoding="utf-8")
assert 'prepare_sdl_audio.py" "$VENDOR/SDL"' in fetch
assert (root / "tools/test_prepare_sdl_audio_fixture.py").is_file()
workflow = (root / ".github/workflows/ci.yml").read_text(encoding="utf-8")
assert "Test SDL AAudio patcher offline" in workflow
assert "test_prepare_sdl_audio_fixture.py" in workflow
print("AAudio game-path preparation test: OK")
