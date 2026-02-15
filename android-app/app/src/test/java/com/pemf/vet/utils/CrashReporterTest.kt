package com.pemf.vet.utils

import org.junit.Test
import org.junit.Assert.*

/**
 * Unit tests for CrashReporter
 */
class CrashReporterTest {
    
    @Test
    fun `CrashReporter should exist and be accessible`() {
        assertNotNull(CrashReporter)
    }
    
    @Test
    fun `CrashReporter should handle error logging`() {
        assertDoesNotThrow {
            CrashReporter.logError("TestTag", "Test error message")
        }
    }
    
    @Test
    fun `CrashReporter should handle exception recording`() {
        val exception = RuntimeException("Test exception")
        assertDoesNotThrow {
            CrashReporter.recordException(exception)
        }
    }
    
    @Test
    fun `CrashReporter should handle custom keys`() {
        assertDoesNotThrow {
            CrashReporter.setCustomKey("test_key", "test_value")
        }
    }
    
    @Test
    fun `CrashReporter should handle user ID setting`() {
        assertDoesNotThrow {
            CrashReporter.setUserId("test_user_123")
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

