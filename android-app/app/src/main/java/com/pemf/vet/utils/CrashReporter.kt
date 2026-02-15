package com.pemf.vet.utils

import android.util.Log

/**
 * Crash reporting utility
 * Currently logs to system log, but can be extended to use Firebase Crashlytics, Sentry, etc.
 * 
 * To integrate Firebase Crashlytics:
 * 1. Add Firebase to your project: https://firebase.google.com/docs/android/setup
 * 2. Add dependency: implementation("com.google.firebase:firebase-crashlytics-ktx:18.6.1")
 * 3. Replace logError() and recordException() with Firebase Crashlytics calls
 */
object CrashReporter {
    private const val TAG = "CrashReporter"
    
    // Check if we're in debug mode using try-catch to handle BuildConfig not being available
    private val isDebug: Boolean
        get() = try {
            val buildConfigClass = Class.forName("com.pemf.vet.BuildConfig")
            val debugField = buildConfigClass.getField("DEBUG")
            debugField.getBoolean(null)
        } catch (e: Exception) {
            // If BuildConfig is not available, assume debug mode
            true
        }
    
    /**
     * Log a non-fatal error
     */
    fun logError(tag: String, message: String, throwable: Throwable? = null) {
        // In release builds, log to system log as fallback
        // TODO: Replace with Firebase Crashlytics or other crash reporting service
        if (!isDebug) {
            Log.e(TAG, "[$tag] $message", throwable)
            
            // Example Firebase Crashlytics integration (uncomment when Firebase is added):
            // FirebaseCrashlytics.getInstance().log("[$tag] $message")
            // if (throwable != null) {
            //     FirebaseCrashlytics.getInstance().recordException(throwable)
            // }
        }
    }
    
    /**
     * Record an exception (for crash reporting)
     */
    fun recordException(throwable: Throwable) {
        // In release builds, log to system log as fallback
        // TODO: Replace with Firebase Crashlytics or other crash reporting service
        if (!isDebug) {
            Log.e(TAG, "Exception recorded", throwable)
            
            // Example Firebase Crashlytics integration (uncomment when Firebase is added):
            // FirebaseCrashlytics.getInstance().recordException(throwable)
        }
    }
    
    /**
     * Set a custom key-value pair for crash reports
     */
    fun setCustomKey(key: String, value: String) {
        // TODO: Replace with Firebase Crashlytics or other crash reporting service
        // FirebaseCrashlytics.getInstance().setCustomKey(key, value)
    }
    
    /**
     * Set user identifier for crash reports
     */
    fun setUserId(userId: String) {
        // TODO: Replace with Firebase Crashlytics or other crash reporting service
        // FirebaseCrashlytics.getInstance().setUserId(userId)
    }
}

