# Source and reproducibility

This repository keeps only the Android port code and build scripts. Third-party source trees and duplicated Road Fighter runtime data are fetched during the build.

`tools/fetch-native-deps.sh` verifies these pinned revisions:

- SDL2 `release-2.32.10` / `5d24957`
- SDL2_image `release-2.8.12` / `12cb2e4`
- SDL2_mixer `release-2.8.2` / `b208916`
- SDL2_ttf `release-2.24.0` / `2a89147`
- Road Fighter Remake `ecfa9dd2`

Upstream Road Fighter source:

- https://gitlab.com/coringao/roadfighter
- https://github.com/coringao/roadfighter

The build copies `maps/`, `graphics/`, and `sound/` from that verified Road Fighter checkout into the generated Android asset tree.

`tools/prepare_upstream.py` applies the SDL2/Android compatibility transforms. `tools/prepare_sdl_audio.py` applies the tested AAudio GAME / LOW_LATENCY / MMAP full-write changes to the pinned SDL2 source. Both transformations have offline regression fixtures.

The build uses NDK r30. NDK r28 and newer produce 16 KB-aligned native binaries by default; CI still inspects every ARM64 shared library and checks the release APK with `zipalign -P 16`.

The runtime font is not committed. The build downloads the official DejaVu 2.37 archive, verifies SHA-256 `fa9ca4d13871dd122f61258a80d01751d603b4d3ee14095d65453b4e846e17d7`, and copies `DejaVuSans-Bold.ttf` into generated assets. Its license text is kept in `LICENSES/DejaVu-font-license.txt`.

Reproduce the CI build with the commands in `README.md`.
