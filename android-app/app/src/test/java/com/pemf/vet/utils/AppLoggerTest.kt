package com.pemf.vet.utils

import org.junit.Test
import org.junit.Assert.*

/**
 * Unit tests for AppLogger
 */
class AppLoggerTest {
    
    @Test
    fun `AppLogger should exist and be accessible`() {
        // Test that AppLogger can be accessed
        assertNotNull(AppLogger)
    }
    
    @Test
    fun `AppLogger should have all required methods`() {
        // Test that all logging methods exist
        // In DEBUG builds, these will log; in RELEASE builds, they won't
        assertDoesNotThrow {
            AppLogger.d("TestTag", "Debug message")
            AppLogger.e("TestTag", "Error message")
            AppLogger.w("TestTag", "Warning message")
            AppLogger.i("TestTag", "Info message")
            AppLogger.v("TestTag", "Verbose message")
        }
    }
    
    @Test
    fun `AppLogger should handle exceptions`() {
        val exception = RuntimeException("Test exception")
        assertDoesNotThrow {
            AppLogger.e("TestTag", "Error with exception", exception)
        }
    }
}

// Helper function for JUnit 4 compatibility
private fun assertDoesNotThrow(block: () -> Unit) {
    try {
        block()
    } catch (e: Exception) {
        fail("Expected no exception, but got: ${e.message}")
    }
}

