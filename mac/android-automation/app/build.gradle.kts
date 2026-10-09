plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.stanley.y700automation"
    compileSdk = 36

    // Gradle generates AndroidTest for one build type only. Explicit opt-in
    // selects the isolated probe variant; ordinary debug builds stay unchanged.
    if (providers.gradleProperty("rev37Probe").orNull == "true") {
        testBuildType = "dg3Probe"
    }

    defaultConfig {
        applicationId = "com.stanley.y700automation"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.5.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["clearPackageData"] = "false"

        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
        }
        create("dg3Probe") {
            initWith(getByName("debug"))
            applicationIdSuffix = ".dg3probe"
            versionNameSuffix = "-dg3probe"
            matchingFallbacks += listOf("debug")
            isMinifyEnabled = false
        }
        release {
            isMinifyEnabled = false
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
    }

    sourceSets.getByName("dg3Probe") {
        java.srcDir("src/debug/java")
    }

    testOptions {
        animationsDisabled = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_1_8)
    }
}

// Probe APK needs the same debug-only vision libraries, without promoting
// OpenCV/MLKit into production release dependencies.
configurations.named("dg3ProbeImplementation") {
    extendsFrom(configurations.getByName("debugImplementation"))
}

dependencies {
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.uiautomator:uiautomator:2.4.0")
    debugImplementation("org.opencv:opencv:4.12.0")
    debugImplementation("com.google.mlkit:text-recognition:16.0.1")
    debugImplementation("com.google.mlkit:text-recognition-chinese:16.0.1")
    debugImplementation("com.microsoft.onnxruntime:onnxruntime-android:1.21.1")
    debugImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
}
