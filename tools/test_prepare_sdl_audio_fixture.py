#!/usr/bin/env python3
"""Offline regression test for the pinned SDL 2.32.10 AAudio transformation."""
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCHER = ROOT / "tools" / "prepare_sdl_audio.py"

AAUDIO_C = r'''#include "../../SDL_internal.h"
#ifdef SDL_AUDIO_DRIVER_AAUDIO
#include "../../core/android/SDL_android.h"
#include "SDL_aaudio.h"

typedef struct AAUDIO_Data
{
#define SDL_PROC(ret, func, params) ret (*func) params;
#include "SDL_aaudiofuncs.h"
#undef SDL_PROC
} AAUDIO_Data;
static AAUDIO_Data ctx;

#define LIB_AAUDIO_SO "libaaudio.so"

static int aaudio_OpenDevice(_THIS, const char *devname)
{
    struct SDL_PrivateAudioData *private;
    SDL_bool iscapture = this->iscapture;
    ctx.AAudioStreamBuilder_setSampleRate(ctx.builder, this->spec.freq);
    ctx.AAudioStreamBuilder_setChannelCount(ctx.builder, this->spec.channels);
    {
        const aaudio_format_t format = (this->spec.format == AUDIO_S16SYS) ? AAUDIO_FORMAT_PCM_I16 : AAUDIO_FORMAT_PCM_FLOAT;
        ctx.AAudioStreamBuilder_setFormat(ctx.builder, format);
    }

    /* Harmless formatting/context drift must not break the patch. */
    ctx.AAudioStreamBuilder_setErrorCallback( ctx.builder, aaudio_errorCallback, private );
    res = ctx.AAudioStreamBuilder_openStream(ctx.builder, &private->stream);
    this->spec.freq = ctx.AAudioStream_getSampleRate(private->stream);
    this->spec.channels = ctx.AAudioStream_getChannelCount(private->stream);
    return 0;
}

static int RebuildAAudioStream(SDL_AudioDevice *device)
{
    struct SDL_PrivateAudioData *hidden = device->hidden;
    const SDL_bool iscapture = device->iscapture;
    ctx.AAudioStreamBuilder_setSampleRate(ctx.builder, device->spec.freq);
    ctx.AAudioStreamBuilder_setChannelCount(ctx.builder, device->spec.channels);
    {
        const aaudio_format_t format = (device->spec.format == AUDIO_S16SYS) ? AAUDIO_FORMAT_PCM_I16 : AAUDIO_FORMAT_PCM_FLOAT;
        ctx.AAudioStreamBuilder_setFormat(ctx.builder, format);
    }
    ctx.AAudioStreamBuilder_setErrorCallback(ctx.builder, aaudio_errorCallback, hidden);
    return 0;
}

static int RecoverAAudioDevice(SDL_AudioDevice *device)
{
    return 0;
}

static void aaudio_PlayDevice(_THIS)
{
    struct SDL_PrivateAudioData *private = this->hidden;
    aaudio_result_t res;
    int64_t timeoutNanoseconds = 1 * 1000 * 1000; /* 8 ms */
    res = ctx.AAudioStream_write(private->stream, private->mixbuf, private->mixlen / private->frame_size, timeoutNanoseconds);
    if (res < 0) {
        LOGI("%s : %s", __func__, ctx.AAudio_convertResultToText(res));
        if (RecoverAAudioDevice(this) < 0) {
            return;  /* oh well, we went down hard. */
        }
    } else {
        LOGI("SDL AAudio play: %d frames, wanted:%d frames", (int)res, private->mixlen / private->frame_size);
    }
#if 0
    /* Log under-run count; braces in comments { } must not confuse the patcher. */
    {
        static int prev = 0;
        int32_t cnt = ctx.AAudioStream_getXRunCount(private->stream);
        if (cnt != prev) {
            SDL_Log("AAudio underrun: %d - total: %d", cnt - prev, cnt);
            prev = cnt;
        }
    }
#endif
}
static int aaudio_CaptureFromDevice(_THIS, void *buffer, int buflen)
{
    return 0;
}
#endif
'''

FUNCS = '''#define SDL_PROC_UNUSED(ret, func, params)\nSDL_PROC_UNUSED(void, AAudioStreamBuilder_setSharingMode, (void))\nSDL_PROC_UNUSED(void, AAudioStreamBuilder_setPerformanceMode, (void))\nSDL_PROC_UNUSED(void, AAudioStreamBuilder_setUsage, (void))\nSDL_PROC_UNUSED(void, AAudioStreamBuilder_setContentType, (void))\nSDL_PROC_UNUSED(int, AAudioStream_setBufferSizeInFrames, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getBufferSizeInFrames, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getFramesPerBurst, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getBufferCapacityInFrames, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getSharingMode, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getPerformanceMode, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getUsage, (void))\nSDL_PROC_UNUSED(int, AAudioStream_getContentType, (void))\nSDL_PROC(int, AAudioStream_getXRunCount, (void))\n'''

with tempfile.TemporaryDirectory(prefix="rf-sdl-aaudio-test-") as tmp:
    sdl = Path(tmp)
    audio = sdl / "src" / "audio" / "aaudio"
    audio.mkdir(parents=True)
    (audio / "SDL_aaudio.c").write_text(AAUDIO_C, encoding="utf-8")
    (audio / "SDL_aaudiofuncs.h").write_text(FUNCS, encoding="utf-8")

    for _ in range(2):
        subprocess.run([sys.executable, str(PATCHER), str(sdl)], check=True)

    patched = (audio / "SDL_aaudio.c").read_text(encoding="utf-8")
    funcs = (audio / "SDL_aaudiofuncs.h").read_text(encoding="utf-8")

    assert patched.count("aaudio_ConfigureRoadFighterOutput(ctx.builder);") == 2
    assert patched.count("aaudio_TuneRoadFighterOutput(private->stream);") == 1
    assert patched.count("aaudio_LogRoadFighterOutput(private->stream);") == 1
    assert "AAUDIO_PERFORMANCE_MODE_LOW_LATENCY" in patched
    assert "AAUDIO_SHARING_MODE_EXCLUSIVE" in patched
    assert "AAUDIO_USAGE_GAME" in patched
    assert "AAudio buffer tune burst=%d requested=%d actual=%d" in patched
    assert "const int64_t timeoutNanoseconds = 50LL * 1000LL * 1000LL;" in patched
    assert "while (remaining > 0)" in patched
    assert "AAudio write timeout remaining=%d/%d xruns=%d" in patched
    assert patched.count("static void aaudio_PlayDevice(_THIS)") == 1
    assert "static int aaudio_CaptureFromDevice(_THIS, void *buffer, int buflen)" in patched
    assert "1 * 1000 * 1000" not in patched
    assert "SDL_PROC_UNUSED(void, AAudioStreamBuilder_setPerformanceMode" not in funcs
    assert "SDL_PROC(void, AAudioStreamBuilder_setPerformanceMode" in funcs
    assert "SDL_PROC_UNUSED(int, AAudioStream_setBufferSizeInFrames" not in funcs
    assert "SDL_PROC(int, AAudioStream_setBufferSizeInFrames" in funcs

print("SDL 2.32.10 AAudio full-write/buffer patch fixture test: OK")
