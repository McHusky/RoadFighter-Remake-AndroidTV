# Licensing and distribution notes

This file is a transparency note, not legal advice.

## Code licensing

The maintained Road Fighter Remake repository states that the project as a whole is distributed under GNU GPL version 2 or later. The Android TV adaptation in this repository is distributed under the same `GPL-2.0-or-later` terms.

SDL2, SDL2_image, SDL2_mixer and SDL2_ttf retain their respective upstream licenses. See `THIRD_PARTY.md`.

The runtime uses DejaVu Sans Bold under its upstream font license. The source repository does not contain the font binary; the build downloads the official DejaVu 2.37 archive and verifies its published SHA-256 before packaging. The full license text is in `LICENSES/DejaVu-font-license.txt`.

## Why the original bundled fonts are not in this repository

Earlier development snapshots contained `comicbd.ttf` (Microsoft Comic Sans MS Bold) and `tanglewo.ttf` (Nick Curtis / Tanglewood Tales). Their embedded copyright notices did not provide a repository redistribution license. They are therefore intentionally excluded from this public repository. The port uses the verified DejaVu Sans Bold build dependency instead, matching the maintained GNU/Linux upstream's font family more closely.

## Road Fighter / Konami

The upstream remake describes itself as an unofficial, not-for-profit remake of Konami's Road Fighter. That disclaimer is preserved in spirit here, but a disclaimer and a GPL license for the remake do not automatically grant rights in Konami trademarks, logos, characters, audiovisual material or other underlying intellectual property.

Before distributing the compiled game through an app store, the publisher should independently verify that they have all permissions required for the app binary, store title, screenshots, icon/banner and description. Google Play may request proof of authorization for third-party intellectual property.

Publishing the app for free does not remove copyright or trademark requirements.
