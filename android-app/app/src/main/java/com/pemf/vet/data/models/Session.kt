package com.pemf.vet.data.models

import android.os.Parcelable
import kotlinx.parcelize.Parcelize

@Parcelize
data class Session(
    val sessionId: Int? = null,
    val active: Boolean = false,
    val startTimestamp: Long = 0, // Unix Epoch milliseconds (for local countdown calculation)
    val startTime: String? = null, // Deprecated: kept for backward compatibility, use startTimestamp instead
    val duration: Int = 0, // minutes
    val remainingTime: Int = 0, // minutes (deprecated: calculated locally from startTimestamp)
    val frequency: Float = 0f, // Hz
    val intensity: Float = 0f, // mT
    val target: String? = null,
    val treatmentMode: String? = null,
    val patientName: String? = null,
    val patientInfo: PatientInfo? = null,
    val activeESPs: List<String> = emptyList()
) : Parcelable

@Parcelize
data class PatientInfo(
    val name: String? = null,
    val age: String? = null,
    val species: String? = null,
    val breed: String? = null,
    val weight: String? = null,
    val owner: String? = null,
    val veterinarian: String? = null
) : Parcelable

