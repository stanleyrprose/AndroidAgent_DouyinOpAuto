package com.stanley.y700automation.vision;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Rev3.7 D-G3 candidate Android JIT comparison, pure, no input injection.
 *
 * A real dispatch check must populate CURRENT independently from Android
 * driver / state SOT at the mutation boundary. The fixture-only entrypoint
 * here DOES NOT mint authority, perform an action, relax a route's age limit,
 * or claim that the live Android observer has been integrated.
 *
 * Production mutation stays hard-closed independently in
 * AutomationInstrumentedTest.interactiveVisionMutationRequiresDg3.
 */
public final class Rev37JitFrameGuard {
    public static final String CLOSED = "VISION_DRIVER_GATE_CLOSED";
    public static final String UNAVAILABLE = "FRAME_UNAVAILABLE";
    public static final String STALE = "FRAME_STALE";
    public static final String BOOT_MISMATCH = "FRAME_BOOT_MISMATCH";
    public static final String REVISION_STALE = "FRAME_REVISION_STALE";
    public static final String DISPLAY_CHANGED = "FRAME_DISPLAY_CHANGED";
    public static final String ROTATION_CHANGED = "FRAME_ROTATION_CHANGED";
    public static final String FOREGROUND_DRIFT = "FRAME_FOREGROUND_DRIFT";
    public static final String LOCATOR_MISMATCH = "LOCATOR_FRAME_MISMATCH";
    public static final String LOCATOR_AMBIGUOUS = "LOCATOR_AMBIGUOUS";
    public static final String READ_ONLY_MATCH = "READ_ONLY_JIT_MATCH";

    private Rev37JitFrameGuard() {}

    public static final class Verdict {
        public final String code;
        public final long ageMs;
        private Verdict(String code, long ageMs) {
            this.code = code;
            this.ageMs = ageMs;
        }
        public boolean readOnlyMatched() {
            return READ_ONLY_MATCH.equals(code);
        }
        public JSONObject json() throws Exception {
            return new JSONObject()
                    .put("verdict", code)
                    .put("frame_age_at_hypothetical_dispatch_ms", ageMs)
                    .put("production_dispatch_authorized", false)
                    .put("dg3_status", "OPEN")
                    .put("ui_mutation_attempts", 0);
        }
    }

    private static Verdict denied(String code) {
        return new Verdict(code, -1);
    }

    /**
     * Deliberate mandatory production hard-stop. There is no user-/workflow-
     * controlled boolean, fixture signal, or open-by-configuration parameter.
     */
    public static Verdict verifyForProductionDispatch(
            JSONObject frame, JSONObject locator, JSONObject current) {
        return denied(CLOSED);
    }

    /**
     * The route contract here is test-only and FIXED at construction; in a
     * production adapter a versioned calibrated route SOT is required. This
     * method is package-private to prevent it from being a public dispatch
     * API. Passing it never authorizes clicks.
     */
    static Verdict compareFixtureReadOnly(
            JSONObject frame, JSONObject locator, JSONObject independentlyObserved,
            String expectedLocatorVersion, int fixtureMaxFrameAgeMs, long nowBootMs) {
        if (frame == null || locator == null || independentlyObserved == null
                || expectedLocatorVersion == null || expectedLocatorVersion.isEmpty()
                || fixtureMaxFrameAgeMs <= 0 || fixtureMaxFrameAgeMs > 10000 || nowBootMs < 0) {
            return denied(UNAVAILABLE);
        }
        // Every required field must be present with a valid type. optInt or
        // optLong alone would silently turn absent/corrupt fields into zeros.
        if (!integer(frame, "frame_token_version", 1) ||
                !string(frame, "frame_id", "frame-") ||
                !oneOf(frame, "source", "SCREENSHOT", "STREAM", "CAPTURE_API") ||
                !string(frame, "observed_boot_id", null) ||
                !string(frame, "state_epoch", null) ||
                !nonNegativeInt(frame, "revision") ||
                !nonNegativeLong(frame, "captured_boottime_ms") ||
                !nonNegativeInt(frame, "display_id") ||
                !intRange(frame, "rotation", 0, 3) ||
                !positiveInt(frame, "width") || !positiveInt(frame, "height") ||
                !integer(frame, "max_age_ms", fixtureMaxFrameAgeMs) ||
                !validForeground(frame.optJSONObject("foreground"))) {
            return denied(UNAVAILABLE);
        }
        String frameId = frame.optString("frame_id", "");
        if (!frameId.equals(locator.optString("frame_id", ""))
                || !expectedLocatorVersion.equals(locator.optString("locator_contract_version", ""))) {
            return denied(LOCATOR_MISMATCH);
        }
        if (!string(locator, "target_identity", null)
                || !isBoolean(locator, "ambiguous", false)) {
            return denied(LOCATOR_AMBIGUOUS);
        }
        JSONArray bounds = locator.optJSONArray("bounds");
        if (bounds == null || bounds.length() != 4
                || !boundsWithin(bounds, frame.optInt("width"), frame.optInt("height"))) {
            return denied(LOCATOR_AMBIGUOUS);
        }
        if (!string(independentlyObserved, "boot_id", null)
                || !frame.optString("observed_boot_id").equals(
                independentlyObserved.optString("boot_id", ""))) {
            return denied(BOOT_MISMATCH);
        }
        if (!string(independentlyObserved, "state_epoch", null)
                || !frame.optString("state_epoch").equals(
                independentlyObserved.optString("state_epoch", ""))) {
            return denied(STALE);
        }
        if (!nonNegativeInt(independentlyObserved, "revision")
                || frame.optInt("revision") != independentlyObserved.optInt("revision")) {
            return denied(REVISION_STALE);
        }
        if (!nonNegativeInt(independentlyObserved, "display_id")
                || !positiveInt(independentlyObserved, "width")
                || !positiveInt(independentlyObserved, "height")
                || frame.optInt("display_id") != independentlyObserved.optInt("display_id")
                || frame.optInt("width") != independentlyObserved.optInt("width")
                || frame.optInt("height") != independentlyObserved.optInt("height")) {
            return denied(DISPLAY_CHANGED);
        }
        if (!intRange(independentlyObserved, "rotation", 0, 3)
                || frame.optInt("rotation") != independentlyObserved.optInt("rotation")) {
            return denied(ROTATION_CHANGED);
        }
        JSONObject expectedForeground = frame.optJSONObject("foreground");
        JSONObject currentForeground = independentlyObserved.optJSONObject("foreground");
        if (!validForeground(currentForeground)
                || !expectedForeground.optString("package").equals(
                currentForeground.optString("package", ""))
                || !expectedForeground.optString("activity").equals(
                currentForeground.optString("activity", ""))) {
            return denied(FOREGROUND_DRIFT);
        }
        if (!isBoolean(independentlyObserved, "screen_interactive", true)
                || !isBoolean(independentlyObserved, "keyguard_locked", false)
                || !isBoolean(independentlyObserved, "blocking_overlay_present", false)) {
            return denied(STALE);
        }
        long captured = frame.optLong("captured_boottime_ms", -1);
        if (nowBootMs < captured || nowBootMs - captured > fixtureMaxFrameAgeMs) {
            return denied(STALE);
        }
        return new Verdict(READ_ONLY_MATCH, nowBootMs - captured);
    }

    private static boolean validForeground(JSONObject foreground) {
        return foreground != null && string(foreground, "package", null)
                && string(foreground, "activity", null);
    }
    private static boolean exists(JSONObject value, String key) {
        return value.has(key) && !value.isNull(key);
    }
    private static boolean integer(JSONObject value, String key, int expected) {
        return exists(value, key) && value.opt(key) instanceof Integer
                && value.optInt(key) == expected;
    }
    private static boolean nonNegativeInt(JSONObject value, String key) {
        return exists(value, key) && value.opt(key) instanceof Integer
                && value.optInt(key) >= 0;
    }
    private static boolean positiveInt(JSONObject value, String key) {
        return nonNegativeInt(value, key) && value.optInt(key) > 0;
    }
    private static boolean intRange(JSONObject value, String key, int low, int high) {
        return nonNegativeInt(value, key)
                && value.optInt(key) >= low && value.optInt(key) <= high;
    }
    private static boolean nonNegativeLong(JSONObject value, String key) {
        return exists(value, key) &&
                (value.opt(key) instanceof Long || value.opt(key) instanceof Integer)
                && value.optLong(key) >= 0;
    }
    private static boolean isBoolean(JSONObject value, String key, boolean expected) {
        return exists(value, key) && value.opt(key) instanceof Boolean
                && value.optBoolean(key) == expected;
    }
    private static boolean string(JSONObject value, String key, String prefix) {
        if (!exists(value, key) || !(value.opt(key) instanceof String)) return false;
        String s = value.optString(key, "");
        return !s.isEmpty() && (prefix == null || s.startsWith(prefix));
    }
    private static boolean oneOf(JSONObject value, String key, String a, String b, String c) {
        return string(value, key, null) && (a.equals(value.optString(key))
                || b.equals(value.optString(key)) || c.equals(value.optString(key)));
    }
    private static boolean boundsWithin(JSONArray bounds, int width, int height) {
        try {
            for (int i = 0; i < 4; i++) {
                if (!(bounds.get(i) instanceof Integer)) return false;
            }
            int x0 = bounds.getInt(0), y0 = bounds.getInt(1);
            int x1 = bounds.getInt(2), y1 = bounds.getInt(3);
            return x0 >= 0 && y0 >= 0 && x0 < x1 && x1 <= width
                    && y0 < y1 && y1 <= height;
        } catch (Exception failure) {
            return false;
        }
    }
}
