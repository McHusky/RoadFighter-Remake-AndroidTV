#pragma once

#include <SDL.h>

// Small, source-compatible SDL 1.2 surface helpers for the pieces still used by
// the original Road Fighter/SGE code. These are intentionally narrow: input,
// windowing and audio are handled elsewhere by native SDL2 code.

// SDL 1.2 SDL_DisplayFormat() converted a surface to the current display
// format. SDL2's software blitter already handles conversion, so a same-format
// copy preserves the old ownership/lifetime semantics without depending on a
// global video surface.
static inline SDL_Surface *rf_sdl_convert_preserve(SDL_Surface *surface, Uint32 format) {
    if (!surface || !surface->format) return nullptr;

    Uint32 oldColorKey = 0;
    const bool hadColorKey = (SDL_GetColorKey(surface, &oldColorKey) == 0);
    Uint8 keyR = 0, keyG = 0, keyB = 0;
    if (hadColorKey) SDL_GetRGB(oldColorKey, surface->format, &keyR, &keyG, &keyB);

    Uint8 alphaMod = 255;
    SDL_BlendMode blendMode = SDL_BLENDMODE_NONE;
    (void)SDL_GetSurfaceAlphaMod(surface, &alphaMod);
    (void)SDL_GetSurfaceBlendMode(surface, &blendMode);

    SDL_Surface *out = SDL_ConvertSurfaceFormat(surface, format, 0);
    if (!out) return nullptr;

    if (hadColorKey) {
        const Uint32 newColorKey = SDL_MapRGB(out->format, keyR, keyG, keyB);
        (void)SDL_SetColorKey(out, SDL_TRUE, newColorKey);
    }
    (void)SDL_SetSurfaceAlphaMod(out, alphaMod);
    (void)SDL_SetSurfaceBlendMode(out, blendMode);
    return out;
}

static inline SDL_Surface *rf_sdl_display_format(SDL_Surface *surface) {
    // SDL 1.2's ordinary 32-bit video surface has no destination alpha.
    // RGB888 uses 32 bits of storage but Amask==0, matching the legacy
    // assumptions in Road Fighter/SGE.
    return rf_sdl_convert_preserve(surface, SDL_PIXELFORMAT_RGB888);
}

// SDL_DisplayFormatAlpha() is the explicit alpha-preserving path.
static inline SDL_Surface *rf_sdl_display_format_alpha(SDL_Surface *surface) {
    return rf_sdl_convert_preserve(surface, SDL_PIXELFORMAT_ARGB8888);
}


// A few SDL 1.2 surface flag names still occur in the bundled SGE-era code.
// SDL2 surfaces are software surfaces, so the old HW/SW allocation hints are
// no-ops. SDL_SetColorKey treats its flag as a boolean, so 1 preserves the old
// SDL_SRCCOLORKEY intent if it appears in code that did not need rewriting.
#ifndef SDL_HWSURFACE
#define SDL_HWSURFACE 0u
#endif
#ifndef SDL_SWSURFACE
#define SDL_SWSURFACE 0u
#endif
#ifndef SDL_SRCCOLORKEY
#define SDL_SRCCOLORKEY 1u
#endif

// SDL_SetAlpha() disappeared in SDL2. In this game it is used to toggle source
// alpha blending (the observed calls use SDL_ALPHA_OPAQUE). Map the old switch
// to SDL2's surface blend mode and alpha modulation.
#ifndef SDL_SRCALPHA
#define SDL_SRCALPHA 0x00010000u
#endif

static inline int rf_sdl_set_alpha(SDL_Surface *surface, Uint32 flags, Uint8 alpha) {
    if (!surface) return -1;
    if (SDL_SetSurfaceAlphaMod(surface, alpha) != 0) return -1;
    return SDL_SetSurfaceBlendMode(
        surface,
        (flags & SDL_SRCALPHA) ? SDL_BLENDMODE_BLEND : SDL_BLENDMODE_NONE
    );
}


// SDL 1.2 exposed a keycode-indexed keyboard-state table with SDLK_LAST=323.
// Road Fighter stores those old numeric keycodes in its configuration, so using
// SDL2's scancode-indexed SDL_GetKeyboardState() directly breaks steering.
#ifndef RF_SDL12_KEY_COUNT
#define RF_SDL12_KEY_COUNT 323
#endif

#ifdef __cplusplus
extern "C" {
#endif
int rf_sdl12_key_index(SDL_Keycode key);
int rf_sdl12_binding_index(int key);
const Uint8 *rf_sdl12_get_key_state(int *numkeys);
void rf_android_log_map_failure(const char *mapname, int line);
#ifdef __cplusplus
}
#endif

// ---------------------------------------------------------------------------
// Narrow SDL 1.2 video/window compatibility used by the original main.cpp.
// The implementation lives in platform_bridge.cpp and presents the game's
// original 512x384 software surface through the existing Android fullscreen
// scaling path.

// SDL 1.2's modifier typedef was renamed in SDL2.
typedef SDL_Keymod SDLMod;
typedef SDL_Keysym SDL_keysym;

// Legacy SDL 1.2 video flags. They are accepted by SDL_SetVideoMode below;
// Android's native window is fullscreen regardless of these desktop hints.
#ifndef SDL_ANYFORMAT
#define SDL_ANYFORMAT 0x10000000u
#endif
#ifndef SDL_HWPALETTE
#define SDL_HWPALETTE 0x20000000u
#endif
#ifndef SDL_DOUBLEBUF
#define SDL_DOUBLEBUF 0x40000000u
#endif
#ifndef SDL_FULLSCREEN
#define SDL_FULLSCREEN 0x80000000u
#endif
#ifndef SDL_ASYNCBLIT
#define SDL_ASYNCBLIT 0x00000004u
#endif
#ifndef SDL_RESIZABLE
#define SDL_RESIZABLE 0x00000010u
#endif
#ifndef SDL_NOFRAME
#define SDL_NOFRAME 0x00000020u
#endif

#ifdef __cplusplus
extern "C" {
#endif

char *SDL_VideoDriverName(char *namebuf, int maxlen);
char *SDL_AudioDriverName(char *namebuf, int maxlen);
void SDL_WM_SetCaption(const char *title, const char *icon);
SDL_Surface *SDL_SetVideoMode(int width, int height, int bpp, Uint32 flags);
SDL_Surface *SDL_GetVideoSurface(void);
int SDL_EnableUNICODE(int enable);
int SDL_Flip(SDL_Surface *screen);
void SDL_UpdateRect(SDL_Surface *screen, Sint32 x, Sint32 y, Uint32 w, Uint32 h);
void SDL_UpdateRects(SDL_Surface *screen, int numrects, SDL_Rect *rects);

#ifdef __cplusplus
}
#endif
