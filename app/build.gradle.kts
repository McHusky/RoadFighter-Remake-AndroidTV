plugins {
    id("com.android.application")
}

android {
    namespace = "io.github.roadfighter.tv"
    compileSdk = 36
    ndkVersion = "30.0.16248370"

    defaultConfig {
        applicationId = "io.github.roadfighter.tv"
        minSdk = 28
        targetSdk = 36
        versionCode = 23
        versionName = "1.0.0"

        ndk {
            abiFilters += listOf("armeabi-v7a", "arm64-v8a")
        }

        externalNativeBuild {
            cmake {
                cppFlags += listOf("-std=c++14", "-Wno-deprecated-declarations", "-Wno-writable-strings")
                arguments += listOf("-DANDROID_STL=c++_shared")
            }
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
            ndk {
                debugSymbolLevel = "FULL"
            }
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }


    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        // SDLActivity and its Android HID helpers are copied verbatim from the
        // pinned SDL release during dependency setup. Lint our own app code and
        // resources, but do not turn upstream SDL implementation details into
        // project-local release blockers.
        lintConfig = file("lint.xml")
    }

    // AGP 8.5.1+ aligns uncompressed native libraries for 16 KB page-size
    // devices. Keep modern packaging enabled for Play-generated split APKs.
    packaging {
        jniLibs {
            useLegacyPackaging = false
        }
    }
}
