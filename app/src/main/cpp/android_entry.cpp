#include <SDL.h>
#include <SDL_system.h>
#include <android/log.h>

#include <dlfcn.h>
#include <unwind.h>

#include <cstdint>
#include <cstdlib>
#include <exception>
#include <typeinfo>
#include <unistd.h>

extern int roadfighter_upstream_main(int argc, char **argv);

namespace {
constexpr const char *kLogTag = "RoadFighterTV";
constexpr int kMaxTerminateFrames = 48;

struct UnwindState {
    int frame = 0;
};

_Unwind_Reason_Code logUnwindFrame(_Unwind_Context *context, void *opaque) {
    auto *state = static_cast<UnwindState *>(opaque);
    if (!state || state->frame >= kMaxTerminateFrames) {
        return _URC_END_OF_STACK;
    }

    const uintptr_t pc = static_cast<uintptr_t>(_Unwind_GetIP(context));
    if (pc != 0) {
        Dl_info info{};
        if (dladdr(reinterpret_cast<void *>(pc), &info) != 0 && info.dli_fbase) {
            const uintptr_t base = reinterpret_cast<uintptr_t>(info.dli_fbase);
            const uintptr_t rel = pc >= base ? pc - base : pc;
            __android_log_print(
                    ANDROID_LOG_ERROR,
                    kLogTag,
                    "terminate bt #%02d pc=%p rel=0x%08lx so=%s symbol=%s",
                    state->frame,
                    reinterpret_cast<void *>(pc),
                    static_cast<unsigned long>(rel),
                    info.dli_fname ? info.dli_fname : "?",
                    info.dli_sname ? info.dli_sname : "?");
        } else {
            __android_log_print(
                    ANDROID_LOG_ERROR,
                    kLogTag,
                    "terminate bt #%02d pc=%p",
                    state->frame,
                    reinterpret_cast<void *>(pc));
        }
        ++state->frame;
    }

    return state->frame >= kMaxTerminateFrames ? _URC_END_OF_STACK : _URC_NO_REASON;
}

void logTerminateBacktrace() noexcept {
    UnwindState state{};
    _Unwind_Backtrace(logUnwindFrame, &state);
}

void logCurrentException() noexcept {
    const std::exception_ptr ep = std::current_exception();
    if (!ep) {
        __android_log_write(ANDROID_LOG_ERROR, kLogTag, "std::terminate without active exception");
        return;
    }

    try {
        std::rethrow_exception(ep);
    } catch (const std::exception &e) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                kLogTag,
                "uncaught C++ exception type=%s what=%s",
                typeid(e).name(),
                e.what());
    } catch (...) {
        __android_log_write(ANDROID_LOG_ERROR, kLogTag, "uncaught non-std C++ exception");
    }
}

[[noreturn]] void roadFighterTerminate() noexcept {
    __android_log_write(ANDROID_LOG_ERROR, kLogTag, "std::terminate entered");
    logCurrentException();
    logTerminateBacktrace();
    std::abort();
}
} // namespace

// On Android SDL's main macro turns this into SDL_main, the entry point SDLActivity invokes.
int main(int argc, char **argv) {
    std::set_terminate(roadFighterTerminate);
    __android_log_write(ANDROID_LOG_INFO, kLogTag, "native main started");

    // SDL 2.32.10 prefers OpenSL ES on Android. For an interactive game we
    // explicitly try AAudio first so the backend can request GAME/LOW_LATENCY.
    // If AAudio itself is unavailable during driver initialization, SDL can
    // still fall back to the proven OpenSL ES backend.
    SDL_SetHint(SDL_HINT_AUDIODRIVER, "AAudio,openslES");
    SDL_SetHint(SDL_HINT_TV_REMOTE_AS_JOYSTICK, "0");
    SDL_SetHint(SDL_HINT_RENDER_SCALE_QUALITY, "0");

    const char *storage = SDL_AndroidGetInternalStoragePath();
    if (storage && *storage) {
        chdir(storage);
        setenv("HOME", storage, 1);
        __android_log_print(ANDROID_LOG_INFO, kLogTag, "storage=%s", storage);
    }

    try {
        const int rc = roadfighter_upstream_main(argc, argv);
        __android_log_print(ANDROID_LOG_INFO, kLogTag, "upstream main returned %d", rc);
        return rc;
    } catch (const std::exception &e) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                kLogTag,
                "exception escaped upstream main type=%s what=%s",
                typeid(e).name(),
                e.what());
        logTerminateBacktrace();
        return EXIT_FAILURE;
    } catch (...) {
        __android_log_write(ANDROID_LOG_ERROR, kLogTag, "non-std exception escaped upstream main");
        logTerminateBacktrace();
        return EXIT_FAILURE;
    }
}
