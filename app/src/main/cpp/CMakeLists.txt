cmake_minimum_required(VERSION 3.22.1)
project(RoadFighterTV LANGUAGES C CXX)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)

set(VENDOR_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor")
set(RF_DIR "${VENDOR_DIR}/roadfighter")

foreach(required SDL SDL_image SDL_mixer SDL_ttf roadfighter)
    if(NOT EXISTS "${VENDOR_DIR}/${required}")
        message(FATAL_ERROR "Missing ${required}. Run tools/fetch-native-deps.sh before Gradle.")
    endif()
endforeach()

# SDL2 must be shared because SDLActivity loads libSDL2.so before libmain.so.
set(SDL_SHARED ON CACHE BOOL "" FORCE)
set(SDL_STATIC OFF CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
set(SDL_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${VENDOR_DIR}/SDL" "${CMAKE_BINARY_DIR}/sdl2")

# SDL_image: Road Fighter needs JPEG; BMP support lives in SDL itself.
set(BUILD_SHARED_LIBS ON CACHE BOOL "" FORCE)
set(SDL2IMAGE_VENDORED ON CACHE BOOL "" FORCE)
set(SDL2IMAGE_DEPS_SHARED OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_SAMPLES OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_TESTS OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_INSTALL OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_AVIF OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_JXL OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_PNG OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_TIF OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_WEBP OFF CACHE BOOL "" FORCE)
set(SDL2IMAGE_JPG ON CACHE BOOL "" FORCE)
add_subdirectory("${VENDOR_DIR}/SDL_image" "${CMAKE_BINARY_DIR}/sdl2_image")

# SDL_mixer: the original assets are OGG Vorbis + WAV.
set(SDL2MIXER_VENDORED ON CACHE BOOL "" FORCE)
set(SDL2MIXER_DEPS_SHARED OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_SAMPLES OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_TESTS OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_INSTALL OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_FLAC OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_GME OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_MOD OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_MP3 OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_MIDI OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_OPUS OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_WAVPACK OFF CACHE BOOL "" FORCE)
set(SDL2MIXER_VORBIS STB CACHE STRING "" FORCE)
add_subdirectory("${VENDOR_DIR}/SDL_mixer" "${CMAKE_BINARY_DIR}/sdl2_mixer")

# SDL_ttf with vendored FreeType; complex shaping is unnecessary for the game's UI.
set(SDL2TTF_VENDORED ON CACHE BOOL "" FORCE)
set(SDL2TTF_HARFBUZZ OFF CACHE BOOL "" FORCE)
set(SDL2TTF_SAMPLES OFF CACHE BOOL "" FORCE)
set(SDL2TTF_INSTALL OFF CACHE BOOL "" FORCE)
add_subdirectory("${VENDOR_DIR}/SDL_ttf" "${CMAKE_BINARY_DIR}/sdl2_ttf")

file(GLOB RF_SOURCES CONFIGURE_DEPENDS
    "${RF_DIR}/src/*.cpp"
    "${RF_DIR}/src/sge/*.cpp"
)

add_library(main SHARED
    android_entry.cpp
    platform_bridge.cpp
    ${RF_SOURCES}
)

target_include_directories(main PRIVATE
    "${RF_DIR}/src"
    "${RF_DIR}/src/sge"
)

target_compile_options(main PRIVATE
    -Wno-deprecated-declarations
    -Wno-writable-strings
    -Wno-unused-parameter
    -fno-omit-frame-pointer
    -fno-optimize-sibling-calls
    -include "${CMAKE_CURRENT_SOURCE_DIR}/rf_sdl12_compat.h"
)

# Accept either exported names used by SDL2 satellite libraries.
if(TARGET SDL2::SDL2)
    set(RF_SDL2 SDL2::SDL2)
elseif(TARGET SDL2-shared)
    set(RF_SDL2 SDL2-shared)
else()
    message(FATAL_ERROR "SDL2 CMake target not found")
endif()

if(TARGET SDL2_image::SDL2_image)
    set(RF_IMAGE SDL2_image::SDL2_image)
elseif(TARGET SDL2_image)
    set(RF_IMAGE SDL2_image)
elseif(TARGET SDL2_image-shared)
    set(RF_IMAGE SDL2_image-shared)
else()
    message(FATAL_ERROR "SDL2_image CMake target not found")
endif()

if(TARGET SDL2_mixer::SDL2_mixer)
    set(RF_MIXER SDL2_mixer::SDL2_mixer)
elseif(TARGET SDL2_mixer)
    set(RF_MIXER SDL2_mixer)
elseif(TARGET SDL2_mixer-shared)
    set(RF_MIXER SDL2_mixer-shared)
else()
    message(FATAL_ERROR "SDL2_mixer CMake target not found")
endif()

if(TARGET SDL2_ttf::SDL2_ttf)
    set(RF_TTF SDL2_ttf::SDL2_ttf)
elseif(TARGET SDL2_ttf)
    set(RF_TTF SDL2_ttf)
elseif(TARGET SDL2_ttf-shared)
    set(RF_TTF SDL2_ttf-shared)
else()
    message(FATAL_ERROR "SDL2_ttf CMake target not found")
endif()

target_link_libraries(main PRIVATE
    ${RF_SDL2}
    ${RF_IMAGE}
    ${RF_MIXER}
    ${RF_TTF}
    android
    log
    dl
)

# Redirect only the small compatibility seams; the original gameplay code stays untouched.
target_link_options(main PRIVATE
    "-Wl,--build-id"
    "-Wl,--wrap=IMG_Load"
    "-Wl,--wrap=SDL_CreateWindow"
    "-Wl,--wrap=SDL_GetWindowSurface"
    "-Wl,--wrap=SDL_UpdateWindowSurface"
    "-Wl,--wrap=SDL_UpdateWindowSurfaceRects"
    "-Wl,--wrap=Mix_OpenAudio"
    "-Wl,--wrap=Mix_AllocateChannels"
    "-Wl,--wrap=Mix_Volume"
    "-Wl,--wrap=Mix_VolumeMusic"
)
