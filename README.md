# Road Fighter Remake for Android TV

A small Android TV port of the open-source Road Fighter Remake, focused on Google TV / Android TV and physical game controllers.

The repository is intentionally simple: one Android app module, one GitHub Actions workflow, pinned native dependencies, and no dependency bot or Play Store automation.

## Status

**Current version: 1.0.0**

This is the first public stable release. The gameplay, controller, rendering, and audio core is the hardware-tested v0.3.2 implementation. Version 1.0.0 keeps that runtime behavior and moves the surrounding Android build to a current baseline.

Tested hardware includes a Google TV Streamer and 8BitDo Micro controllers. The Android audio path uses SDL2 AAudio with GAME / LOW_LATENCY / MMAP-oriented configuration and a full-block writer. On the tested Google TV Streamer this fixed the HDMI audio delay while keeping audio clean with the device audio setting on **Automatic**.

## Android baseline

As of 2026-10-03:

- compileSdk 36
- targetSdk 36
- minSdk 28
- Android Gradle Plugin 9.4.0
- Gradle 9.6.0
- Java 17
- Android NDK r30 (`30.0.16248370`)
- CMake 3.22.1
- `armeabi-v7a` and `arm64-v8a`
- modern native-library packaging
- Android App Bundle output
- 16 KB page-size validation for ARM64 native libraries

The app itself is offline and contains no analytics, ads, accounts, telemetry, or Internet permission.

## GitHub Releases

A normal push or pull request builds and checks the project. A pushed version tag such as `v1.0.0` additionally creates a **GitHub Release with a signed, directly installable APK** and `SHA256SUMS.txt`.

The signing key is deliberately not stored in this public repository. Set up these four repository secrets once before pushing the first release tag:

- `APK_KEYSTORE_BASE64`
- `APK_KEYSTORE_PASSWORD`
- `APK_KEY_ALIAS`
- `APK_KEY_PASSWORD`

GitHub stores repository secrets separately from the source tree and exposes them only to workflows that reference them.

### One-time signing setup

Create and permanently back up one release keystore. Keep this file private; the same key should be used for all future releases so installed APKs can be updated in place.

```bash
keytool -genkeypair -v \
  -keystore roadfighter-release.jks \
  -alias roadfighter \
  -keyalg RSA \
  -keysize 4096 \
  -validity 10000
```

Encode the keystore as a single-line Base64 value and save that value as `APK_KEYSTORE_BASE64` in **GitHub → Repository → Settings → Secrets and variables → Actions**. Add the keystore password, alias, and key password as the other three secrets.

On Linux:

```bash
base64 -w 0 roadfighter-release.jks
```

On macOS:

```bash
base64 < roadfighter-release.jks | tr -d '\n'
```

Do not commit the `.jks` file. The repository `.gitignore` already excludes keystores.

### Publish a release

After the secrets are configured:

```bash
git tag -a v1.0.0 -m "Road Fighter Remake Android TV v1.0.0"
git push origin v1.0.0
```

GitHub Actions then builds both ARM ABIs, runs lint and the 16 KB checks, aligns and signs the release APK, verifies the APK signature, and publishes it under the repository's **Releases** page.

Future releases work the same way: update `versionName`/`versionCode`, commit, then push the matching `vX.Y.Z` tag.

## Build locally

Prerequisites:

- Git
- Python 3
- JDK 17
- Android SDK platform 36
- Android Build Tools 36.0.0
- Android NDK r30 (`30.0.16248370`)
- CMake 3.22.1
- Gradle 9.6.0

Prepare the pinned native sources and game data:

```bash
python3 ./tools/test_prepare_sdl_audio_fixture.py
bash ./tools/fetch-native-deps.sh
python3 ./tools/test_prepare_upstream_compat.py
python3 ./tools/normalize_map_paths.py
python3 ./tools/prepare_upstream.py
```

Build an installable debug APK:

```bash
gradle --no-daemon :app:assembleDebug
```

Build the unsigned release APK and AAB and run lint:

```bash
gradle --no-daemon :app:assembleRelease :app:bundleRelease :app:lintRelease
```

The source repository intentionally contains no private signing material.

## Continuous integration

`.github/workflows/ci.yml`:

1. installs the pinned Android toolchain,
2. fetches and verifies the pinned native dependencies,
3. runs the SDL/Road Fighter compatibility tests,
4. builds debug APK, release APK, and AAB,
5. runs Android lint,
6. verifies both ARM ABIs and 16 KB native compatibility,
7. stores the build outputs as an Actions artifact,
8. on `v*` tags only, signs the release APK and publishes it on GitHub Releases.

Android lint remains enabled for project-owned code and resources. The verbatim SDL Android Java glue under `org/libsdl` is excluded from project lint because it contains optional upstream HID/Bluetooth paths that are not part of this port's app-specific implementation.

## Native source model

Third-party source trees are not committed. `tools/fetch-native-deps.sh` fetches and verifies the pinned revisions for:

- SDL2 2.32.10
- SDL2_image 2.8.12
- SDL2_mixer 2.8.2
- SDL2_ttf 2.24.0
- Road Fighter Remake commit `ecfa9dd2`

The maps, graphics, and sounds are copied from that exact verified Road Fighter checkout during the build so code and runtime data stay matched.

A redistributable DejaVu Sans Bold font is fetched from the official DejaVu 2.37 archive, SHA-256 checked, and packaged at build time. The font binary is intentionally not stored in this repository.

See `SOURCE.md` and `THIRD_PARTY.md` for exact pins and license notes.

## Controls

The port is designed around standard Android game-controller input. The Google TV remote is not assigned as a player controller.

The tested 8BitDo Micro setup uses the D-pad plus the normal action/start buttons exposed by Android. The controller's Star button is not relied on because Android TV firmware does not consistently expose it to applications.

## Privacy

The app is offline. The manifest does not request Internet access, and the port contains no telemetry, analytics, account system, ads, or network service.

## License and trademarks

The Android TV adaptation follows the upstream Road Fighter Remake GPL-2.0-or-later licensing model. SDL components keep their upstream zlib licenses. See `LICENSE`, `LEGAL.md`, and `THIRD_PARTY.md`.

Road Fighter and related Konami names and assets remain the property of their respective rights holders. This repository is an unofficial open-source port and is not affiliated with or endorsed by Konami.
