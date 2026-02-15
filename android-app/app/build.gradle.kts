plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("kotlin-kapt")
    id("dagger.hilt.android.plugin")
    id("kotlin-parcelize")
}

android {
    namespace = "com.pemf.vet"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pemf.vet"
        minSdk = 29
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
        
        // MQTT credentials from gradle.properties (secure - not hardcoded)
        val mqttBrokerUrl = project.findProperty("MQTT_BROKER_URL") as? String ?: ""
        val mqttBrokerUser = project.findProperty("MQTT_BROKER_USER") as? String ?: ""
        val mqttBrokerPass = project.findProperty("MQTT_BROKER_PASS") as? String ?: ""
        val mqttCertPins = project.findProperty("MQTT_CERT_PINS") as? String ?: ""
        
        buildConfigField("String", "MQTT_BROKER_URL", "\"$mqttBrokerUrl\"")
        buildConfigField("String", "MQTT_BROKER_USER", "\"$mqttBrokerUser\"")
        buildConfigField("String", "MQTT_BROKER_PASS", "\"$mqttBrokerPass\"")
        buildConfigField("String", "MQTT_CERT_PINS", "\"$mqttCertPins\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        compose = false
        viewBinding = true
        dataBinding = false
        buildConfig = true
    }

    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {
    // Core Android
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.activity:activity-ktx:1.8.2")
    implementation("androidx.work:work-runtime-ktx:2.9.0")

    // ViewModel & LiveData
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0")
    implementation("androidx.lifecycle:lifecycle-livedata-ktx:2.7.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    // Process lifecycle for app foreground/background detection
    implementation("androidx.lifecycle:lifecycle-process:2.7.0")

    // Navigation
    implementation("androidx.navigation:navigation-fragment-ktx:2.7.6")
    implementation("androidx.navigation:navigation-ui-ktx:2.7.6")
    
    // ViewPager2
    implementation("androidx.viewpager2:viewpager2:1.0.0")

    // Nordic BLE Scanner
    implementation("no.nordicsemi.android.support.v18:scanner:1.6.0")

    // Hilt Dependency Injection
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-android-compiler:2.48")
    kapt("androidx.hilt:hilt-compiler:1.1.0")
    implementation("androidx.hilt:hilt-work:1.1.0")

    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

    // MQTT (HiveMQ Cloud için)
    // Using standard MqttClient instead of MqttAndroidClient to avoid AlarmPingSender Android 13+ issues
    implementation("org.eclipse.paho:org.eclipse.paho.client.mqttv3:1.2.5")

    // BLE (Nordic Semiconductor - Industry Standard)
    implementation("no.nordicsemi.android:ble:2.7.4")
    implementation("no.nordicsemi.android:ble-ktx:2.7.4")

    // Coroutines (Flow API zaten kotlinx-coroutines-core içinde)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

    // Room Database
    implementation("androidx.room:room-runtime:2.6.1")
    implementation("androidx.room:room-ktx:2.6.1")
    kapt("androidx.room:room-compiler:2.6.1")

    // DataStore (replaces SharedPreferences)
    implementation("androidx.datastore:datastore-preferences:1.0.0")

    // Charts
    implementation("com.github.PhilJay:MPAndroidChart:v3.1.0")

    // JSON
    implementation("com.google.code.gson:gson:2.10.1")

    // Testing
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.7.3")
    testImplementation("io.mockk:mockk:1.13.8")
}

