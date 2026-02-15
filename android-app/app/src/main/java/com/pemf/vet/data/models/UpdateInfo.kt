package com.pemf.vet.data.models

data class UpdateInfo(
    val version: String,
    val url: String,
    val releaseNotes: String,
    val mandatory: Boolean = false
)
