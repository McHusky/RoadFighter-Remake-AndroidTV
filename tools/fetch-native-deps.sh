#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR="$ROOT/app/src/main/cpp/vendor"
SDL_JAVA="$ROOT/app/src/main/java/org/libsdl"
mkdir -p "$VENDOR"

clone_tag_verified() {
  local url="$1"
  local tag="$2"
  local expected_short="$3"
  local dest="$4"
  if [[ ! -d "$dest/.git" ]]; then
    rm -rf "$dest"
    git clone --depth 1 --branch "$tag" --recurse-submodules --shallow-submodules "$url" "$dest"
  fi
  local actual
  actual="$(git -C "$dest" rev-parse --short=7 HEAD)"
  if [[ "$actual" != "$expected_short" ]]; then
    echo "ERROR: unexpected $tag revision: $actual (expected $expected_short)" >&2
    exit 1
  fi
  echo "Verified $tag revision: $actual"
}

clone_branch_verified() {
  local url="$1"
  local branch="$2"
  local expected_short="$3"
  local dest="$4"
  if [[ ! -d "$dest/.git" ]]; then
    rm -rf "$dest"
    git clone --depth 1 --branch "$branch" "$url" "$dest"
  fi
  local actual
  actual="$(git -C "$dest" rev-parse --short=8 HEAD)"
  if [[ "$actual" != "$expected_short" ]]; then
    echo "ERROR: unexpected Road Fighter revision: $actual (expected $expected_short)" >&2
    echo "The upstream branch changed; update and review the pinned revision before building." >&2
    exit 1
  fi
  echo "Verified Road Fighter revision: $actual"
}

clone_tag_verified https://github.com/libsdl-org/SDL.git release-2.32.10 5d24957 "$VENDOR/SDL"
python3 "$ROOT/tools/prepare_sdl_audio.py" "$VENDOR/SDL"
clone_tag_verified https://github.com/libsdl-org/SDL_image.git release-2.8.12 12cb2e4 "$VENDOR/SDL_image"
clone_tag_verified https://github.com/libsdl-org/SDL_mixer.git release-2.8.2 b208916 "$VENDOR/SDL_mixer"
clone_tag_verified https://github.com/libsdl-org/SDL_ttf.git release-2.24.0 2a89147 "$VENDOR/SDL_ttf"
clone_branch_verified https://gitlab.com/coringao/roadfighter.git master ecfa9dd2 "$VENDOR/roadfighter"

# Fetch the redistributable runtime font from the official DejaVu 2.37
# binary release instead of storing font binaries in this source repository.
DEJAVU_URL="https://downloads.sourceforge.net/project/dejavu/dejavu/2.37/dejavu-fonts-ttf-2.37.tar.bz2"
DEJAVU_FALLBACK_URL="https://github.com/dejavu-fonts/dejavu-fonts/releases/download/version_2_37/dejavu-fonts-ttf-2.37.tar.bz2"
DEJAVU_SHA256="fa9ca4d13871dd122f61258a80d01751d603b4d3ee14095d65453b4e846e17d7"
DEJAVU_ARCHIVE="$VENDOR/dejavu-fonts-ttf-2.37.tar.bz2"
DEJAVU_TMP="$VENDOR/.dejavu-fonts-2.37"
RF_FONT_DIR="$ROOT/app/src/main/assets/roadfighter/fonts"

echo "Fetching verified DejaVu Sans Bold runtime font..."
if [[ ! -f "$DEJAVU_ARCHIVE" ]]; then
  if ! curl --fail --location --retry 3 --retry-delay 2 \
      --output "$DEJAVU_ARCHIVE" "$DEJAVU_URL"; then
    echo "Primary DejaVu mirror failed; trying the upstream GitHub release asset..." >&2
    rm -f "$DEJAVU_ARCHIVE"
    curl --fail --location --retry 3 --retry-delay 2 \
      --output "$DEJAVU_ARCHIVE" "$DEJAVU_FALLBACK_URL"
  fi
fi
if ! python3 - "$DEJAVU_ARCHIVE" "$DEJAVU_SHA256" <<'PY'
import hashlib
import pathlib
import sys
path = pathlib.Path(sys.argv[1])
expected = sys.argv[2].lower()
actual = hashlib.sha256(path.read_bytes()).hexdigest()
if actual != expected:
    print(f"checksum mismatch: {actual} != {expected}", file=sys.stderr)
    raise SystemExit(1)
PY
then
  echo "ERROR: DejaVu 2.37 archive checksum mismatch" >&2
  rm -f "$DEJAVU_ARCHIVE"
  exit 1
fi
rm -rf "$DEJAVU_TMP"
mkdir -p "$DEJAVU_TMP" "$RF_FONT_DIR"
tar -xjf "$DEJAVU_ARCHIVE" -C "$DEJAVU_TMP"
DEJAVU_FONT="$(find "$DEJAVU_TMP" -type f -name DejaVuSans-Bold.ttf -print -quit)"
if [[ -z "$DEJAVU_FONT" || ! -s "$DEJAVU_FONT" ]]; then
  echo "ERROR: DejaVuSans-Bold.ttf not found in verified DejaVu archive" >&2
  exit 1
fi
cp "$DEJAVU_FONT" "$RF_FONT_DIR/DejaVuSans-Bold.ttf"
rm -rf "$DEJAVU_TMP"
echo "Installed verified DejaVu Sans Bold 2.37 runtime font."

# Keep runtime data in lock-step with the exact Road Fighter source revision.
# The original 2003 Windows package uses an older .mg2 serialization dialect;
# mixing those maps with the 2019 Linux source can make load_map() reject a level
# even when all referenced images exist. Overlay maps/graphics/sound from the
# verified upstream checkout before packaging the APK. The verified DejaVu font
# fetched above and RoadFighter.cfg remain Android compatibility assets.
RF_ASSETS="$ROOT/app/src/main/assets/roadfighter"
for runtime_dir in maps graphics sound; do
  if [[ ! -d "$VENDOR/roadfighter/$runtime_dir" ]]; then
    echo "ERROR: pinned Road Fighter checkout is missing $runtime_dir" >&2
    exit 1
  fi
  rm -rf "$RF_ASSETS/$runtime_dir"
  cp -R "$VENDOR/roadfighter/$runtime_dir" "$RF_ASSETS/$runtime_dir"
done
echo "Synced pinned upstream maps/graphics/sound into Android assets."

# SDLActivity is part of SDL2's Android project. Keep the app source tree self-contained
# for the Gradle build after the dependency checkout.
rm -rf "$SDL_JAVA"
mkdir -p "$(dirname "$SDL_JAVA")"
cp -R "$VENDOR/SDL/android-project/app/src/main/java/org/libsdl" "$SDL_JAVA"

echo "Native dependencies and SDLActivity sources are ready."
