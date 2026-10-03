#!/usr/bin/env python3
"""Patch pinned SDL2 AAudio for Road Fighter's interactive Android-TV audio."""
from pathlib import Path
import re
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one upstream match, found {count}")
    return text.replace(old, new, 1)


def replace_c_function_once(text: str, function_name: str, new: str, marker: str, label: str) -> str:
    """Replace one complete static C function without depending on its body formatting."""
    if marker in text:
        return text

    signature = re.compile(
        rf"(?m)^static\s+void\s+{re.escape(function_name)}\s*\(\s*_THIS\s*\)\s*\{{"
    )
    matches = list(signature.finditer(text))
    if len(matches) != 1:
        raise SystemExit(
            f"ERROR: {label}: expected exactly one {function_name} definition, found {len(matches)}"
        )

    match = matches[0]
    open_brace = text.rfind("{", match.start(), match.end())
    if open_brace < 0:
        raise SystemExit(f"ERROR: {label}: opening brace not found")

    # Find the matching closing brace while ignoring braces inside comments,
    # character literals and string literals. This is deliberately small, but
    # it is much more robust than regex-matching an entire C function body.
    depth = 1
    i = open_brace + 1
    state = "code"
    quote = ""
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""

        if state == "line_comment":
            if ch == "\n":
                state = "code"
        elif state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "code"
                i += 1
        elif state == "string":
            if ch == "\\":
                i += 1
            elif ch == quote:
                state = "code"
        else:
            if ch == "/" and nxt == "/":
                state = "line_comment"
                i += 1
            elif ch == "/" and nxt == "*":
                state = "block_comment"
                i += 1
            elif ch in ("\"", "'"):
                state = "string"
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    replacement = new.rstrip() + "\n"
                    # Consume one existing line ending after the old function so
                    # the replacement does not create accidental blank-line drift.
                    if text.startswith("\r\n", end):
                        end += 2
                    elif text.startswith("\n", end):
                        end += 1
                    return text[:match.start()] + replacement + text[end:]
        i += 1

    raise SystemExit(f"ERROR: {label}: closing brace not found")


def insert_before_line_once(text: str, pattern: str, insertion: str, marker: str, label: str) -> str:
    """Insert text immediately before one stable line, tolerating whitespace drift."""
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one upstream line match, found {len(matches)}")
    match = matches[0]
    nearby = text[max(0, match.start() - 256):match.start()]
    if marker in nearby:
        return text
    return text[:match.start()] + insertion + text[match.start():]


def insert_after_line_once(text: str, pattern: str, insertion: str, marker: str, label: str) -> str:
    """Insert text immediately after one stable line, tolerating whitespace drift."""
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 1:
        raise SystemExit(f"ERROR: {label}: expected exactly one upstream line match, found {len(matches)}")
    match = matches[0]
    end = match.end()
    nearby = text[end:end + 512]
    if marker in nearby:
        return text
    return text[:end] + "\n" + insertion + text[end:]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: prepare_sdl_audio.py <SDL checkout>")

    sdl = Path(sys.argv[1])
    aaudio_c = sdl / "src/audio/aaudio/SDL_aaudio.c"
    funcs_h = sdl / "src/audio/aaudio/SDL_aaudiofuncs.h"
    if not aaudio_c.is_file() or not funcs_h.is_file():
        raise SystemExit(f"ERROR: SDL AAudio sources not found under {sdl}")

    funcs = funcs_h.read_text(encoding="utf-8")
    used_functions = [
        "AAudioStreamBuilder_setSharingMode",
        "AAudioStreamBuilder_setPerformanceMode",
        "AAudioStreamBuilder_setUsage",
        "AAudioStreamBuilder_setContentType",
        "AAudioStream_setBufferSizeInFrames",
        "AAudioStream_getBufferSizeInFrames",
        "AAudioStream_getFramesPerBurst",
        "AAudioStream_getBufferCapacityInFrames",
        "AAudioStream_getSharingMode",
        "AAudioStream_getPerformanceMode",
        "AAudioStream_getUsage",
        "AAudioStream_getContentType",
    ]
    for fn in used_functions:
        lines = funcs.splitlines()
        matched = [line for line in lines if fn in line]
        if len(matched) != 1:
            raise SystemExit(f"ERROR: {fn}: expected one declaration, found {len(matched)}")
        line = matched[0]
        if line.startswith("SDL_PROC("):
            continue
        if not line.startswith("SDL_PROC_UNUSED("):
            raise SystemExit(f"ERROR: {fn}: unexpected declaration: {line}")
        funcs = funcs.replace(line, line.replace("SDL_PROC_UNUSED(", "SDL_PROC(", 1), 1)
    funcs_h.write_text(funcs, encoding="utf-8")

    src = aaudio_c.read_text(encoding="utf-8")
    src = replace_once(
        src,
        '#include "../../core/android/SDL_android.h"\n',
        '#include "../../core/android/SDL_android.h"\n#include <android/log.h>\n',
        "android log include",
    )

    helper_anchor = '#define LIB_AAUDIO_SO "libaaudio.so"\n\n'
    helper = r'''#define LIB_AAUDIO_SO "libaaudio.so"

/*
 * Road Fighter is an interactive game, not a media player. SDL 2.32.10's
 * AAudio backend otherwise leaves performance mode at NONE and usage at MEDIA.
 * Keep the GAME/LOW_LATENCY/EXCLUSIVE request because the Google TV Streamer
 * did grant a direct MMAP HDMI path instead of the several-hundred-ms deep
 * buffer used by Automatic output mode.
 */
static void aaudio_ConfigureRoadFighterOutput(AAudioStreamBuilder *builder)
{
    ctx.AAudioStreamBuilder_setPerformanceMode(builder, AAUDIO_PERFORMANCE_MODE_LOW_LATENCY);
    ctx.AAudioStreamBuilder_setSharingMode(builder, AAUDIO_SHARING_MODE_EXCLUSIVE);
    if (SDL_GetAndroidSDKVersion() >= 28) {
        ctx.AAudioStreamBuilder_setUsage(builder, AAUDIO_USAGE_GAME);
        ctx.AAudioStreamBuilder_setContentType(builder, AAUDIO_CONTENT_TYPE_SONIFICATION);
    }
}

/*
 * The tested HDMI MMAP stream reports a 768-frame hardware burst. Two bursts
 * provide enough headroom for SDL2's blocking writer while remaining far
 * shallower than the normal HDMI deep-buffer route.
 */
static void aaudio_TuneRoadFighterOutput(AAudioStream *stream)
{
    const int32_t burst = ctx.AAudioStream_getFramesPerBurst(stream);
    if (burst > 0) {
        const int32_t requested = burst * 2;
        const aaudio_result_t actual = ctx.AAudioStream_setBufferSizeInFrames(stream, requested);
        __android_log_print(actual >= 0 ? ANDROID_LOG_INFO : ANDROID_LOG_WARN, "RoadFighterTV",
                            "AAudio buffer tune burst=%d requested=%d actual=%d",
                            burst, requested, (int)actual);
    }
}

static void aaudio_LogRoadFighterOutput(AAudioStream *stream)
{
    const int32_t burst = ctx.AAudioStream_getFramesPerBurst(stream);
    const int32_t buffer = ctx.AAudioStream_getBufferSizeInFrames(stream);
    const int32_t capacity = ctx.AAudioStream_getBufferCapacityInFrames(stream);
    const int perf = (int)ctx.AAudioStream_getPerformanceMode(stream);
    const int sharing = (int)ctx.AAudioStream_getSharingMode(stream);
    const int usage = SDL_GetAndroidSDKVersion() >= 28 ? (int)ctx.AAudioStream_getUsage(stream) : -1;
    const int content = SDL_GetAndroidSDKVersion() >= 28 ? (int)ctx.AAudioStream_getContentType(stream) : -1;
    __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
                        "AAudio game path perf=%d sharing=%d usage=%d content=%d burst=%d buffer=%d capacity=%d rate=%d channels=%d xruns=%d",
                        perf, sharing, usage, content, burst, buffer, capacity,
                        ctx.AAudioStream_getSampleRate(stream),
                        ctx.AAudioStream_getChannelCount(stream),
                        ctx.AAudioStream_getXRunCount(stream));
}

'''
    src = replace_once(src, helper_anchor, helper, "AAudio game helper")

    src = insert_before_line_once(
        src,
        r"^[ \t]*ctx\.AAudioStreamBuilder_setErrorCallback\(\s*ctx\.builder\s*,\s*aaudio_errorCallback\s*,\s*private\s*\);[ \t]*$",
        "    if (!iscapture) {\n        aaudio_ConfigureRoadFighterOutput(ctx.builder);\n    }\n",
        "aaudio_ConfigureRoadFighterOutput(ctx.builder);",
        "AAudio initial output configuration",
    )

    src = insert_before_line_once(
        src,
        r"^[ \t]*ctx\.AAudioStreamBuilder_setErrorCallback\(\s*ctx\.builder\s*,\s*aaudio_errorCallback\s*,\s*hidden\s*\);[ \t]*$",
        "    if (!iscapture) {\n        aaudio_ConfigureRoadFighterOutput(ctx.builder);\n    }\n",
        "aaudio_ConfigureRoadFighterOutput(ctx.builder);",
        "AAudio rebuild output configuration",
    )

    src = insert_after_line_once(
        src,
        r"^[ \t]*this->spec\.channels\s*=\s*ctx\.AAudioStream_getChannelCount\(private->stream\);[ \t]*$",
        "    if (!iscapture) {\n        aaudio_TuneRoadFighterOutput(private->stream);\n        aaudio_LogRoadFighterOutput(private->stream);\n    }",
        "aaudio_TuneRoadFighterOutput(private->stream);",
        "AAudio actual-path tuning/logging",
    )

    # SDL 2.32.10 uses a 1 ms AAudioStream_write timeout and accepts a short
    # write as if the whole mixer block was consumed. On the Streamer's HDMI
    # MMAP path the hardware burst is 768 frames while our mixer block is 512.
    # A 1 ms timeout can therefore return a short/zero write before the next
    # 16 ms hardware burst, dropping the rest of the block. Write every frame
    # and allow enough time for the HDMI burst to drain.
    play_device = r'''static void aaudio_PlayDevice(_THIS)
{
    struct SDL_PrivateAudioData *private = this->hidden;
    const int32_t frame_count = (int32_t)(private->mixlen / private->frame_size);
    const int64_t timeoutNanoseconds = 50LL * 1000LL * 1000LL;
    const Uint8 *src = private->mixbuf;
    int32_t remaining = frame_count;

    while (remaining > 0) {
        const aaudio_result_t res = ctx.AAudioStream_write(private->stream, src, remaining, timeoutNanoseconds);
        if (res < 0) {
            __android_log_print(ANDROID_LOG_WARN, "RoadFighterTV",
                                "AAudio write error=%d remaining=%d xruns=%d",
                                (int)res, remaining, ctx.AAudioStream_getXRunCount(private->stream));
            if (RecoverAAudioDevice(this) < 0) {
                return;
            }
            return;
        }
        if (res == 0) {
            __android_log_print(ANDROID_LOG_WARN, "RoadFighterTV",
                                "AAudio write timeout remaining=%d/%d xruns=%d",
                                remaining, frame_count, ctx.AAudioStream_getXRunCount(private->stream));
            return;
        }
        src += ((size_t)res * private->frame_size);
        remaining -= (int32_t)res;
    }
}
'''
    src = replace_c_function_once(
        src,
        "aaudio_PlayDevice",
        play_device,
        "AAudio write timeout remaining=",
        "AAudio full-block output writer",
    )

    aaudio_c.write_text(src, encoding="utf-8")
    print("Patched SDL2 AAudio for Road Fighter: GAME/LOW_LATENCY/MMAP plus robust full-block HDMI writes.")


if __name__ == "__main__":
    main()
