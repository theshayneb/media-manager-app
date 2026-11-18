plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// The version comes from android/version.txt (the release workflow publishes android-<version>).
val appVersion = rootProject.file("version.txt").readText().trim()

android {
    namespace = "mm.companion"
    compileSdk = 35

    defaultConfig {
        applicationId = "mm.companion"
        minSdk = 30            // Android 11: the Trash and "all files" access this app uses
        targetSdk = 35
        versionName = appVersion
        versionCode = appVersion.split(".").let { (it[0].toInt() * 10000) + (it[1].toInt() * 100) + it[2].toInt() }
        // The Microsoft app ID for OneDrive sign-in (can also be typed in the app's Settings).
        buildConfigField("String", "ONEDRIVE_CLIENT_ID", "\"${System.getenv("ONEDRIVE_CLIENT_ID") ?: ""}\"")
    }

    signingConfigs {
        create("release") {
            // The same key every time, so a new version installs over the old one.
            val keystore = System.getenv("ANDROID_KEYSTORE_FILE")
            if (keystore != null && file(keystore).exists()) {
                storeFile = file(keystore)
                storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("ANDROID_KEY_ALIAS") ?: "companion"
                keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")
            } else {
                initWith(getByName("debug"))
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("release")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation(project(":core"))
    implementation(platform("androidx.compose:compose-bom:2024.10.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.exifinterface:exifinterface:1.3.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
