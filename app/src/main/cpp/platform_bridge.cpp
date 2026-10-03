#include <jni.h>
#include <SDL.h>
#include <SDL_mixer.h>
#include <android/log.h>

#include <algorithm>
#include <atomic>
#include <cstring>
#include <string>

namespace {
constexpr int kPlayers = 2;
constexpr int kControls = 7;
enum Control { LEFT = 0, RIGHT, UP, DOWN, GAS, BACK, START };

std::atomic_bool g_control[kPlayers][kControls];
SDL_Window *g_game_window = nullptr;
SDL_Surface *g_logical_surface = nullptr;
SDL_Renderer *g_renderer = nullptr;
SDL_Texture *g_frame_texture = nullptr;
constexpr int kLogicalWidth = 512;
constexpr int kLogicalHeight = 384;
constexpr int kDefaultVolume = (MIX_MAX_VOLUME * 30) / 100;
constexpr int kFallbackAndroidAudioChunkFrames = 1024;
std::atomic_int g_androidPreferredSampleRate{0};
std::atomic_int g_androidPreferredFramesPerBuffer{0};
std::atomic_bool g_androidClaimsLowLatency{false};
std::string g_window_title = "Road Fighter";
int g_unicode_enabled = 0;

SDL_Scancode scancodeFor(int player, int control) {
    if (player == 0) {
        switch (control) {
            case LEFT: return SDL_SCANCODE_LEFT;
            case RIGHT: return SDL_SCANCODE_RIGHT;
            case UP: return SDL_SCANCODE_UP;
            case DOWN: return SDL_SCANCODE_DOWN;
            case GAS: return SDL_SCANCODE_SPACE;
            case BACK: return SDL_SCANCODE_ESCAPE;
            case START: return SDL_SCANCODE_F1;
            default: return SDL_SCANCODE_UNKNOWN;
        }
    }

    switch (control) {
        case LEFT: return SDL_SCANCODE_A;
        case RIGHT: return SDL_SCANCODE_D;
        case GAS: return SDL_SCANCODE_LSHIFT;
        case BACK: return SDL_SCANCODE_ESCAPE;
        case START: return SDL_SCANCODE_F1;
        // Player 2 does not need separate menu up/down bindings in the original game.
        default: return SDL_SCANCODE_UNKNOWN;
    }
}

bool aggregateDown(SDL_Scancode scancode) {
    if (scancode == SDL_SCANCODE_UNKNOWN) return false;
    for (int p = 0; p < kPlayers; ++p) {
        for (int c = 0; c < kControls; ++c) {
            if (scancodeFor(p, c) == scancode && g_control[p][c].load(std::memory_order_relaxed)) {
                return true;
            }
        }
    }
    return false;
}

bool aggregateControlDown(int control) {
    if (control < 0 || control >= kControls) return false;
    for (int p = 0; p < kPlayers; ++p) {
        if (g_control[p][control].load(std::memory_order_relaxed)) return true;
    }
    return false;
}

void pushKey(SDL_Scancode scancode, bool down) {
    if (scancode == SDL_SCANCODE_UNKNOWN || (SDL_WasInit(SDL_INIT_EVENTS) == 0)) return;

    SDL_Event event{};
    event.type = down ? SDL_KEYDOWN : SDL_KEYUP;
    event.key.type = event.type;
    event.key.timestamp = SDL_GetTicks();
    event.key.state = down ? SDL_PRESSED : SDL_RELEASED;
    event.key.repeat = 0;
    event.key.keysym.scancode = scancode;
    event.key.keysym.sym = SDL_GetKeyFromScancode(scancode);
    event.key.keysym.mod = KMOD_NONE;
    SDL_PushEvent(&event);
}

void setControl(int player, int control, bool down) {
    if (player < 0 || player >= kPlayers || control < 0 || control >= kControls) return;

    const SDL_Scancode scancode = scancodeFor(player, control);
    const bool oldAggregate = aggregateDown(scancode);
    const bool oldConfirm = (control == GAS) ? aggregateControlDown(GAS) : false;
    const bool old = g_control[player][control].exchange(down, std::memory_order_relaxed);
    if (old == down) return;
    const bool newAggregate = aggregateDown(scancode);
    if (oldAggregate != newAggregate) pushKey(scancode, newAggregate);

    // Physical B is both gas and confirm. The original intro/menu code uses
    // a mix of Space and Return depending on state, so emit Return too.
    if (control == GAS) {
        const bool newConfirm = aggregateControlDown(GAS);
        if (oldConfirm != newConfirm) pushKey(SDL_SCANCODE_RETURN, newConfirm);
    }
}

void resetPlayer(int player) {
    if (player < 0 || player >= kPlayers) return;
    for (int c = 0; c < kControls; ++c) setControl(player, c, false);
}
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_roadfighter_tv_RoadFighterActivity_nativeControl(
        JNIEnv *, jclass, jint playerIndex, jint control, jboolean down) {
    setControl(static_cast<int>(playerIndex), static_cast<int>(control), down == JNI_TRUE);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_roadfighter_tv_RoadFighterActivity_nativeResetPlayer(
        JNIEnv *, jclass, jint playerIndex) {
    resetPlayer(static_cast<int>(playerIndex));
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_roadfighter_tv_RoadFighterActivity_nativeResetAll(JNIEnv *, jclass) {
    resetPlayer(0);
    resetPlayer(1);
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_roadfighter_tv_RoadFighterActivity_nativeConfigureAudio(
        JNIEnv *, jclass, jint sampleRate, jint framesPerBuffer, jboolean lowLatencyFeature) {
    const int rate = static_cast<int>(sampleRate);
    const int frames = static_cast<int>(framesPerBuffer);

    // Android documents these as device-specific values. Reject implausible data
    // rather than feeding a bad vendor property into SDL/OpenSL ES.
    g_androidPreferredSampleRate.store(
            (rate >= 8000 && rate <= 192000) ? rate : 0,
            std::memory_order_relaxed);
    g_androidPreferredFramesPerBuffer.store(
            (frames >= 32 && frames <= 4096) ? frames : 0,
            std::memory_order_relaxed);
    g_androidClaimsLowLatency.store(lowLatencyFeature == JNI_TRUE, std::memory_order_relaxed);

    __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
            "native audio config preferredRate=%d preferredFrames=%d lowLatencyFeature=%s",
            g_androidPreferredSampleRate.load(std::memory_order_relaxed),
            g_androidPreferredFramesPerBuffer.load(std::memory_order_relaxed),
            g_androidClaimsLowLatency.load(std::memory_order_relaxed) ? "true" : "false");
}

extern "C" JNIEXPORT void JNICALL
Java_io_github_roadfighter_tv_RoadFighterActivity_nativeRequestQuit(JNIEnv *, jclass) {
    if (SDL_WasInit(SDL_INIT_EVENTS) == 0) {
        __android_log_write(ANDROID_LOG_WARN, "RoadFighterTV",
                "quit requested before SDL event subsystem was ready");
        return;
    }

    SDL_Event event{};
    event.type = SDL_QUIT;
    event.quit.type = SDL_QUIT;
    event.quit.timestamp = SDL_GetTicks();
    if (SDL_PushEvent(&event) < 0) {
        __android_log_print(ANDROID_LOG_ERROR, "RoadFighterTV",
                "SDL_PushEvent(SDL_QUIT) failed: %s", SDL_GetError());
    }
}

extern "C" void rf_android_log_map_failure(const char *mapname, int line) {
    __android_log_print(
            ANDROID_LOG_ERROR,
            "RoadFighterTV",
            "load_map rejected map='%s' at upstream loadmg2.cpp:%d",
            mapname ? mapname : "(null)",
            line);
}

// ---- SDL 1.2 keyboard compatibility --------------------------------------
// Road Fighter's configuration stores SDL 1.2 keycodes (e.g. LEFT=276,
// RIGHT=275, LSHIFT=304). SDL2 keyboard state is indexed by scancode instead.
// Rebuild the small legacy keycode-indexed table the original game expects.
static int legacyKeyForScancode(SDL_Scancode sc) {
    switch (sc) {
        case SDL_SCANCODE_KP_0: return 256;
        case SDL_SCANCODE_KP_1: return 257;
        case SDL_SCANCODE_KP_2: return 258;
        case SDL_SCANCODE_KP_3: return 259;
        case SDL_SCANCODE_KP_4: return 260;
        case SDL_SCANCODE_KP_5: return 261;
        case SDL_SCANCODE_KP_6: return 262;
        case SDL_SCANCODE_KP_7: return 263;
        case SDL_SCANCODE_KP_8: return 264;
        case SDL_SCANCODE_KP_9: return 265;
        case SDL_SCANCODE_KP_PERIOD: return 266;
        case SDL_SCANCODE_KP_DIVIDE: return 267;
        case SDL_SCANCODE_KP_MULTIPLY: return 268;
        case SDL_SCANCODE_KP_MINUS: return 269;
        case SDL_SCANCODE_KP_PLUS: return 270;
        case SDL_SCANCODE_KP_ENTER: return 271;
        case SDL_SCANCODE_KP_EQUALS: return 272;
        case SDL_SCANCODE_UP: return 273;
        case SDL_SCANCODE_DOWN: return 274;
        case SDL_SCANCODE_RIGHT: return 275;
        case SDL_SCANCODE_LEFT: return 276;
        case SDL_SCANCODE_INSERT: return 277;
        case SDL_SCANCODE_HOME: return 278;
        case SDL_SCANCODE_END: return 279;
        case SDL_SCANCODE_PAGEUP: return 280;
        case SDL_SCANCODE_PAGEDOWN: return 281;
        case SDL_SCANCODE_F1: return 282;
        case SDL_SCANCODE_F2: return 283;
        case SDL_SCANCODE_F3: return 284;
        case SDL_SCANCODE_F4: return 285;
        case SDL_SCANCODE_F5: return 286;
        case SDL_SCANCODE_F6: return 287;
        case SDL_SCANCODE_F7: return 288;
        case SDL_SCANCODE_F8: return 289;
        case SDL_SCANCODE_F9: return 290;
        case SDL_SCANCODE_F10: return 291;
        case SDL_SCANCODE_F11: return 292;
        case SDL_SCANCODE_F12: return 293;
        case SDL_SCANCODE_F13: return 294;
        case SDL_SCANCODE_F14: return 295;
        case SDL_SCANCODE_F15: return 296;
        case SDL_SCANCODE_NUMLOCKCLEAR: return 300;
        case SDL_SCANCODE_CAPSLOCK: return 301;
        case SDL_SCANCODE_SCROLLLOCK: return 302;
        case SDL_SCANCODE_RSHIFT: return 303;
        case SDL_SCANCODE_LSHIFT: return 304;
        case SDL_SCANCODE_RCTRL: return 305;
        case SDL_SCANCODE_LCTRL: return 306;
        case SDL_SCANCODE_RALT: return 307;
        case SDL_SCANCODE_LALT: return 308;
        case SDL_SCANCODE_RGUI: return 309;
        case SDL_SCANCODE_LGUI: return 310;
        case SDL_SCANCODE_MODE: return 313;
        case SDL_SCANCODE_HELP: return 315;
        case SDL_SCANCODE_PRINTSCREEN: return 316;
        case SDL_SCANCODE_SYSREQ: return 317;
        case SDL_SCANCODE_PAUSE: return 318;
        case SDL_SCANCODE_MENU: return 319;
        case SDL_SCANCODE_POWER: return 320;
        case SDL_SCANCODE_UNDO: return 322;
        default: break;
    }

    const SDL_Keycode key = SDL_GetKeyFromScancode(sc);
    if (key >= 0 && key < 128) return static_cast<int>(key);
    return -1;
}

extern "C" int rf_sdl12_key_index(SDL_Keycode key) {
    if (key >= 0 && key < 128) return static_cast<int>(key);
    return legacyKeyForScancode(SDL_GetScancodeFromKey(key));
}

extern "C" int rf_sdl12_binding_index(int key) {
    // Values read from the original RoadFighter.cfg are already SDL1 keycodes.
    if (key >= 0 && key < RF_SDL12_KEY_COUNT) return key;

    // If the upstream SDL2 port supplied a modern SDLK_* enum as a default,
    // normalize it back to the legacy index before touching the state table.
    return rf_sdl12_key_index(static_cast<SDL_Keycode>(key));
}

extern "C" const Uint8 *rf_sdl12_get_key_state(int *numkeys) {
    static Uint8 legacy[RF_SDL12_KEY_COUNT];
    std::memset(legacy, 0, sizeof(legacy));

    int realCount = 0;
    const Uint8 *realState = SDL_GetKeyboardState(&realCount);
    if (realState && realCount > 0) {
        const int maxScancode = std::min(realCount, static_cast<int>(SDL_NUM_SCANCODES));
        for (int sc = 0; sc < maxScancode; ++sc) {
            if (!realState[sc]) continue;
            const int legacyKey = legacyKeyForScancode(static_cast<SDL_Scancode>(sc));
            if (legacyKey >= 0 && legacyKey < RF_SDL12_KEY_COUNT) legacy[legacyKey] = 1;
        }
    }

    // Merge normalized Android controller state. This is important because
    // SDL_PushEvent() does not modify SDL2's internal keyboard-state array.
    for (int p = 0; p < kPlayers; ++p) {
        for (int c = 0; c < kControls; ++c) {
            if (!g_control[p][c].load(std::memory_order_relaxed)) continue;
            const SDL_Scancode sc = scancodeFor(p, c);
            const int legacyKey = legacyKeyForScancode(sc);
            if (legacyKey >= 0 && legacyKey < RF_SDL12_KEY_COUNT) legacy[legacyKey] = 1;

            // B is confirm as well as gas. Some intro/menu states use Return
            // while gameplay uses Space/Shift, so expose both while B is held.
            if (c == GAS) legacy[SDLK_RETURN] = 1;
        }
    }

    // Log only control transitions, not every frame. This makes ADB logs useful
    // for verifying whether Android input actually reaches the legacy key table.
    unsigned int controlMask = 0;
    for (int p = 0; p < kPlayers; ++p) {
        for (int c = 0; c < kControls; ++c) {
            if (g_control[p][c].load(std::memory_order_relaxed)) {
                controlMask |= 1u << (p * kControls + c);
            }
        }
    }
    static unsigned int lastControlMask = ~0u;
    if (controlMask != lastControlMask) {
        lastControlMask = controlMask;
        __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
                "legacy input mask=0x%x p1(LRUDG)=%d%d%d%d%d p2(LRG)=%d%d%d",
                controlMask,
                legacy[276] != 0, legacy[275] != 0, legacy[273] != 0,
                legacy[274] != 0, legacy[32] != 0,
                legacy['a'] != 0, legacy['d'] != 0, legacy[304] != 0);
    }

    if (numkeys) *numkeys = RF_SDL12_KEY_COUNT;
    return legacy;
}

// ---- 4:3 GPU presentation bridge ------------------------------------
// The original game is laid out at 512x384. Keep that logical surface and scale
// the completed frame into Android's actual fullscreen window in one operation.
extern "C" SDL_Window *__real_SDL_CreateWindow(
        const char *, int, int, int, int, Uint32);
extern "C" SDL_Surface *__real_SDL_GetWindowSurface(SDL_Window *);
extern "C" int __real_SDL_UpdateWindowSurface(SDL_Window *);
extern "C" int __real_SDL_UpdateWindowSurfaceRects(SDL_Window *, const SDL_Rect *, int);

static SDL_Surface *ensureLogicalSurface(SDL_Window *window) {
    if (!window) return nullptr;

    if (!g_logical_surface
            || g_logical_surface->w != kLogicalWidth
            || g_logical_surface->h != kLogicalHeight
            || g_logical_surface->format->format != SDL_PIXELFORMAT_RGB888) {
        if (g_logical_surface) {
            SDL_FreeSurface(g_logical_surface);
            g_logical_surface = nullptr;
        }
        // The original game requests a 32-bit screen and its old SGE helpers
        // sometimes access pixels directly. Keep the logical framebuffer
        // deterministically 32-bit; presentation is GPU accelerated below.
        g_logical_surface = SDL_CreateRGBSurfaceWithFormat(
                0, kLogicalWidth, kLogicalHeight, 32, SDL_PIXELFORMAT_RGB888);
        __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
                "logical framebuffer %dx%d RGB888(no alpha): %s",
                kLogicalWidth, kLogicalHeight, g_logical_surface ? "ok" : SDL_GetError());
    }
    return g_logical_surface;
}

static bool ensureGpuPresenter(SDL_Window *window) {
    if (!window) return false;
    if (g_renderer && g_frame_texture) return true;

    if (g_frame_texture) {
        SDL_DestroyTexture(g_frame_texture);
        g_frame_texture = nullptr;
    }
    if (g_renderer) {
        SDL_DestroyRenderer(g_renderer);
        g_renderer = nullptr;
    }

    // On Android, CPU-scaling a 512x384 frame to a 1080p/4K window every frame
    // is extremely expensive. Upload only the small logical framebuffer and let
    // the GLES-backed SDL renderer scale it to the TV output.
    const Uint32 attempts[] = {
        SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC,
        SDL_RENDERER_ACCELERATED,
        0u,
    };
    for (Uint32 flags : attempts) {
        g_renderer = SDL_CreateRenderer(window, -1, flags);
        if (g_renderer) break;
    }
    if (!g_renderer) {
        __android_log_print(ANDROID_LOG_ERROR, "RoadFighterTV",
                "SDL_CreateRenderer failed: %s", SDL_GetError());
        return false;
    }

    SDL_RendererInfo info{};
    if (SDL_GetRendererInfo(g_renderer, &info) == 0) {
        __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
                "renderer=%s flags=0x%x", info.name ? info.name : "unknown", info.flags);
    }

    if (SDL_RenderSetLogicalSize(g_renderer, kLogicalWidth, kLogicalHeight) != 0) {
        __android_log_print(ANDROID_LOG_WARN, "RoadFighterTV",
                "SDL_RenderSetLogicalSize failed: %s", SDL_GetError());
    }

    g_frame_texture = SDL_CreateTexture(
            g_renderer,
            SDL_PIXELFORMAT_RGB888,
            SDL_TEXTUREACCESS_STREAMING,
            kLogicalWidth,
            kLogicalHeight);
    if (!g_frame_texture) {
        __android_log_print(ANDROID_LOG_ERROR, "RoadFighterTV",
                "SDL_CreateTexture failed: %s", SDL_GetError());
        SDL_DestroyRenderer(g_renderer);
        g_renderer = nullptr;
        return false;
    }
    SDL_SetTextureBlendMode(g_frame_texture, SDL_BLENDMODE_NONE);
    return true;
}

extern "C" SDL_Window *__wrap_SDL_CreateWindow(
        const char *title, int x, int y, int w, int h, Uint32 flags) {
    // Android's native window is fullscreen regardless of the requested desktop size.
    g_game_window = __real_SDL_CreateWindow(title, x, y, w, h, flags);
    return g_game_window;
}

extern "C" SDL_Surface *__wrap_SDL_GetWindowSurface(SDL_Window *window) {
    if (!window || window != g_game_window) return __real_SDL_GetWindowSurface(window);
    SDL_Surface *logical = ensureLogicalSurface(window);
    return logical ? logical : __real_SDL_GetWindowSurface(window);
}

static int presentLogicalSurfaceCpuFallback(SDL_Window *window) {
    SDL_Surface *real = __real_SDL_GetWindowSurface(window);
    if (!real) return -1;

    SDL_FillRect(real, nullptr, SDL_MapRGB(real->format, 0, 0, 0));
    const double scaleX = static_cast<double>(real->w) / kLogicalWidth;
    const double scaleY = static_cast<double>(real->h) / kLogicalHeight;
    const double scale = std::min(scaleX, scaleY);
    SDL_Rect dst{};
    dst.w = std::max(1, static_cast<int>(kLogicalWidth * scale));
    dst.h = std::max(1, static_cast<int>(kLogicalHeight * scale));
    dst.x = (real->w - dst.w) / 2;
    dst.y = (real->h - dst.h) / 2;
    if (SDL_BlitScaled(g_logical_surface, nullptr, real, &dst) != 0) return -1;
    return __real_SDL_UpdateWindowSurface(window);
}

static int presentLogicalSurface(SDL_Window *window) {
    if (!window || window != g_game_window || !g_logical_surface) {
        return __real_SDL_UpdateWindowSurface(window);
    }

    if (!ensureGpuPresenter(window)) {
        return presentLogicalSurfaceCpuFallback(window);
    }

    if (SDL_UpdateTexture(
            g_frame_texture, nullptr, g_logical_surface->pixels, g_logical_surface->pitch) != 0) {
        __android_log_print(ANDROID_LOG_ERROR, "RoadFighterTV",
                "SDL_UpdateTexture failed: %s", SDL_GetError());
        return -1;
    }

    SDL_SetRenderDrawColor(g_renderer, 0, 0, 0, 255);
    if (SDL_RenderClear(g_renderer) != 0) return -1;
    SDL_Rect logicalDst{0, 0, kLogicalWidth, kLogicalHeight};
    if (SDL_RenderCopy(g_renderer, g_frame_texture, nullptr, &logicalDst) != 0) return -1;
    SDL_RenderPresent(g_renderer);
    return 0;
}

extern "C" int __wrap_SDL_UpdateWindowSurface(SDL_Window *window) {
    return presentLogicalSurface(window);
}

extern "C" int __wrap_SDL_UpdateWindowSurfaceRects(
        SDL_Window *window, const SDL_Rect *, int) {
    return presentLogicalSurface(window);
}

// ---- SDL 1.2 video compatibility -----------------------------------------
// main.cpp is still written around SDL 1.2's screen-surface API. Keep that
// interface narrow and map it onto the same SDL2 window + logical surface used
// by the Android presentation bridge above.
extern "C" char *SDL_VideoDriverName(char *namebuf, int maxlen) {
    if (!namebuf || maxlen <= 0) return nullptr;
    const char *driver = SDL_GetCurrentVideoDriver();
    if (!driver) return nullptr;
    SDL_strlcpy(namebuf, driver, static_cast<size_t>(maxlen));
    return namebuf;
}

extern "C" char *SDL_AudioDriverName(char *namebuf, int maxlen) {
    if (!namebuf || maxlen <= 0) return nullptr;
    const char *driver = SDL_GetCurrentAudioDriver();
    if (!driver) return nullptr;
    SDL_strlcpy(namebuf, driver, static_cast<size_t>(maxlen));
    return namebuf;
}

extern "C" void SDL_WM_SetCaption(const char *title, const char *) {
    g_window_title = (title && *title) ? title : "Road Fighter";
    if (g_game_window) SDL_SetWindowTitle(g_game_window, g_window_title.c_str());
}

extern "C" SDL_Surface *SDL_SetVideoMode(int width, int height, int bpp, Uint32 flags) {
    __android_log_print(ANDROID_LOG_INFO, "RoadFighterTV",
            "SDL_SetVideoMode request %dx%d bpp=%d flags=0x%x", width, height, bpp, flags);
    if (!g_game_window) {
        g_game_window = __real_SDL_CreateWindow(
                g_window_title.c_str(),
                SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                width > 0 ? width : kLogicalWidth,
                height > 0 ? height : kLogicalHeight,
                SDL_WINDOW_SHOWN);
        if (!g_game_window) return nullptr;
    }
    return ensureLogicalSurface(g_game_window);
}

extern "C" SDL_Surface *SDL_GetVideoSurface(void) {
    if (!g_game_window) return nullptr;
    return ensureLogicalSurface(g_game_window);
}

extern "C" int SDL_EnableUNICODE(int enable) {
    const int previous = g_unicode_enabled;
    if (enable >= 0) g_unicode_enabled = enable ? 1 : 0;
    return previous;
}

extern "C" int SDL_Flip(SDL_Surface *) {
    if (!g_game_window) return -1;
    return presentLogicalSurface(g_game_window);
}

extern "C" void SDL_UpdateRect(SDL_Surface *, Sint32, Sint32, Uint32, Uint32) {
    if (g_game_window) (void)presentLogicalSurface(g_game_window);
}

extern "C" void SDL_UpdateRects(SDL_Surface *, int, SDL_Rect *) {
    if (g_game_window) (void)presentLogicalSurface(g_game_window);
}

// ---- Audio bridge ----------------------------------------------------------
// Keep the old game's 44.1 kHz mixer format, but use a smaller Android buffer
// for responsive game SFX. The upstream game requests 2048 frames; older port
// builds forced 4096 frames, which adds about 93 ms of buffering at 44.1 kHz
// before Android/HDMI latency is even counted.
// ---- Windows-era asset path compatibility ---------------------------------
// The original 2003 .mg2 files use backslashes in image paths. Android/Linux
// does not treat '\\' as a directory separator, so normalize before SDL_image.
extern "C" SDL_Surface *__real_IMG_Load(const char *file);

extern "C" SDL_Surface *__wrap_IMG_Load(const char *file) {
    if (!file) {
        __android_log_print(ANDROID_LOG_ERROR, "RoadFighterTV", "IMG_Load called with null path");
        return nullptr;
    }

    // Keep this compatibility seam allocation-free. If the old map parser ever
    // hands us a corrupt/non-terminated path, do not let std::string allocate or
    // throw while the game is constructing a level.
    char normalized[1024];
    const size_t len = strnlen(file, sizeof(normalized));
    if (len >= sizeof(normalized)) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "RoadFighterTV",
                "IMG_Load rejected overlong/non-terminated path (>= %zu bytes)",
                sizeof(normalized));
        return nullptr;
    }
    for (size_t i = 0; i < len; ++i) {
        normalized[i] = file[i] == '\\' ? '/' : file[i];
    }
    normalized[len] = '\0';

    SDL_Surface *surface = __real_IMG_Load(normalized);
    if (!surface) {
        __android_log_print(
                ANDROID_LOG_ERROR,
                "RoadFighterTV",
                "IMG_Load failed path='%s' normalized='%s': %s",
                file,
                normalized,
                SDL_GetError());
    } else {
        const int bpp = surface->format ? surface->format->BitsPerPixel : 0;
        __android_log_print(
                ANDROID_LOG_DEBUG,
                "RoadFighterTV",
                "IMG_Load ok path='%s' size=%dx%d bpp=%d",
                normalized,
                surface->w,
                surface->h,
                bpp);
    }
    return surface;
}

extern "C" int __real_Mix_OpenAudio(int, Uint16, int, int);
extern "C" int __real_Mix_AllocateChannels(int);
extern "C" int __real_Mix_Volume(int, int);
extern "C" int __real_Mix_VolumeMusic(int);

static int scaleRequestedVolume(int volume) {
    if (volume < 0) return volume; // SDL_mixer uses -1 as a query.
    volume = std::min(MIX_MAX_VOLUME, std::max(0, volume));
    return (volume * 30 + 50) / 100;
}

extern "C" int __wrap_Mix_OpenAudio(
        int frequency, Uint16 format, int channels, int requestedChunkFrames) {
    // Android's low-latency path is device-specific: the stream should match the
    // platform's native/optimal sample rate and HAL frames-per-buffer. Road Fighter
    // asks for the old desktop-friendly 44.1 kHz / 2048-frame setup, which can force
    // Android to resample and use a deeper path (especially on 48 kHz TV/HDMI output).
    const int preferredRate = g_androidPreferredSampleRate.load(std::memory_order_relaxed);
    const int preferredFrames = g_androidPreferredFramesPerBuffer.load(std::memory_order_relaxed);
    const int effectiveFrequency = preferredRate > 0 ? preferredRate : frequency;
    const int fallbackFrames = requestedChunkFrames > 0
            ? std::min(requestedChunkFrames, kFallbackAndroidAudioChunkFrames)
            : kFallbackAndroidAudioChunkFrames;
    const int effectiveChunkFrames = preferredFrames > 0 ? preferredFrames : fallbackFrames;

    const int result = __real_Mix_OpenAudio(
            effectiveFrequency, format, channels, effectiveChunkFrames);

    int actualFrequency = 0;
    Uint16 actualFormat = 0;
    int actualChannels = 0;
    if (result == 0) {
        Mix_QuerySpec(&actualFrequency, &actualFormat, &actualChannels);
    }
    const int chunkMs = effectiveFrequency > 0
            ? (effectiveChunkFrames * 1000 + effectiveFrequency / 2) / effectiveFrequency
            : -1;
    const char *driver = SDL_GetCurrentAudioDriver();
    __android_log_print(result == 0 ? ANDROID_LOG_INFO : ANDROID_LOG_ERROR, "RoadFighterTV",
            "Mix_OpenAudio requested=%dHz/%dfr native=%dHz/%dfr effective=%dHz/%dfr (~%dms) actual=%dHz/%dch driver=%s lowLatencyFeature=%s result=%d error=%s",
            frequency, requestedChunkFrames, preferredRate, preferredFrames,
            effectiveFrequency, effectiveChunkFrames, chunkMs,
            actualFrequency, actualChannels, driver ? driver : "(none)",
            g_androidClaimsLowLatency.load(std::memory_order_relaxed) ? "true" : "false",
            result, result == 0 ? "none" : Mix_GetError());
    if (result == 0) {
        __real_Mix_Volume(-1, kDefaultVolume);
        __real_Mix_VolumeMusic(kDefaultVolume);
    }
    return result;
}

extern "C" int __wrap_Mix_AllocateChannels(int channels) {
    const int result = __real_Mix_AllocateChannels(channels);
    if (result >= 0) __real_Mix_Volume(-1, kDefaultVolume);
    return result;
}

extern "C" int __wrap_Mix_Volume(int channel, int volume) {
    return __real_Mix_Volume(channel, scaleRequestedVolume(volume));
}

extern "C" int __wrap_Mix_VolumeMusic(int volume) {
    return __real_Mix_VolumeMusic(scaleRequestedVolume(volume));
}
