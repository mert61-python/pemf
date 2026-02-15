package com.pemf.vet.data.repository

import com.pemf.vet.data.models.Session
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SessionRepository @Inject constructor() {

    private val _session = MutableStateFlow(Session())
    val session: StateFlow<Session> = _session.asStateFlow()

    fun updateSession(session: Session) {
        _session.value = session
    }
    
    fun getActiveSession(): StateFlow<Session> = session
}

