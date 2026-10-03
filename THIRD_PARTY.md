# Third-party components

The build fetches these projects from their upstream repositories and verifies the expected pinned revision:

| Component | Version / commit | License |
| --- | --- | --- |
| SDL2 | `release-2.32.10` / `5d24957` | zlib |
| SDL2_image | `release-2.8.12` / `12cb2e4` | zlib |
| SDL2_mixer | `release-2.8.2` / `b208916` | zlib |
| SDL2_ttf | `release-2.24.0` / `2a89147` | zlib |
| Road Fighter Remake | `ecfa9dd2` | GPL-2.0-or-later aggregate project, as stated by upstream |

Upstream URLs:

- https://github.com/libsdl-org/SDL
- https://github.com/libsdl-org/SDL_image
- https://github.com/libsdl-org/SDL_mixer
- https://github.com/libsdl-org/SDL_ttf
- https://gitlab.com/coringao/roadfighter
- https://github.com/dejavu-fonts/dejavu-fonts

Vendored codec dependencies pulled by SDL satellite repositories retain their own upstream licenses and license files in the fetched source trees.

## DejaVu Sans Bold

`DejaVuSans-Bold.ttf` is fetched at build time from the official DejaVu 2.37 binary archive and SHA-256 verified before packaging. The font binary is intentionally not committed to this source repository. Its redistribution license is tracked in `LICENSES/DejaVu-font-license.txt`.

## Local modifications

SDL2's AAudio backend is transformed at build time by `tools/prepare_sdl_audio.py`. The modification remains under SDL2's zlib license.

The Road Fighter source is transformed at build time by `tools/prepare_upstream.py` under the upstream project's GPL-2.0-or-later terms.
