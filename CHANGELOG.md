# Changelog

## 1.0.0

- First public stable release of the Android TV port.
- Keep the hardware-tested v0.3.2 gameplay, controller, rendering, and AAudio implementation unchanged.
- Add `arm64-v8a` while retaining `armeabi-v7a`.
- Move to compile/target SDK 36, AGP 9.4.0, Gradle 9.6.0, Java 17, and Android NDK r30.
- Use modern native-library packaging and validate 16 KB ARM64 compatibility in CI.
- Build an Android App Bundle in addition to the debug APK.
- Use a SHA-256-verified DejaVu Sans Bold build-time font dependency instead of the unlicensed development-snapshot fonts.
- Keep the public repository to one build workflow with no Dependabot or Play Store automation.
- Publish a signed installable APK automatically to GitHub Releases when a `v*` tag is pushed; the private signing key remains in GitHub Actions secrets.

## 0.3.2

- Fix choppy/broken AAudio output on Google TV Streamer by replacing SDL 2.32.10's short single-shot write with a full-block writer.
- Keep the working `AAUDIO_USAGE_GAME`, `LOW_LATENCY`, and `EXCLUSIVE`/MMAP-oriented configuration.
- Tune the AAudio output buffer to two hardware bursts and log XRuns/write failures.
- This is the hardware-tested runtime baseline for the current repository.

### CI lint cleanup

- Keep Android lint enabled for the app while excluding the verbatim SDL Android Java glue copied from the pinned SDL release.
- Removed the deprecated `android.useAndroidX=false` project option.
- Removed a redundant deprecated Java `srcDir` declaration; `src/main/java` is already the Android default source directory.
