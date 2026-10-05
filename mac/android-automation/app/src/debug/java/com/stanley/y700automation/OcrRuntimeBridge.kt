package com.stanley.y700automation

import android.content.Context
import android.graphics.Bitmap
import android.os.SystemClock
import com.paddle.ocr.PaddleOCR
import com.paddle.ocr.model.OCRRunResult
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.TimeoutException
import kotlin.math.ceil
import kotlin.math.floor
import kotlin.math.max

/**
 * Target-app-owned PaddleOCR runtime for Sprint V2.
 *
 * It deliberately lives in the target process/class loader so OpenCV and ORT
 * native libraries resolve in one namespace. Inference, load and unload are
 * serialized on one worker. Callers may time out without cancelling a native
 * inference; in-flight ownership is released only when the worker actually
 * finishes, so idle unload cannot race an active ORT call.
 */
object OcrRuntimeBridge {
    class OcrTimeoutException(message: String) : RuntimeException(message)

    private const val RUNTIME = "paddle-ppocrv6-tiny-onnx"
    private const val DEFAULT_IDLE_TIMEOUT_MS = 10L * 60L * 1000L
    private const val DEFAULT_MIN_RESIDENCY_MS = 60L * 1000L

    private val stateLock = Any()
    private val worker = Executors.newSingleThreadScheduledExecutor { runnable ->
        Thread(runnable, "y700-ocr-v2").apply { isDaemon = true }
    }

    private var engine: PaddleOCR? = null
    private var loadedAtMs = 0L
    private var lastActivityMs = 0L
    private var inFlight = 0
    private var loadCount = 0L
    private var unloadCount = 0L
    private var timeoutCount = 0L
    private var requestCount = 0L
    private var successCount = 0L
    private var idleTimeoutMs = DEFAULT_IDLE_TIMEOUT_MS
    private var minResidencyMs = DEFAULT_MIN_RESIDENCY_MS
    private var unloadFuture: ScheduledFuture<*>? = null

    @JvmStatic
    fun recognize(context: Context, bitmap: Bitmap, timeoutMs: Long): String {
        require(timeoutMs > 0L) { "timeoutMs must be positive" }
        require(!bitmap.isRecycled) { "bitmap is recycled" }
        val owned = bitmap.copy(Bitmap.Config.ARGB_8888, false)
            ?: throw IllegalStateException("unable to copy OCR bitmap")

        synchronized(stateLock) {
            requestCount++
            inFlight++
            lastActivityMs = SystemClock.elapsedRealtime()
            unloadFuture?.cancel(false)
            unloadFuture = null
        }

        val future = worker.submit<String> {
            try {
                val localEngine = ensureEngine(context.applicationContext)
                val started = SystemClock.elapsedRealtimeNanos()
                val result = runBlocking { localEngine.recognize(owned) }
                val elapsedMs = (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0
                synchronized(stateLock) { successCount++ }
                resultJson(result, elapsedMs).toString()
            } finally {
                if (!owned.isRecycled) owned.recycle()
                synchronized(stateLock) {
                    inFlight--
                    lastActivityMs = SystemClock.elapsedRealtime()
                    scheduleUnloadLocked()
                }
            }
        }

        return try {
            future.get(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (e: TimeoutException) {
            synchronized(stateLock) { timeoutCount++ }
            // Do not cancel the native task. It retains its in-flight reference
            // and will cleanly release it only after ORT/OpenCV actually return.
            throw OcrTimeoutException("OCR request exceeded ${timeoutMs}ms")
        }
    }

    @JvmStatic
    fun statusJson(): String = synchronized(stateLock) {
        JSONObject()
            .put("runtime", RUNTIME)
            .put("loaded", engine != null)
            .put("in_flight", inFlight)
            .put("loaded_at_ms", loadedAtMs)
            .put("last_activity_ms", lastActivityMs)
            .put("idle_timeout_ms", idleTimeoutMs)
            .put("minimum_residency_ms", minResidencyMs)
            .put("request_count", requestCount)
            .put("success_count", successCount)
            .put("timeout_count", timeoutCount)
            .put("load_count", loadCount)
            .put("unload_count", unloadCount)
            .toString()
    }

    /** Debug/test hook for exercising lifecycle boundaries without waiting 10 min. */
    @JvmStatic
    fun configureLifecycleForTest(idleMs: Long, minimumResidencyMs: Long) {
        require(idleMs >= 25L) { "idleMs too small" }
        require(minimumResidencyMs >= 0L) { "minimumResidencyMs must be >= 0" }
        synchronized(stateLock) {
            idleTimeoutMs = idleMs
            minResidencyMs = minimumResidencyMs
            if (engine != null && inFlight == 0) scheduleUnloadLocked()
        }
    }

    @JvmStatic
    fun resetLifecycleDefaults() {
        synchronized(stateLock) {
            idleTimeoutMs = DEFAULT_IDLE_TIMEOUT_MS
            minResidencyMs = DEFAULT_MIN_RESIDENCY_MS
            if (engine != null && inFlight == 0) scheduleUnloadLocked()
        }
    }

    private fun ensureEngine(context: Context): PaddleOCR {
        synchronized(stateLock) {
            engine?.let { return it }
        }

        // worker is single-threaded, so only one load transition can reach here.
        OpenCvBootstrap.ensureLoaded()
        val created = runBlocking { PaddleOCR.create(context) }
        synchronized(stateLock) {
            engine = created
            loadedAtMs = SystemClock.elapsedRealtime()
            lastActivityMs = loadedAtMs
            loadCount++
            return created
        }
    }

    private fun scheduleUnloadLocked() {
        unloadFuture?.cancel(false)
        unloadFuture = null
        if (engine == null || inFlight > 0) return

        val now = SystemClock.elapsedRealtime()
        val idleDeadline = lastActivityMs + idleTimeoutMs
        val residencyDeadline = loadedAtMs + minResidencyMs
        val delay = max(0L, max(idleDeadline, residencyDeadline) - now)
        unloadFuture = worker.schedule({ unloadIfEligible() }, delay, TimeUnit.MILLISECONDS)
    }

    private fun unloadIfEligible() {
        synchronized(stateLock) {
            val local = engine ?: return
            val now = SystemClock.elapsedRealtime()
            val eligible = inFlight == 0 &&
                now >= lastActivityMs + idleTimeoutMs &&
                now >= loadedAtMs + minResidencyMs
            if (!eligible) {
                scheduleUnloadLocked()
                return
            }

            // Hold the state lock across release. A new request is not accepted
            // (inFlight is not incremented) until the unload transition finishes.
            runBlocking { local.release() }
            engine = null
            unloadCount++
            unloadFuture = null
        }
    }

    private fun resultJson(result: OCRRunResult, elapsedMs: Double): JSONObject {
        val items = JSONArray()
        for (item in result.results) {
            val polygon = JSONArray()
            var minX = Float.POSITIVE_INFINITY
            var minY = Float.POSITIVE_INFINITY
            var maxX = Float.NEGATIVE_INFINITY
            var maxY = Float.NEGATIVE_INFINITY
            for (point in item.box.points) {
                minX = kotlin.math.min(minX, point.x)
                minY = kotlin.math.min(minY, point.y)
                maxX = kotlin.math.max(maxX, point.x)
                maxY = kotlin.math.max(maxY, point.y)
                polygon.put(JSONArray().put(point.x.toDouble()).put(point.y.toDouble()))
            }
            val left = floor(minX.toDouble()).toInt()
            val top = floor(minY.toDouble()).toInt()
            val right = ceil(maxX.toDouble()).toInt()
            val bottom = ceil(maxY.toDouble()).toInt()
            items.put(
                JSONObject()
                    .put("text", item.text)
                    .put("confidence", item.confidence.toDouble())
                    .put("polygon", polygon)
                    .put("bbox", JSONArray().put(left).put(top).put(right).put(bottom))
                    .put("center", JSONArray().put((left + right) / 2).put((top + bottom) / 2))
            )
        }
        return JSONObject()
            .put("runtime", RUNTIME)
            .put("latency_ms", elapsedMs)
            .put("pipeline_total_ms", result.totalTimeMs)
            .put("cold_load_ms", result.coldLoadTimeMs)
            .put("items", items)
    }
}
