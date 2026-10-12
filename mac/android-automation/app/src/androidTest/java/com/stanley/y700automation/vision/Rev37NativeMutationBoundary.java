package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Rev3.7 native mutation-time frame/locator/Android SOT observer boundary.
 *
 * Run ONLY from the actual Android Driver dispatch call site, never from a
 * detached host preflight. This implementation compares independently
 * observed Android fields against one exact captured FrameToken.
 *
 * No visual route has an empirically accepted device-specific JIT age and
 * the modal/window contracts are not accepted; D-G3 remains closed. This
 * class NEVER performs any UI input, wakes/unlocks device, or emits pixels.
 *
 * UNCOMPILED DEVELOPMENT SOURCE — no production authorization.
 */
public final class Rev37NativeMutationBoundary {
    private static final boolean DG3_ACCEPTED = false;
    private static final String TIKTOK_PACKAGE = "com.zhiliaoapp.musically";
    private static final String TIKTOK_CONTRACT = "tiktok.create.observe.v1";
    private static final String TIKTOK_LOCATOR = "tiktok-create-target.v1";
    private static final int NO_ACCEPTED_ROUTE_AGE = -1;

    private Rev37NativeMutationBoundary() {}

    public static final class Verdict {
        public final String code;
        public final long frameAgeMs;
        public final Rect acceptedTargetBounds;
        private Verdict(String code, long frameAgeMs, Rect bounds) {
            this.code = code;
            this.frameAgeMs = frameAgeMs;
            this.acceptedTargetBounds = bounds == null
                    ? null : new Rect(bounds);
        }
        public boolean acceptedForSingleDispatch() {
            return "NATIVE_JIT_MATCHED".equals(code)
                    && acceptedTargetBounds != null;
        }
        public JSONObject toReceipt() throws Exception {
            return new JSONObject()
                    .put("status", acceptedForSingleDispatch()
                            ? "MATCHED" : "BLOCKED")
                    .put("reason_code", code)
                    .put("frame_age_ms", frameAgeMs)
                    .put("dg3_status", "OPEN")
                    .put("production_dispatch_authorized",
                            acceptedForSingleDispatch())
                    .put("ui_mutation_attempts", 0);
        }
    }

    private static Verdict deny(String code) {
        return new Verdict(code, -1L, null);
    }

    private static boolean field(JSONObject object, String name) {
        return object != null && object.has(name) && !object.isNull(name);
    }

    private static boolean nonNegativeInteger(JSONObject object, String name) {
        return field(object, name) && object.opt(name) instanceof Integer
                && object.optInt(name) >= 0;
    }

    private static boolean equalsString(JSONObject a, JSONObject b,
                                        String aField, String bField) {
        return field(a, aField) && field(b, bField)
                && a.opt(aField) instanceof String
                && b.opt(bField) instanceof String
                && a.optString(aField).equals(b.optString(bField));
    }

    private static Rect unambiguousBounds(JSONObject locator,
                                           int width, int height) {
        if (!field(locator, "ambiguous")
                || !(locator.opt("ambiguous") instanceof Boolean)
                || locator.optBoolean("ambiguous", true))
            return null;
        JSONArray bounds = locator.optJSONArray("bounds");
        if (bounds == null || bounds.length() != 4)
            return null;
        for (int i = 0; i < 4; ++i) {
            try {
                if (!(bounds.get(i) instanceof Integer)) return null;
            } catch (Exception ignored) {
                return null;
            }
        }
        int l = bounds.optInt(0, -1), t = bounds.optInt(1, -1);
        int r = bounds.optInt(2, -1), b = bounds.optInt(3, -1);
        if (!(0 <= l && l < r && r <= width &&
                0 <= t && t < b && b <= height))
            return null;
        return new Rect(l, t, r, b);
    }

    /**
     * FrameToken must have been minted by the device screenshot observer,
     * with locator produced FROM exactly that frame. A JSON object from a
     * workflow/caller is NOT itself FrameToken provenance.
     */
    public static Verdict compareAtNativeBoundary(
            Instrumentation instrumentation, UiDevice device,
            JSONObject frameToken, JSONObject locator) {
        if (frameToken == null || locator == null
                || instrumentation == null || device == null)
            return deny("FRAME_UNAVAILABLE");
        // Mandatory in-process native screenshot identity, consumed once.
        // This cannot be synthesized by a request containing matching
        // frame_id/locator JSON; no registered native frame => zero input.
        if (!Rev37NativeFrameRegistry.consumeExactNativeProof(
                frameToken, locator))
            return deny("FRAME_NATIVE_PROVENANCE_UNAVAILABLE");
        if (frameToken.optInt("frame_token_version", -1) != 1
                || !"SCREENSHOT".equals(frameToken.optString("source"))
                || !equalsString(frameToken, locator, "frame_id", "frame_id"))
            return deny("LOCATOR_FRAME_MISMATCH");

        String route = frameToken.optString("route_contract_id", "");
        if (!TIKTOK_CONTRACT.equals(route)
                || !TIKTOK_LOCATOR.equals(
                        locator.optString("locator_contract_version", ""))
                || !TIKTOK_PACKAGE.equals(
                        frameToken.optString("foreground_package", "")))
            return deny("RUNTIME_CONTRACT_MISMATCH");

        int width = frameToken.optInt("width", -1);
        int height = frameToken.optInt("height", -1);
        Rect target = unambiguousBounds(locator, width, height);
        if (target == null || !nonNegativeInteger(frameToken, "revision")
                || !nonNegativeInteger(frameToken, "display_id")
                || !nonNegativeInteger(frameToken, "rotation")
                || !field(frameToken, "captured_boottime_ms")
                || !(frameToken.opt("captured_boottime_ms") instanceof Long
                     || frameToken.opt("captured_boottime_ms") instanceof Integer))
            return deny("FRAME_EVIDENCE_INVALID");

        // The native observer does NOT accept workflow-supplied clear booleans.
        Rev37NativeStateObserver.Observation current =
                Rev37NativeStateObserver.observe(
                        instrumentation, device, TIKTOK_PACKAGE,
                        target, TIKTOK_CONTRACT);
        if (!current.available()) return deny(current.reason);

        JSONObject present = current.current;
        if (!equalsString(frameToken, present,
                "observed_boot_id", "boot_id"))
            return deny("FRAME_BOOT_MISMATCH");
        if (!equalsString(frameToken, present,
                "state_epoch", "state_epoch"))
            return deny("FRAME_STALE");
        if (frameToken.optInt("revision", -1)
                != present.optInt("revision", -2))
            return deny("FRAME_REVISION_STALE");

        for (String field : new String[]{"display_id", "rotation",
                                          "width", "height"}) {
            if (!nonNegativeInteger(present, field)
                    || frameToken.optInt(field, -1) != present.optInt(field, -2))
                return deny("FRAME_DISPLAY_CHANGED");
        }
        JSONObject foreground = present.optJSONObject("foreground");
        JSONObject oldForeground = frameToken.optJSONObject("foreground");
        if (foreground == null || oldForeground == null
                || !equalsString(oldForeground, foreground,
                        "package", "package")
                || !equalsString(oldForeground, foreground,
                        "activity", "activity"))
            return deny("FRAME_FOREGROUND_DRIFT");
        if (!present.optBoolean("screen_interactive", false)
                || present.optBoolean("keyguard_locked", true)
                || !field(present, "blocking_overlay_present")
                || present.optBoolean("blocking_overlay_present", true))
            return deny("UNEXPECTED_BLOCKING_OVERLAY");

        long nowMs = SystemClock.elapsedRealtimeNanos() / 1000000L;
        long fromMs = frameToken.optLong("captured_boottime_ms", -1L);
        if (fromMs < 0 || nowMs < fromMs)
            return deny("FRAME_STALE");
        long age = nowMs - fromMs;

        // No route has an accepted calibrated maximum age. This gate is
        // deliberately separate from a caller's max_age_ms field.
        if (NO_ACCEPTED_ROUTE_AGE <= 0 || age > NO_ACCEPTED_ROUTE_AGE)
            return deny("FRAME_AGE_UNCALIBRATED");

        // Even a fully matching read-only observation can never override
        // the independent release/Driver dispatch gate.
        if (!DG3_ACCEPTED || !Rev37NativeStateObserver.productionDispatchAuthorized()
                || !Rev37NativeModalGuard.productionDispatchAuthorized()
                || !Rev37NativeFrameRegistry.productionDispatchAuthorized()
                || !Rev37NativeAppContract.productionDispatchAuthorized())
            return deny("VISION_DRIVER_GATE_CLOSED");

        // This verdict carries the NATIVE-MATCHED bounds only inside the
        // current instrumentation process. It is not an external click
        // capability; the Driver must enforce its own independent release
        // switch and consume it exactly once in the same dispatch stack.
        return new Verdict("NATIVE_JIT_MATCHED", age, target);
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
