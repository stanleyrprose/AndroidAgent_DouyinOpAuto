package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.uiautomator.UiDevice;

import com.stanley.y700automation.vision.VisionV0Harness.VisionFailure;

import org.json.JSONArray;
import org.json.JSONObject;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;

/** OCR selector backend. It resolves only; shared Action Executor owns input. */
public final class OcrTextLocator {
    public static final String ERR_POLICY_BLOCKED = "VISION_POLICY_BLOCKED";
    public static final String ERR_INVALID_PATTERN = "VISION_INVALID_PATTERN";
    public static final String ERR_TIMEOUT = "VISION_OCR_TIMEOUT";
    public static final String ERR_NOT_FOUND = "VISION_OCR_NOT_FOUND";
    public static final String ERR_AMBIGUOUS = "VISION_OCR_AMBIGUOUS";
    public static final String ERR_MODEL = "VISION_MODEL_UNAVAILABLE";

    private static final int MAX_PATTERN_LENGTH = 128;
    private static final int MAX_REGEX_INPUT_LENGTH = 512;
    private static final double DEFAULT_MIN_CONFIDENCE = 0.85;
    private static final long DEFAULT_TIMEOUT_MS = 5000L;
    // Real-Y700 V2 benchmark: very short detector crops depressed confidence
    // on otherwise correct text. The request ROI remains the acceptance/click
    // boundary; only inference receives this minimum vertical context.
    private static final int MIN_INFERENCE_CONTEXT_HEIGHT_PX = 512;

    public static final class Metrics {
        long requestCount;
        long successCount;
        long failureCount;
        long timeoutCount;
        long cacheHitCount;
        long contextRetryCount;
        long lowConfidenceRejectedCount;
        long ambiguousCount;
        long staleTargetCount;
        long rotationMismatchCount;
        long postconditionFailureCount;
        final List<Double> ocrMs = new ArrayList<>();

        public JSONObject json() throws Exception {
            return new JSONObject()
                    .put("ocr_request_count", requestCount)
                    .put("ocr_success_count", successCount)
                    .put("ocr_failure_count", failureCount)
                    .put("ocr_timeout_count", timeoutCount)
                    .put("ocr_cache_hit_count", cacheHitCount)
                    .put("ocr_context_retry_count", contextRetryCount)
                    .put("ocr_low_confidence_rejected_count", lowConfidenceRejectedCount)
                    .put("ocr_ambiguous_count", ambiguousCount)
                    .put("ocr_stale_target_count", staleTargetCount)
                    .put("ocr_rotation_mismatch_count", rotationMismatchCount)
                    .put("ocr_postcondition_failure_count", postconditionFailureCount)
                    .put("ocr_ms", VisionV0Harness.percentiles(ocrMs));
        }
    }

    public static final class Resolved {
        public final Rect bbox;
        public final int centerX;
        public final int centerY;
        public final double confidence;
        public final JSONObject metadata;
        public final Rect roi;
        public final long roiFingerprint;
        public final int frameRotation;
        public final int frameWidth;
        public final int frameHeight;

        Resolved(Rect bbox, double confidence, JSONObject metadata, Rect roi,
                 long roiFingerprint, VisionV0Harness.Frame frame) {
            this.bbox = bbox;
            this.centerX = bbox.centerX();
            this.centerY = bbox.centerY();
            this.confidence = confidence;
            this.metadata = metadata;
            this.roi = new Rect(roi);
            this.roiFingerprint = roiFingerprint;
            this.frameRotation = frame.rotation;
            this.frameWidth = frame.width;
            this.frameHeight = frame.height;
        }
    }

    private static final class OcrCandidate {
        final JSONObject item;
        final Rect bbox;

        OcrCandidate(JSONObject item, Rect bbox) {
            this.item = item;
            this.bbox = bbox;
        }
    }

    private final Instrumentation instrumentation;
    private final UiDevice device;
    private final VisionTemplateLocator.Config config;
    private final Metrics metrics = new Metrics();

    private long cachedFingerprint = Long.MIN_VALUE;
    private int cachedRotation = -1;
    private int cachedWidth = -1;
    private int cachedHeight = -1;
    private Rect cachedRoi;
    private Rect cachedInferenceRoi;
    private boolean cachedContextRetry;
    private JSONObject cachedOcr;

    public OcrTextLocator(
            Instrumentation instrumentation,
            UiDevice device,
            VisionTemplateLocator.Config config) {
        this.instrumentation = instrumentation;
        this.device = device;
        this.config = config;
    }

    public Metrics metrics() {
        return metrics;
    }

    public void notePostconditionFailure() {
        metrics.postconditionFailureCount++;
    }

    public static JSONObject visionTextSpec(JSONObject selector) {
        if (selector == null) return null;
        if ("vision_text".equals(selector.optString("type"))) return selector;
        JSONArray fallback = selector.optJSONArray("fallback");
        if (fallback == null) return null;
        for (int i = 0; i < fallback.length(); i++) {
            JSONObject item = fallback.optJSONObject(i);
            if (item != null && "vision_text".equals(item.optString("type"))) return item;
        }
        return null;
    }

    public static void validateTextSpec(JSONObject spec) throws VisionFailure {
        if (spec == null || !"vision_text".equals(spec.optString("type"))) {
            throw new VisionFailure(ERR_INVALID_PATTERN,
                    "OCR selector requires type=vision_text");
        }
        String pattern = spec.optString("pattern", "");
        if (pattern.isEmpty() || pattern.length() > MAX_PATTERN_LENGTH) {
            throw new VisionFailure(ERR_INVALID_PATTERN,
                    "OCR pattern must contain 1.." + MAX_PATTERN_LENGTH + " characters");
        }
        String match = spec.optString("match", "substring");
        if (!"substring".equals(match) && !"regex".equals(match)) {
            throw new VisionFailure(ERR_INVALID_PATTERN,
                    "OCR match must be substring or regex");
        }
        if ("regex".equals(match)) validateRegex(pattern);
        if (spec.has("roi") && spec.has("roi_ratio")) {
            throw new VisionFailure(VisionV0Harness.ERR_INVALID_ROI,
                    "roi and roi_ratio are mutually exclusive");
        }
        double minConfidence = spec.optDouble("min_confidence", DEFAULT_MIN_CONFIDENCE);
        if (!Double.isFinite(minConfidence) || minConfidence < 0.0 || minConfidence > 1.0) {
            throw new VisionFailure(ERR_INVALID_PATTERN, "min_confidence must be within [0,1]");
        }
        Iterator<String> keys = spec.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            switch (key) {
                case "type":
                case "pattern":
                case "match":
                case "roi":
                case "roi_ratio":
                case "min_confidence":
                case "expected_package":
                    break;
                default:
                    throw new VisionFailure(ERR_INVALID_PATTERN,
                            "unsupported vision_text key: " + key);
            }
        }
    }

    public synchronized Resolved resolve(JSONObject spec, long requestTimeoutMs)
            throws Exception {
        metrics.requestCount++;
        long totalStarted = SystemClock.elapsedRealtimeNanos();
        try {
            if (!config.enabled) {
                throw new VisionFailure(ERR_POLICY_BLOCKED, "vision_enabled=false");
            }
            if (!config.ocrEnabled) {
                throw new VisionFailure(ERR_POLICY_BLOCKED, "ocr_enabled=false");
            }
            if (!"fallback".equals(config.mode)) {
                throw new VisionFailure(ERR_POLICY_BLOCKED,
                        "vision mode must be fallback for V2");
            }
            validateTextSpec(spec);

            String expectedPackage = spec.optString("expected_package", "");
            String currentPackage = device.getCurrentPackageName();
            if (!expectedPackage.isEmpty() && !expectedPackage.equals(currentPackage)) {
                throw new VisionFailure(ERR_POLICY_BLOCKED,
                        "current package does not match expected_package");
            }

            long timeoutMs = requestTimeoutMs > 0 ? requestTimeoutMs : DEFAULT_TIMEOUT_MS;
            timeoutMs = Math.max(250L, Math.min(30_000L, timeoutMs));
            long deadlineNs = SystemClock.elapsedRealtimeNanos() + timeoutMs * 1_000_000L;

            VisionV0Harness.Frame frame = null;
            try {
                frame = VisionV0Harness.capture(instrumentation, device, null, 0L);
                Rect roi = VisionV0Harness.resolveRoi(
                        frame.width,
                        frame.height,
                        intArray(spec.optJSONArray("roi")),
                        doubleArray(spec.optJSONArray("roi_ratio")));
                long roiFingerprint = VisionV0Harness.fingerprintRegion(frame.bitmap, roi);

                boolean cacheHit = cachedOcr != null &&
                        roiFingerprint == cachedFingerprint &&
                        frame.rotation == cachedRotation &&
                        frame.width == cachedWidth && frame.height == cachedHeight &&
                        cachedRoi != null && cachedRoi.equals(roi) &&
                        cachedInferenceRoi != null;
                if (cacheHit) {
                    metrics.cacheHitCount++;
                    Resolved resolved = select(
                            spec,
                            new JSONObject(cachedOcr.toString()),
                            roi,
                            new Rect(cachedInferenceRoi),
                            roiFingerprint,
                            frame,
                            true,
                            cachedContextRetry);
                    metrics.successCount++;
                    metrics.ocrMs.add(msSince(totalStarted));
                    return resolved;
                }

                Rect inferenceRoi = new Rect(roi);
                JSONObject raw = invokeRuntimeOnRoi(frame.bitmap, inferenceRoi, deadlineNs);
                try {
                    Resolved resolved = select(
                            spec,
                            raw,
                            roi,
                            inferenceRoi,
                            roiFingerprint,
                            frame,
                            false,
                            false);
                    updateCache(roiFingerprint, frame, roi, inferenceRoi, raw, false);
                    metrics.successCount++;
                    metrics.ocrMs.add(msSince(totalStarted));
                    return resolved;
                } catch (VisionFailure first) {
                    if (!ERR_NOT_FOUND.equals(first.code)) {
                        updateCache(roiFingerprint, frame, roi, inferenceRoi, raw, false);
                        throw first;
                    }
                }

                Rect expanded = expandInferenceContext(
                        roi,
                        frame.width,
                        frame.height,
                        MIN_INFERENCE_CONTEXT_HEIGHT_PX);
                if (expanded.equals(roi)) {
                    updateCache(roiFingerprint, frame, roi, inferenceRoi, raw, false);
                    throw new VisionFailure(ERR_NOT_FOUND,
                            "OCR found no eligible target inside request ROI");
                }

                metrics.contextRetryCount++;
                JSONObject retryRaw = invokeRuntimeOnRoi(frame.bitmap, expanded, deadlineNs);
                updateCache(roiFingerprint, frame, roi, expanded, retryRaw, true);
                Resolved resolved = select(
                        spec,
                        retryRaw,
                        roi,
                        expanded,
                        roiFingerprint,
                        frame,
                        false,
                        true);
                metrics.successCount++;
                metrics.ocrMs.add(msSince(totalStarted));
                return resolved;
            } finally {
                if (frame != null) frame.close();
            }
        } catch (VisionFailure e) {
            metrics.failureCount++;
            if (ERR_TIMEOUT.equals(e.code)) metrics.timeoutCount++;
            if (ERR_AMBIGUOUS.equals(e.code)) metrics.ambiguousCount++;
            if (VisionV0Harness.ERR_STALE_TARGET.equals(e.code)) metrics.staleTargetCount++;
            if (VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code)) metrics.rotationMismatchCount++;
            metrics.ocrMs.add(msSince(totalStarted));
            throw e;
        }
    }

    public void validatePreAction(Resolved resolved) throws VisionFailure {
        VisionV0Harness.Frame current = null;
        try {
            current = VisionV0Harness.capture(instrumentation, device, null, 0L);
            if (resolved.frameRotation != current.rotation ||
                    resolved.frameWidth != current.width ||
                    resolved.frameHeight != current.height) {
                throw new VisionFailure(VisionV0Harness.ERR_ROTATION_MISMATCH,
                        "OCR target frame geometry changed before action");
            }
            long currentFingerprint = VisionV0Harness.fingerprintRegion(current.bitmap, resolved.roi);
            if (currentFingerprint != resolved.roiFingerprint) {
                throw new VisionFailure(VisionV0Harness.ERR_STALE_TARGET,
                        "OCR effective ROI fingerprint changed before action");
            }
            if (resolved.centerX < 0 || resolved.centerY < 0 ||
                    resolved.centerX >= current.width || resolved.centerY >= current.height) {
                throw new VisionFailure(VisionV0Harness.ERR_STALE_TARGET,
                        "OCR target center outside current screen");
            }
        } catch (VisionFailure e) {
            if (VisionV0Harness.ERR_STALE_TARGET.equals(e.code)) metrics.staleTargetCount++;
            if (VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code)) metrics.rotationMismatchCount++;
            throw e;
        } finally {
            if (current != null) current.close();
        }
    }

    public JSONObject runtimeStatus() {
        try {
            Context target = instrumentation.getTargetContext();
            ClassLoader loader = target.getClassLoader();
            Class<?> bridge = Class.forName(
                    "com.stanley.y700automation.OcrRuntimeBridge", true, loader);
            Method status = bridge.getMethod("statusJson");
            return new JSONObject(String.valueOf(status.invoke(null)));
        } catch (Throwable t) {
            return new JSONObject();
        }
    }


    private JSONObject invokeRuntimeOnRoi(
            Bitmap frameBitmap,
            Rect inferenceRoi,
            long deadlineNs) throws VisionFailure {
        long remainingMs =
                (deadlineNs - SystemClock.elapsedRealtimeNanos()) / 1_000_000L;
        if (remainingMs <= 0L) {
            throw new VisionFailure(ERR_TIMEOUT,
                    "OCR request deadline exhausted before inference");
        }
        Bitmap crop = Bitmap.createBitmap(
                frameBitmap,
                inferenceRoi.left,
                inferenceRoi.top,
                inferenceRoi.width(),
                inferenceRoi.height());
        try {
            return invokeRuntime(crop, remainingMs);
        } finally {
            crop.recycle();
        }
    }

    private void updateCache(
            long roiFingerprint,
            VisionV0Harness.Frame frame,
            Rect roi,
            Rect inferenceRoi,
            JSONObject raw,
            boolean contextRetry) throws Exception {
        cachedFingerprint = roiFingerprint;
        cachedRotation = frame.rotation;
        cachedWidth = frame.width;
        cachedHeight = frame.height;
        cachedRoi = new Rect(roi);
        cachedInferenceRoi = new Rect(inferenceRoi);
        cachedContextRetry = contextRetry;
        cachedOcr = new JSONObject(raw.toString());
    }

    private JSONObject invokeRuntime(Bitmap crop, long timeoutMs) throws VisionFailure {
        try {
            Context target = instrumentation.getTargetContext();
            ClassLoader loader = target.getClassLoader();
            Class<?> bridge = Class.forName(
                    "com.stanley.y700automation.OcrRuntimeBridge", true, loader);
            Method recognize = bridge.getMethod(
                    "recognize", Context.class, Bitmap.class, long.class);
            Object out = recognize.invoke(null, target, crop, timeoutMs);
            return new JSONObject(String.valueOf(out));
        } catch (InvocationTargetException e) {
            Throwable root = rootCause(e);
            if (root.getClass().getSimpleName().contains("OcrTimeoutException")) {
                throw new VisionFailure(ERR_TIMEOUT, safeMessage(root));
            }
            throw new VisionFailure(ERR_MODEL,
                    "OCR runtime failed: " + root.getClass().getSimpleName() +
                            ":" + safeMessage(root));
        } catch (Throwable t) {
            Throwable root = rootCause(t);
            throw new VisionFailure(ERR_MODEL,
                    "OCR runtime unavailable: " + root.getClass().getSimpleName() +
                            ":" + safeMessage(root));
        }
    }

    private Resolved select(
            JSONObject spec,
            JSONObject raw,
            Rect roi,
            Rect inferenceRoi,
            long fingerprint,
            VisionV0Harness.Frame frame,
            boolean cacheHit,
            boolean contextRetry) throws Exception {
        String pattern = spec.getString("pattern");
        String match = spec.optString("match", "substring");
        double minConfidence = spec.optDouble("min_confidence", DEFAULT_MIN_CONFIDENCE);
        Pattern regex = "regex".equals(match) ? safeCompile(pattern) : null;
        String normalizedPattern = normalize(pattern);

        JSONArray items = raw.optJSONArray("items");
        List<OcrCandidate> matches = new ArrayList<>();
        int lowConfidence = 0;
        if (items != null) {
            for (int i = 0; i < items.length(); i++) {
                JSONObject item = items.optJSONObject(i);
                if (item == null) continue;
                String text = item.optString("text", "");
                if (text.length() > MAX_REGEX_INPUT_LENGTH) continue;
                boolean textMatch;
                if (regex != null) {
                    textMatch = regex.matcher(text.replaceAll("\\s+", "")).find();
                } else {
                    textMatch = normalize(text).contains(normalizedPattern);
                }
                if (!textMatch) continue;
                double confidence = item.optDouble("confidence", Double.NaN);
                if (!Double.isFinite(confidence) || confidence < minConfidence) {
                    lowConfidence++;
                    continue;
                }

                JSONArray localBox = item.optJSONArray("bbox");
                if (localBox == null || localBox.length() < 4) continue;
                Rect bbox = new Rect(
                        localBox.optInt(0) + inferenceRoi.left,
                        localBox.optInt(1) + inferenceRoi.top,
                        localBox.optInt(2) + inferenceRoi.left,
                        localBox.optInt(3) + inferenceRoi.top);
                if (bbox.width() <= 0 || bbox.height() <= 0) continue;
                if (bbox.left < roi.left || bbox.top < roi.top ||
                        bbox.right > roi.right || bbox.bottom > roi.bottom) {
                    // Context outside the request ROI is inference-only and must
                    // never widen the acceptance/click region.
                    continue;
                }
                matches.add(new OcrCandidate(item, bbox));
            }
        }
        metrics.lowConfidenceRejectedCount += lowConfidence;

        if (matches.isEmpty()) {
            throw new VisionFailure(ERR_NOT_FOUND,
                    "OCR found no text target above min_confidence inside request ROI");
        }
        if (matches.size() > 1) {
            throw new VisionFailure(ERR_AMBIGUOUS,
                    "OCR pattern matched " + matches.size() + " eligible targets");
        }

        OcrCandidate candidate = matches.get(0);
        JSONObject item = candidate.item;
        Rect bbox = candidate.bbox;

        JSONArray globalPolygon = new JSONArray();
        JSONArray localPolygon = item.optJSONArray("polygon");
        if (localPolygon != null) {
            for (int i = 0; i < localPolygon.length(); i++) {
                JSONArray p = localPolygon.optJSONArray(i);
                if (p == null || p.length() < 2) continue;
                globalPolygon.put(new JSONArray()
                        .put(p.optDouble(0) + inferenceRoi.left)
                        .put(p.optDouble(1) + inferenceRoi.top));
            }
        }

        double confidence = item.getDouble("confidence");
        JSONObject metadata = new JSONObject()
                .put("text", item.optString("text", ""))
                .put("confidence", confidence)
                .put("polygon", globalPolygon)
                .put("bbox", rectJson(bbox))
                .put("center", new JSONArray().put(bbox.centerX()).put(bbox.centerY()))
                .put("source", "vision_text")
                .put("locator_type", "vision_text")
                .put("roi", rectJson(roi))
                .put("roi_fingerprint", Long.toUnsignedString(fingerprint))
                .put("frame_width", frame.width)
                .put("frame_height", frame.height)
                .put("display_rotation", frame.rotation)
                .put("package", frame.packageName == null ? JSONObject.NULL : frame.packageName)
                .put("source_context", new JSONObject()
                        .put("runtime", raw.optString("runtime", ""))
                        .put("match", match)
                        .put("cache_hit", cacheHit)
                        .put("context_retry", contextRetry)
                        .put("inference_roi", rectJson(inferenceRoi))
                        .put("min_inference_context_height_px", MIN_INFERENCE_CONTEXT_HEIGHT_PX)
                        .put("ocr_latency_ms", raw.optDouble("latency_ms", Double.NaN)));
        return new Resolved(bbox, confidence, metadata, roi, fingerprint, frame);
    }

    private static void validateRegex(String pattern) throws VisionFailure {
        if (pattern.length() > MAX_PATTERN_LENGTH || pattern.isEmpty()) {
            throw new VisionFailure(ERR_INVALID_PATTERN, "regex length invalid");
        }
        // Conservative linear-ish subset: no grouping, lookaround, alternation,
        // backreferences, counted repetition, or repeated wildcard chains.
        if (pattern.indexOf('(') >= 0 || pattern.indexOf(')') >= 0 ||
                pattern.indexOf('|') >= 0 || pattern.indexOf('{') >= 0 ||
                pattern.indexOf('}') >= 0 || pattern.contains("(?") ||
                pattern.matches(".*\\\\[1-9].*") || pattern.contains(".*.*")) {
            throw new VisionFailure(ERR_INVALID_PATTERN,
                    "regex uses unsupported/backtracking-heavy constructs");
        }
        if (pattern.matches(".*([+*?])\\1.*")) {
            throw new VisionFailure(ERR_INVALID_PATTERN, "repeated regex quantifier rejected");
        }
        safeCompile(pattern);
    }

    private static Pattern safeCompile(String pattern) throws VisionFailure {
        try {
            return Pattern.compile(pattern, Pattern.CASE_INSENSITIVE | Pattern.UNICODE_CASE);
        } catch (PatternSyntaxException e) {
            throw new VisionFailure(ERR_INVALID_PATTERN, "invalid regex syntax");
        }
    }

    static Rect expandInferenceContext(
            Rect roi,
            int frameWidth,
            int frameHeight,
            int minHeightPx) {
        Rect out = new Rect(roi);
        int targetHeight = Math.min(Math.max(1, minHeightPx), frameHeight);
        if (out.height() < targetHeight) {
            int extra = targetHeight - out.height();
            out.top -= extra / 2;
            out.bottom += extra - extra / 2;
        }
        if (out.top < 0) {
            out.bottom = Math.min(frameHeight, out.bottom - out.top);
            out.top = 0;
        }
        if (out.bottom > frameHeight) {
            int overflow = out.bottom - frameHeight;
            out.top = Math.max(0, out.top - overflow);
            out.bottom = frameHeight;
        }
        out.left = Math.max(0, out.left);
        out.right = Math.min(frameWidth, out.right);
        return out;
    }

    static String normalize(String text) {
        if (text == null || text.isEmpty()) return "";
        String compact = text.replaceAll("\\s+", "");
        StringBuilder out = new StringBuilder(compact.length());
        for (int offset = 0; offset < compact.length();) {
            int cp = compact.codePointAt(offset);
            int chars = Character.charCount(cp);
            if (isIgnorableHanSeparator(cp)) {
                int prev = previousCodePoint(compact, offset);
                int nextOffset = offset + chars;
                int next = nextOffset < compact.length()
                        ? compact.codePointAt(nextOffset)
                        : -1;
                if (isHan(prev) && isHan(next)) {
                    offset += chars;
                    continue;
                }
            }
            out.appendCodePoint(Character.toLowerCase(cp));
            offset += chars;
        }
        return out.toString();
    }

    private static boolean isIgnorableHanSeparator(int cp) {
        return cp == '|' || cp == 0xFF5C || cp == 0x00A6;
    }

    private static int previousCodePoint(String text, int offset) {
        return offset <= 0 ? -1 : text.codePointBefore(offset);
    }

    private static boolean isHan(int cp) {
        if (cp < 0) return false;
        Character.UnicodeScript script = Character.UnicodeScript.of(cp);
        return script == Character.UnicodeScript.HAN;
    }

    private static int[] intArray(JSONArray a) {
        if (a == null) return null;
        int[] out = new int[a.length()];
        for (int i = 0; i < out.length; i++) out[i] = a.optInt(i);
        return out;
    }

    private static double[] doubleArray(JSONArray a) {
        if (a == null) return null;
        double[] out = new double[a.length()];
        for (int i = 0; i < out.length; i++) out[i] = a.optDouble(i, Double.NaN);
        return out;
    }

    private static JSONArray rectJson(Rect r) {
        return new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom);
    }

    private static Throwable rootCause(Throwable t) {
        Throwable root = t;
        while (root.getCause() != null && root.getCause() != root) root = root.getCause();
        return root;
    }

    private static String safeMessage(Throwable t) {
        String message = t.getMessage();
        if (message == null || message.trim().isEmpty()) return "no message";
        message = message.replace('\n', ' ').replace('\r', ' ').trim();
        return message.length() > 240 ? message.substring(0, 240) : message;
    }

    private static double msSince(long startedNs) {
        return (SystemClock.elapsedRealtimeNanos() - startedNs) / 1_000_000.0;
    }
}
