package com.pemf.vet.utils

import android.util.Log

/**
 * Production-safe logging utility
 * Logs are only shown in DEBUG builds, not in RELEASE builds
 */
object AppLogger {
    private const val DEFAULT_TAG = "PEMFVet"
    
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
    
    @JvmStatic
    fun d(tag: String = DEFAULT_TAG, message: String, throwable: Throwable? = null) {
        if (isDebug) {
            if (throwable != null) {
                Log.d(tag, message, throwable)
            } else {
                Log.d(tag, message)
            }
        }
    }
    
    @JvmStatic
    fun e(tag: String = DEFAULT_TAG, message: String, throwable: Throwable? = null) {
        // Errors are always logged, but in release builds they can be sent to crash reporting
        if (isDebug) {
            if (throwable != null) {
                Log.e(tag, message, throwable)
            } else {
                Log.e(tag, message)
            }
        } else {
            // In release builds, send to crash reporting if available
            CrashReporter.logError(tag, message, throwable)
        }
    }
    
    @JvmStatic
    fun w(tag: String = DEFAULT_TAG, message: String, throwable: Throwable? = null) {
        if (isDebug) {
            if (throwable != null) {
                Log.w(tag, message, throwable)
            } else {
                Log.w(tag, message)
            }
        }
    }
    
    @JvmStatic
    fun i(tag: String = DEFAULT_TAG, message: String) {
        if (isDebug) {
            Log.i(tag, message)
        }
    }
    
    @JvmStatic
    fun v(tag: String = DEFAULT_TAG, message: String) {
        if (isDebug) {
            Log.v(tag, message)
        }
    }
}

