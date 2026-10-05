package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;
import org.opencv.core.Core;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Production V1 template locator.
 *
 * This class resolves targets only. The shared Automation Core Action Executor
 * remains responsible for input injection and postconditions.
 */
public final class VisionTemplateLocator {
    public static final String ERR_POLICY_BLOCKED = "VISION_POLICY_BLOCKED";
    private static final double DEFAULT_CONFIDENCE = 0.90;
    private static final double DEFAULT_MIN_VARIANCE = 8.0;
    private static final double DEFAULT_SECOND_BEST_DELTA = 0.03;
    private static final int SMALL_TARGET_PX = 48;
    private static final int CACHE_MAX_ENTRIES = 16;
    private static final long CACHE_MAX_BYTES = 24L * 1024L * 1024L;

    private static final LinkedHashMap<String, CachedTemplate> CACHE =
            new LinkedHashMap<>(16, 0.75f, true);
    private static long cacheBytes = 0L;
    private static boolean openCvLoaded = false;

    public static final class Config {
        public final boolean enabled;
        public final String mode;
        public final boolean templateEnabled;
        public final boolean allowHighRiskVision;
        public final long evidenceMaxBytes;

        public Config(JSONObject vision) {
            JSONObject v = vision == null ? new JSONObject() : vision;
            this.enabled = v.optBoolean("enabled", false);
            this.mode = v.optString("mode", "fallback");
            this.templateEnabled = v.optBoolean("template_enabled", true);
            this.allowHighRiskVision = v.optBoolean("allow_high_risk_vision", false);
            long requested = v.optLong("evidence_max_bytes", 64L * 1024L * 1024L);
            this.evidenceMaxBytes = Math.max(8L * 1024L * 1024L,
                    Math.min(512L * 1024L * 1024L, requested));
        }

        public JSONObject json() throws Exception {
            return new JSONObject()
                    .put("enabled", enabled)
                    .put("mode", mode)
                    .put("template_enabled", templateEnabled)
                    .put("allow_high_risk_vision", allowHighRiskVision)
                    .put("evidence_max_bytes", evidenceMaxBytes);
        }
    }

    public static final class Metrics {
        long visionRequestCount;
        long visionSuccessCount;
        long visionFailureCount;
        long semanticToVisionFallbackCount;
        long templateRequestCount;
        long templateSuccessCount;
        long cacheHitCount;
        long staleTargetCount;
        long rotationMismatchCount;
        long captureRetryCount;
        long captureFailedCount;
        long oomThrottledCount;
        long templateAmbiguousCount;
        long falsePositivePostconditionFailureCount;
        final List<Double> frameCaptureMs = new ArrayList<>();
        final List<Double> templateMatchMs = new ArrayList<>();
        final List<Double> visionTotalMs = new ArrayList<>();

        public JSONObject json() throws Exception {
            return new JSONObject()
                    .put("vision_request_count", visionRequestCount)
                    .put("vision_success_count", visionSuccessCount)
                    .put("vision_failure_count", visionFailureCount)
                    .put("semantic_to_vision_fallback_count", semanticToVisionFallbackCount)
                    .put("template_request_count", templateRequestCount)
                    .put("template_success_count", templateSuccessCount)
                    .put("ocr_request_count", 0)
                    .put("ocr_success_count", 0)
                    .put("cache_hit_count", cacheHitCount)
                    .put("stale_target_count", staleTargetCount)
                    .put("vision_stale_target_count", staleTargetCount)
                    .put("vision_rotation_mismatch_count", rotationMismatchCount)
                    .put("vision_capture_retry_count", captureRetryCount)
                    .put("vision_capture_failed_count", captureFailedCount)
                    .put("vision_oom_throttled_count", oomThrottledCount)
                    .put("vision_template_ambiguous_count", templateAmbiguousCount)
                    .put("vision_evidence_eviction_count", 0)
                    .put("false_positive_postcondition_failure_count",
                            falsePositivePostconditionFailureCount)
                    .put("frame_capture_ms", VisionV0Harness.percentiles(frameCaptureMs))
                    .put("template_match_ms", VisionV0Harness.percentiles(templateMatchMs))
                    .put("ocr_ms", new JSONObject())
                    .put("vision_total_ms", VisionV0Harness.percentiles(visionTotalMs));
        }
    }

    public static final class Resolved {
        public final VisionV0Harness.VisionTarget target;
        public final JSONObject metadata;
        public final Rect roi;
        public final String clickPolicy;
        public final long roiFingerprint;

        Resolved(
                VisionV0Harness.VisionTarget target,
                JSONObject metadata,
                Rect roi,
                String clickPolicy,
                long roiFingerprint) {
            this.target = target;
            this.metadata = metadata;
            this.roi = roi;
            this.clickPolicy = clickPolicy;
            this.roiFingerprint = roiFingerprint;
        }
    }

    private static final class CachedTemplate {
        final String path;
        final String sha256;
        final String version;
        final Bitmap bitmap;
        final long bytes;

        CachedTemplate(String path, String sha256, String version, Bitmap bitmap) {
            this.path = path;
            this.sha256 = sha256;
            this.version = version;
            this.bitmap = bitmap;
            this.bytes = Math.max(1L, bitmap.getAllocationByteCount());
        }
    }

    private final Instrumentation instrumentation;
    private final UiDevice device;
    private final Config config;
    private final Metrics metrics = new Metrics();
    private final Random random;

    public VisionTemplateLocator(
            Instrumentation instrumentation,
            UiDevice device,
            Config config,
            long deterministicSeed) throws VisionV0Harness.VisionFailure {
        this.instrumentation = instrumentation;
        this.device = device;
        this.config = config;
        this.random = new Random(deterministicSeed);
        if (config.enabled && config.templateEnabled && "fallback".equals(config.mode)) {
            ensureOpenCv(instrumentation);
        }
    }

    public Config config() {
        return config;
    }

    public Metrics metrics() {
        return metrics;
    }

    public void noteSemanticFallback() {
        metrics.semanticToVisionFallbackCount++;
    }

    public void notePostconditionFailure() {
        metrics.falsePositivePostconditionFailureCount++;
    }

    public static boolean hasVisionTemplate(JSONObject selector) {
        return visionSpec(selector) != null;
    }

    public static JSONObject visionSpec(JSONObject selector) {
        if (selector == null) return null;
        if ("vision_template".equals(selector.optString("type"))) {
            return selector;
        }
        JSONArray fallback = selector.optJSONArray("fallback");
        if (fallback == null) return null;
        for (int i = 0; i < fallback.length(); i++) {
            JSONObject item = fallback.optJSONObject(i);
            if (item != null && "vision_template".equals(item.optString("type"))) {
                return item;
            }
        }
        return null;
    }

    public static void validateTemplateSpec(JSONObject spec)
            throws VisionV0Harness.VisionFailure {
        if (spec == null || !"vision_template".equals(spec.optString("type"))) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "vision template selector requires type=vision_template");
        }
        Iterator<String> keys = spec.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            switch (key) {
                case "type":
                case "template":
                case "template_sha256":
                case "template_version":
                case "confidence":
                case "roi":
                case "roi_ratio":
                case "scale":
                case "min_variance":
                case "min_second_best_delta":
                case "use_alpha_mask":
                case "click_policy":
                case "expected_package":
                    break;
                default:
                    throw new VisionV0Harness.VisionFailure(
                            VisionV0Harness.ERR_TEMPLATE_CONFIG,
                            "unsupported vision_template key: " + key);
            }
        }

        String template = spec.optString("template", "");
        if (template.isEmpty() || template.startsWith("/") || template.contains("..") ||
                template.contains("\\")) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "template must be a relative asset path without traversal");
        }
        String sha = spec.optString("template_sha256", "");
        if (!sha.matches("(?i)[0-9a-f]{64}")) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "template_sha256 must be 64 hex characters");
        }
        double confidence = spec.optDouble("confidence", DEFAULT_CONFIDENCE);
        if (!Double.isFinite(confidence) || confidence < 0.0 || confidence > 1.0) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "confidence must be finite within [0,1]");
        }
        double delta = spec.optDouble("min_second_best_delta", DEFAULT_SECOND_BEST_DELTA);
        if (!Double.isFinite(delta) || delta < 0.0 || delta > 1.0) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "min_second_best_delta must be finite within [0,1]");
        }
        if (spec.has("roi") && spec.has("roi_ratio")) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_INVALID_ROI,
                    "roi and roi_ratio are mutually exclusive");
        }
        String clickPolicy = spec.optString("click_policy", "EXACT").toUpperCase(Locale.ROOT);
        if (!"EXACT".equals(clickPolicy) && !"SAFE_JITTER".equals(clickPolicy)) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "unsupported click_policy=" + clickPolicy);
        }
        JSONObject scale = spec.optJSONObject("scale");
        if (scale != null) {
            VisionV0Harness.deterministicScales(
                    scale.optDouble("min", 1.0),
                    scale.optDouble("max", 1.0),
                    scale.optDouble("step", 0.05));
        }
    }

    public synchronized Resolved resolve(JSONObject spec)
            throws Exception {
        metrics.visionRequestCount++;
        metrics.templateRequestCount++;
        long totalStart = SystemClock.elapsedRealtimeNanos();
        try {
            if (!config.enabled) {
                throw new VisionV0Harness.VisionFailure(
                        ERR_POLICY_BLOCKED, "vision_enabled=false");
            }
            if (!"fallback".equals(config.mode)) {
                throw new VisionV0Harness.VisionFailure(
                        ERR_POLICY_BLOCKED, "vision mode must be fallback for V1");
            }
            if (!config.templateEnabled) {
                throw new VisionV0Harness.VisionFailure(
                        ERR_POLICY_BLOCKED, "template vision is disabled");
            }
            validateTemplateSpec(spec);

            String expectedPackage = spec.optString("expected_package", "");
            String currentPackage = device.getCurrentPackageName();
            if (!expectedPackage.isEmpty() && !expectedPackage.equals(currentPackage)) {
                throw new VisionV0Harness.VisionFailure(
                        ERR_POLICY_BLOCKED,
                        "current package does not match expected_package");
            }

            CachedTemplate template = loadTemplate(spec);
            int retriesBefore = VisionV0Harness.captureRetryCount();
            long captureStart = SystemClock.elapsedRealtimeNanos();
            VisionV0Harness.Frame frame = null;
            try {
                frame = VisionV0Harness.capture(instrumentation, device, null, 0L);
                metrics.frameCaptureMs.add(msSince(captureStart));
                int retryDelta = Math.max(0,
                        VisionV0Harness.captureRetryCount() - retriesBefore);
                metrics.captureRetryCount += retryDelta;

                Rect roi = VisionV0Harness.resolveRoi(
                        frame.width,
                        frame.height,
                        intArray(spec.optJSONArray("roi")),
                        doubleArray(spec.optJSONArray("roi_ratio")));

                double confidence = spec.optDouble("confidence", DEFAULT_CONFIDENCE);
                double minVariance = spec.optDouble("min_variance", DEFAULT_MIN_VARIANCE);
                double secondDelta =
                        spec.optDouble("min_second_best_delta", DEFAULT_SECOND_BEST_DELTA);
                boolean useAlpha = spec.optBoolean("use_alpha_mask", false);

                long matchStart = SystemClock.elapsedRealtimeNanos();
                VisionV0Harness.VisionTarget target;
                JSONObject scale = spec.optJSONObject("scale");
                if (scale == null) {
                    target = VisionV0Harness.matchTemplate(
                            frame,
                            template.bitmap,
                            roi,
                            useAlpha,
                            confidence,
                            minVariance,
                            secondDelta);
                } else {
                    List<Double> scales = VisionV0Harness.deterministicScales(
                            scale.optDouble("min", 1.0),
                            scale.optDouble("max", 1.0),
                            scale.optDouble("step", 0.05));
                    target = VisionV0Harness.matchTemplateMultiScale(
                            frame,
                            template.bitmap,
                            roi,
                            useAlpha,
                            scales,
                            confidence,
                            minVariance,
                            secondDelta);
                }
                double matchMs = msSince(matchStart);
                metrics.templateMatchMs.add(matchMs);

                JSONObject metadata = target.json()
                        .put("locator_type", "vision_template")
                        .put("template", template.path)
                        .put("template_sha256", template.sha256)
                        .put("template_version", template.version)
                        .put("roi", rectJson(roi))
                        .put("frame_width", frame.width)
                        .put("frame_height", frame.height)
                        .put("display_rotation", frame.rotation)
                        .put("frame_capture_ms", metrics.frameCaptureMs.get(
                                metrics.frameCaptureMs.size() - 1))
                        .put("template_match_ms", matchMs)
                        .put("package", currentPackage == null ? JSONObject.NULL : currentPackage);

                long roiFingerprint = VisionV0Harness.fingerprintRegion(frame.bitmap, roi);
                metadata.put("roi_fingerprint", Long.toUnsignedString(roiFingerprint));
                metrics.templateSuccessCount++;
                metrics.visionSuccessCount++;
                metrics.visionTotalMs.add(msSince(totalStart));
                return new Resolved(
                        target,
                        metadata,
                        roi,
                        spec.optString("click_policy", "EXACT").toUpperCase(Locale.ROOT),
                        roiFingerprint);
            } finally {
                if (frame != null) frame.close();
            }
        } catch (VisionV0Harness.VisionFailure e) {
            metrics.visionFailureCount++;
            if (VisionV0Harness.ERR_TEMPLATE_AMBIGUOUS.equals(e.code)) {
                metrics.templateAmbiguousCount++;
            } else if (VisionV0Harness.ERR_CAPTURE_FAILED.equals(e.code)) {
                metrics.captureFailedCount++;
            } else if (VisionV0Harness.ERR_OOM_THROTTLED.equals(e.code)) {
                metrics.oomThrottledCount++;
            } else if (VisionV0Harness.ERR_STALE_TARGET.equals(e.code)) {
                metrics.staleTargetCount++;
            } else if (VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code)) {
                metrics.rotationMismatchCount++;
            }
            metrics.visionTotalMs.add(msSince(totalStart));
            throw e;
        }
    }

    public void validatePreAction(Resolved resolved) throws VisionV0Harness.VisionFailure {
        VisionV0Harness.Frame current = null;
        try {
            long captureStart = SystemClock.elapsedRealtimeNanos();
            current = VisionV0Harness.capture(instrumentation, device, null, 0L);
            metrics.frameCaptureMs.add(msSince(captureStart));
            VisionV0Harness.validatePreAction(
                    resolved.target,
                    current.rotation,
                    current.width,
                    current.height,
                    null);
            long currentRoiFingerprint =
                    VisionV0Harness.fingerprintRegion(current.bitmap, resolved.roi);
            if (currentRoiFingerprint != resolved.roiFingerprint) {
                throw new VisionV0Harness.VisionFailure(
                        VisionV0Harness.ERR_STALE_TARGET,
                        "effective ROI fingerprint changed before action");
            }
        } catch (VisionV0Harness.VisionFailure e) {
            if (VisionV0Harness.ERR_STALE_TARGET.equals(e.code)) {
                metrics.staleTargetCount++;
            } else if (VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code)) {
                metrics.rotationMismatchCount++;
            }
            throw e;
        } finally {
            if (current != null) current.close();
        }
    }

    public int[] clickPoint(Resolved resolved, boolean destructive) {
        Rect b = resolved.target.bbox;
        int cx = b.centerX();
        int cy = b.centerY();
        if (destructive || !"SAFE_JITTER".equals(resolved.clickPolicy) ||
                b.width() < SMALL_TARGET_PX || b.height() < SMALL_TARGET_PX) {
            return new int[]{cx, cy};
        }

        double maxDx = b.width() * 0.20;
        double maxDy = b.height() * 0.20;
        double dx = truncateGaussian(random.nextGaussian() * (maxDx / 3.0), maxDx);
        double dy = truncateGaussian(random.nextGaussian() * (maxDy / 3.0), maxDy);
        int x = (int) Math.round(cx + dx);
        int y = (int) Math.round(cy + dy);

        int insetX = Math.max(1, (int) Math.ceil(b.width() * 0.20));
        int insetY = Math.max(1, (int) Math.ceil(b.height() * 0.20));
        Rect safe = new Rect(
                b.left + insetX,
                b.top + insetY,
                b.right - insetX,
                b.bottom - insetY);
        if (safe.width() <= 0 || safe.height() <= 0 || !safe.contains(x, y)) {
            return new int[]{cx, cy};
        }
        return new int[]{x, y};
    }

    private CachedTemplate loadTemplate(JSONObject spec) throws Exception {
        String path = spec.getString("template");
        String expectedSha = spec.getString("template_sha256").toLowerCase(Locale.ROOT);
        String version = spec.optString("template_version", "sha256");
        String key = path + "|" + expectedSha + "|" + version;

        synchronized (CACHE) {
            CachedTemplate hit = CACHE.get(key);
            if (hit != null && !hit.bitmap.isRecycled()) {
                metrics.cacheHitCount++;
                return hit;
            }
        }

        byte[] bytes;
        try (InputStream in = instrumentation.getContext().getAssets()
                .open("vision_templates/" + path);
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[32 * 1024];
            int n;
            while ((n = in.read(buffer)) >= 0) {
                if (n > 0) out.write(buffer, 0, n);
            }
            bytes = out.toByteArray();
        } catch (Exception e) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "template asset unavailable: " + path);
        }

        String actualSha = sha256(bytes);
        if (!expectedSha.equals(actualSha)) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "template SHA-256 mismatch for " + path);
        }
        Bitmap bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
        if (bitmap == null || bitmap.getWidth() <= 0 || bitmap.getHeight() <= 0) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_TEMPLATE_CONFIG,
                    "template decode failed: " + path);
        }

        CachedTemplate loaded = new CachedTemplate(
                path, expectedSha, version, bitmap);
        synchronized (CACHE) {
            Iterator<Map.Entry<String, CachedTemplate>> it = CACHE.entrySet().iterator();
            while (it.hasNext()) {
                Map.Entry<String, CachedTemplate> entry = it.next();
                CachedTemplate old = entry.getValue();
                if (old.path.equals(path) && !entry.getKey().equals(key)) {
                    cacheBytes -= old.bytes;
                    if (!old.bitmap.isRecycled()) old.bitmap.recycle();
                    it.remove();
                }
            }
            CACHE.put(key, loaded);
            cacheBytes += loaded.bytes;
            trimCache();
        }
        return loaded;
    }

    private static void trimCache() {
        Iterator<Map.Entry<String, CachedTemplate>> it = CACHE.entrySet().iterator();
        while ((CACHE.size() > CACHE_MAX_ENTRIES || cacheBytes > CACHE_MAX_BYTES)
                && it.hasNext()) {
            CachedTemplate old = it.next().getValue();
            cacheBytes -= old.bytes;
            if (!old.bitmap.isRecycled()) old.bitmap.recycle();
            it.remove();
        }
    }

    private static void ensureOpenCv(Instrumentation instrumentation)
            throws VisionV0Harness.VisionFailure {
        synchronized (VisionTemplateLocator.class) {
            if (openCvLoaded) return;

            Throwable bootstrapFailure = null;
            try {
                ClassLoader targetLoader = instrumentation.getTargetContext().getClassLoader();
                Class<?> bootstrap = Class.forName(
                        "com.stanley.y700automation.OpenCvBootstrap",
                        true,
                        targetLoader);
                Object version = bootstrap.getMethod("ensureLoaded").invoke(null);
                if (version == null || String.valueOf(version).isEmpty()) {
                    throw new IllegalStateException("OpenCV target bootstrap returned no version");
                }
                openCvLoaded = true;
                return;
            } catch (Throwable t) {
                bootstrapFailure = t;
            }

            Throwable loadLibraryFailure = null;
            try {
                System.loadLibrary("opencv_java4");
                Core.getVersionString();
                openCvLoaded = true;
                return;
            } catch (Throwable t) {
                loadLibraryFailure = t;
            }

            try {
                String nativeDir = instrumentation.getTargetContext()
                        .getApplicationInfo().nativeLibraryDir;
                String cxxPath = nativeDir + "/" + System.mapLibraryName("c++_shared");
                String libraryPath = nativeDir + "/" +
                        System.mapLibraryName("opencv_java4");
                try {
                    System.load(cxxPath);
                } catch (Throwable ignored) {
                    // OpenCV may not require an explicit preload when the target
                    // native namespace already exposes libc++_shared.
                }
                System.load(libraryPath);
                Core.getVersionString();
                openCvLoaded = true;
            } catch (Throwable t) {
                throw new VisionV0Harness.VisionFailure(
                        "VISION_MODEL_UNAVAILABLE",
                        "OpenCV runtime unavailable: targetBootstrap=" +
                                failureSummary(bootstrapFailure) +
                                ", loadLibrary=" + failureSummary(loadLibraryFailure) +
                                ", absoluteLoad=" + failureSummary(t));
            }
        }
    }

    private static String failureSummary(Throwable t) {
        if (t == null) return "none";
        Throwable root = t;
        while (root.getCause() != null && root.getCause() != root) {
            root = root.getCause();
        }
        String message = root.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return root.getClass().getSimpleName();
        }
        message = message.replace('\n', ' ').replace('\r', ' ').trim();
        if (message.length() > 240) {
            message = message.substring(0, 240);
        }
        return root.getClass().getSimpleName() + ":" + message;
    }

    private static int[] intArray(JSONArray arr) throws VisionV0Harness.VisionFailure {
        if (arr == null) return null;
        if (arr.length() != 4) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_INVALID_ROI, "roi must have 4 entries");
        }
        int[] out = new int[4];
        for (int i = 0; i < 4; i++) out[i] = arr.optInt(i, Integer.MIN_VALUE);
        return out;
    }

    private static double[] doubleArray(JSONArray arr) throws VisionV0Harness.VisionFailure {
        if (arr == null) return null;
        if (arr.length() != 4) {
            throw new VisionV0Harness.VisionFailure(
                    VisionV0Harness.ERR_INVALID_ROI, "roi_ratio must have 4 entries");
        }
        double[] out = new double[4];
        for (int i = 0; i < 4; i++) out[i] = arr.optDouble(i, Double.NaN);
        return out;
    }

    private static JSONArray rectJson(Rect r) {
        return new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom);
    }

    private static double truncateGaussian(double value, double limit) {
        return Math.max(-limit, Math.min(limit, value));
    }

    private static double msSince(long startNs) {
        return (SystemClock.elapsedRealtimeNanos() - startNs) / 1_000_000.0;
    }

    private static String sha256(byte[] data) throws Exception {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        byte[] hash = digest.digest(data);
        StringBuilder out = new StringBuilder(hash.length * 2);
        for (byte b : hash) out.append(String.format(Locale.US, "%02x", b & 0xff));
        return out.toString();
    }
}
