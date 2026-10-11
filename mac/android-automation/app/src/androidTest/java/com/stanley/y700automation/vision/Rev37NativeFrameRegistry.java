package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;

import java.security.SecureRandom;
import java.util.Arrays;

/**
 * Rev3.7 native in-process frame/locator provenance.
 *
 * A caller-supplied frame_id is NEVER evidence of a real screenshot.
 * Only this class can mint a short-lived native FrameToken after a real
 * UiAutomation screenshot and independently observed native state.
 * It retains an IN-MEMORY one-shot anchor, not pixels, files or coordinates
 * from the request. A matching visual locator must be registered from
 * the same VisionV0Harness.Frame while it is still open.
 *
 * It is a source-development candidate; native modal/window contracts
 * and max-frame-age calibration remain unaccepted, and ALL mutation
 * dispatch stays behind independent static D-G3 release guards.
 */
public final class Rev37NativeFrameRegistry {
    private static final SecureRandom RANDOM = new SecureRandom();
    private static final Object LOCK = new Object();
    private static final String ROUTE = "tiktok.create.observe.v1";
    private static final String LOCATOR = "tiktok-create-target.v1";
    private static final String PACKAGE = "com.zhiliaoapp.musically";
    // The immutable Create template has ONE source-owned acceptance
    // contract in Rev37NativeTemplateRoute. The registry cannot be
    // separately enabled by another boolean or caller threshold.
    private static final double MIN_SCORE = 0.90;
    private static final double MIN_MARGIN = 0.10;
    private static String nonce;
    private static long generation;
    private static long fingerprint;
    private static long issuedAt;
    private static String locatorNonce;
    private static int[] locatorBounds;
    private static JSONObject issuerSnapshot;
    private static boolean consumed = true;

    private Rev37NativeFrameRegistry() {}

    private static String newNonce() {
        byte[] data = new byte[24];
        RANDOM.nextBytes(data);
        StringBuilder builder = new StringBuilder("frame-");
        for (byte part : data) {
            builder.append(Character.forDigit((part >>> 4) & 15, 16))
                   .append(Character.forDigit(part & 15, 16));
        }
        return builder.toString();
    }

    public static void invalidate() {
        synchronized (LOCK) {
            consumed = true;
            nonce = null;
            locatorNonce = null;
            locatorBounds = null;
            issuerSnapshot = null;
            generation = -1;
            fingerprint = -1;
            issuedAt = -1;
        }
    }

    /**
     * Read-only capture with independently checked boot/epoch/foreground.
     * No screenshot bytes escape this process. Frame must be closed by
     * caller after optional independent template match.
     */
    public static final class IssuedFrame implements AutoCloseable {
        public final VisionV0Harness.Frame frame;
        public final JSONObject token;
        private boolean closed;
        private IssuedFrame(VisionV0Harness.Frame frame, JSONObject token) {
            this.frame = frame;
            this.token = token;
        }
        @Override public void close() {
            if (!closed) {
                closed = true;
                // Never leave a one-use native screenshot authorization in
                // the registry after its pixel frame has been recycled.
                synchronized (LOCK) {
                    if (nonce != null
                            && nonce.equals(token.optString("frame_id")))
                        invalidate();
                }
                frame.close();
            }
        }
    }

    public static IssuedFrame captureReadOnly(
            Instrumentation instrumentation, UiDevice device,
            Rect routeBounds) throws Exception {
        invalidate();
        if (instrumentation == null || device == null || routeBounds == null)
            throw new IllegalStateException("FRAME_UNAVAILABLE");
        // Until accepted modal and window observers are installed, this
        // rejects BEFORE capture or token issuance, not after dispatch.
        Rev37NativeStateObserver.Observation before =
                Rev37NativeStateObserver.observe(
                        instrumentation, device, PACKAGE, routeBounds, ROUTE);
        if (!before.available())
            throw new IllegalStateException(before.reason);
        VisionV0Harness.Frame frame = VisionV0Harness.capture(
                instrumentation, device, null, 0L);
        boolean retained = false;
        try {
            Rev37NativeStateObserver.Observation after =
                    Rev37NativeStateObserver.observe(
                            instrumentation, device, PACKAGE,
                            routeBounds, ROUTE);
            if (!after.available())
                throw new IllegalStateException(after.reason);
            JSONObject a = before.current, b = after.current;
            for (String key : new String[]{
                    "boot_id", "state_epoch", "revision", "display_id",
                    "rotation", "width", "height"}) {
                if (!a.get(key).equals(b.get(key)))
                    throw new IllegalStateException("FRAME_STATE_DRIFT");
            }
            if (!a.getJSONObject("foreground").getString("package")
                    .equals(b.getJSONObject("foreground").getString("package"))
                    || !a.getJSONObject("foreground").getString("activity")
                    .equals(b.getJSONObject("foreground").getString("activity")))
                throw new IllegalStateException("FRAME_FOREGROUND_DRIFT");
            if (frame.width != b.getInt("width")
                    || frame.height != b.getInt("height")
                    || frame.rotation != b.getInt("rotation"))
                throw new IllegalStateException("FRAME_GEOMETRY_DRIFT");

            String id = newNonce();
            JSONObject token = new JSONObject()
                    .put("frame_token_version", 1)
                    .put("source", "SCREENSHOT")
                    .put("frame_id", id)
                    .put("route_contract_id", ROUTE)
                    .put("foreground_package", PACKAGE)
                    .put("foreground", b.getJSONObject("foreground"))
                    .put("observed_boot_id", b.getString("boot_id"))
                    .put("state_epoch", b.getString("state_epoch"))
                    .put("revision", b.getInt("revision"))
                    .put("display_id", b.getInt("display_id"))
                    .put("rotation", frame.rotation)
                    .put("width", frame.width).put("height", frame.height)
                    .put("captured_boottime_ms", frame.capturedAtNs / 1000000L);
            synchronized (LOCK) {
                nonce = id;
                generation = frame.generation;
                fingerprint = frame.fingerprint;
                issuedAt = frame.capturedAtNs / 1000000L;
                issuerSnapshot = new JSONObject(token.toString());
                consumed = false;
            }
            retained = true;
            return new IssuedFrame(frame, token);
        } finally {
            if (!retained) {
                frame.close();
                invalidate();
            }
        }
    }

    /**
     * Bind a VisionV0Harness match obtained from the exact captured frame.
     * Confidence/ambiguity acceptance is separate and MUST NOT be inferred
     * from this identity check.
     */
    public static JSONObject bindMatchedLocator(
            IssuedFrame issued, VisionV0Harness.VisionTarget match)
            throws Exception {
        if (issued == null || issued.closed || match == null
                || issued.frame.bitmap.isRecycled()
                || !"vision_template".equals(match.source)
                || !Rev37NativeTemplateRoute.templateContractAccepted()
                || !Double.isFinite(match.confidence)
                || !Double.isFinite(match.secondBest)
                || match.confidence < MIN_SCORE
                || match.confidence - match.secondBest < MIN_MARGIN)
            throw new IllegalStateException("LOCATOR_UNVERIFIED");
        int[] bounds = {match.bbox.left, match.bbox.top,
                match.bbox.right, match.bbox.bottom};
        synchronized (LOCK) {
            if (consumed || nonce == null || issuerSnapshot == null
                    || !nonce.equals(issued.token.optString("frame_id"))
                    || match.frameGeneration != generation
                    || match.frameFingerprint != fingerprint
                    || match.frameWidth != issued.frame.width
                    || match.frameHeight != issued.frame.height
                    || match.rotation != issued.frame.rotation
                    || bounds[0] < 0 || bounds[1] < 0
                    || bounds[2] > issued.frame.width
                    || bounds[3] > issued.frame.height
                    || bounds[0] >= bounds[2] || bounds[1] >= bounds[3])
                throw new IllegalStateException("LOCATOR_FRAME_MISMATCH");
            locatorNonce = nonce;
            locatorBounds = bounds.clone();
            return new JSONObject()
                    .put("frame_id", nonce)
                    .put("locator_contract_version", LOCATOR)
                    .put("ambiguous", false)
                    .put("bounds", new JSONArray(Arrays.asList(
                            bounds[0], bounds[1], bounds[2], bounds[3])))
                    .put("source", "NATIVE_VISION_TEMPLATE");
        }
    }

    private static boolean immutableSnapshotEquals(JSONObject saved,
                                                    JSONObject supplied) {
        if (saved == null || supplied == null
                || saved.length() != supplied.length()) return false;
        try {
            for (String name : new String[]{"frame_token_version", "source",
                    "frame_id", "route_contract_id", "foreground_package",
                    "observed_boot_id", "state_epoch", "revision",
                    "display_id", "rotation", "width", "height",
                    "captured_boottime_ms"}) {
                if (!saved.has(name) || !supplied.has(name)
                        || !saved.get(name).equals(supplied.get(name)))
                    return false;
            }
            JSONObject oldFg = saved.getJSONObject("foreground");
            JSONObject newFg = supplied.getJSONObject("foreground");
            return oldFg.length() == 2 && newFg.length() == 2
                    && oldFg.get("package").equals(newFg.get("package"))
                    && oldFg.get("activity").equals(newFg.get("activity"));
        } catch (Exception ignored) {
            return false;
        }
    }

    /**
     * Mutating dispatch compares AND CONSUMES this one-shot native record.
     * Caller JSON alone can never populate the registry or mint new proof.
     * A failed comparison also invalidates it to block brute-force retries.
     */
    public static boolean consumeExactNativeProof(
            JSONObject frameToken, JSONObject locator) {
        synchronized (LOCK) {
            boolean match = false;
            if (!consumed && nonce != null && issuerSnapshot != null
                    && locatorBounds != null && locatorNonce != null
                    && frameToken != null && locator != null) {
                JSONArray area = locator.optJSONArray("bounds");
                if (area != null && area.length() == 4) {
                    match = nonce.equals(frameToken.optString("frame_id"))
                            && nonce.equals(locator.optString("frame_id"))
                            && locatorNonce.equals(nonce)
                            && issuedAt == frameToken.optLong(
                                    "captured_boottime_ms", -1L)
                            && immutableSnapshotEquals(issuerSnapshot, frameToken)
                            && "NATIVE_VISION_TEMPLATE".equals(
                                    locator.optString("source"))
                            && locatorBounds[0] == area.optInt(0, -1)
                            && locatorBounds[1] == area.optInt(1, -1)
                            && locatorBounds[2] == area.optInt(2, -1)
                            && locatorBounds[3] == area.optInt(3, -1)
                            && SystemClock.elapsedRealtimeNanos() / 1000000L
                                >= issuedAt;
                }
            }
            invalidate();
            return match;
        }
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
