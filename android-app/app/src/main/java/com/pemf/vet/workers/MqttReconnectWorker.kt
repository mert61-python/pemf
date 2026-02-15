package com.pemf.vet.workers

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.*
import com.pemf.vet.data.api.MqttService
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import java.util.concurrent.TimeUnit

/**
 * Background worker to ensure MQTT connection stays active
 * Runs periodically to check and reconnect if needed
 */
@HiltWorker
class MqttReconnectWorker @AssistedInject constructor(
    @Assisted appContext: Context,
    @Assisted workerParams: WorkerParameters,
    private val mqttService: MqttService
) : CoroutineWorker(appContext, workerParams) {

    companion object {
        private const val WORK_NAME = "mqtt_reconnect_worker"
        private const val REPEAT_INTERVAL_MINUTES = 15L

        fun schedule(context: Context) {
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val request = PeriodicWorkRequestBuilder<MqttReconnectWorker>(
                REPEAT_INTERVAL_MINUTES,
                TimeUnit.MINUTES
            )
                .setConstraints(constraints)
                .setBackoffCriteria(
                    BackoffPolicy.EXPONENTIAL,
                    WorkRequest.MIN_BACKOFF_MILLIS,
                    TimeUnit.MILLISECONDS
                )
                .build()

            WorkManager.getInstance(context).enqueueUniquePeriodicWork(
                WORK_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                request
            )
        }

        fun cancel(context: Context) {
            WorkManager.getInstance(context).cancelUniqueWork(WORK_NAME)
        }
    }

    override suspend fun doWork(): Result {
        return try {
            // Check if connected, if not try to reconnect
            if (!mqttService.isConnected()) {
                mqttService.reconnect()
            }
            Result.success()
        } catch (e: Exception) {
            Result.retry()
        }
    }
}
