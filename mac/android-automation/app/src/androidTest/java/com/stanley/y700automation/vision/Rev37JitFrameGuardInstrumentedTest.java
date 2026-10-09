package com.stanley.y700automation.vision;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

/**
 * Isolated synthetic JIT guard regression. Never clicks or authorizes input.
 * All fixtures are synthetic; no production evidence/driver is made available.
 */
@RunWith(AndroidJUnit4.class)
public final class Rev37JitFrameGuardInstrumentedTest {
    private static final int LIMIT = 600;
    private static final String VERSION = "visual-target.v1";

    private static JSONObject foreground() throws Exception {
        return new JSONObject().put("package", "com.example.fixture")
                .put("activity", "FixtureActivity");
    }
    private static JSONObject frame() throws Exception {
        return new JSONObject()
                .put("frame_token_version", 1)
                .put("frame_id", "frame-jit-fixture")
                .put("source", "SCREENSHOT")
                .put("observed_boot_id", "boot-fixture")
                .put("captured_boottime_ms", 1000L)
                .put("state_epoch", "epoch-fixture")
                .put("revision", 42)
                .put("display_id", 0)
                .put("rotation", 1)
                .put("width", 1600)
                .put("height", 2560)
                .put("foreground", foreground())
                .put("max_age_ms", LIMIT);
    }
    private static JSONObject locator() throws Exception {
        return new JSONObject()
                .put("frame_id", "frame-jit-fixture")
                .put("locator_contract_version", VERSION)
                .put("target_identity", "fixture-only-control")
                .put("bounds", new JSONArray().put(100).put(200).put(400).put(350))
                .put("ambiguous", false);
    }
    private static JSONObject current() throws Exception {
        return new JSONObject()
                .put("boot_id", "boot-fixture")
                .put("state_epoch", "epoch-fixture")
                .put("revision", 42)
                .put("display_id", 0)
                .put("rotation", 1)
                .put("width", 1600)
                .put("height", 2560)
                .put("foreground", foreground())
                .put("screen_interactive", true)
                .put("keyguard_locked", false)
                .put("blocking_overlay_present", false);
    }

    private static Rev37JitFrameGuard.Verdict compare(
            JSONObject frame, JSONObject locator, JSONObject current,
            long now) {
        return Rev37JitFrameGuard.compareFixtureReadOnly(
                frame, locator, current, VERSION, LIMIT, now);
    }
    private static void reject(
            String code, JSONObject frame, JSONObject locator, JSONObject current,
            long now) throws Exception {
        Rev37JitFrameGuard.Verdict v = compare(frame, locator, current, now);
        assertEquals(code, v.code);
        assertFalse(v.readOnlyMatched());
        assertEquals(-1, v.ageMs);
        assertFalse(v.json().getBoolean("production_dispatch_authorized"));
        assertEquals(0, v.json().getInt("ui_mutation_attempts"));
        assertEquals("OPEN", v.json().getString("dg3_status"));
    }

    @Test
    public void healthyFixtureReadOnlyButProductionAlwaysBlocked() throws Exception {
        Rev37JitFrameGuard.Verdict v = compare(frame(), locator(), current(), 1450);
        assertTrue(v.readOnlyMatched());
        assertEquals(450, v.ageMs);
        assertFalse(v.json().getBoolean("production_dispatch_authorized"));
        assertEquals(0, v.json().getInt("ui_mutation_attempts"));
        Rev37JitFrameGuard.Verdict prod =
                Rev37JitFrameGuard.verifyForProductionDispatch(frame(), locator(), current());
        assertEquals(Rev37JitFrameGuard.CLOSED, prod.code);
        assertFalse(prod.json().getBoolean("production_dispatch_authorized"));
        assertEquals(0, prod.json().getInt("ui_mutation_attempts"));
    }
    @Test
    public void expiredFrameAndFutureTimestampRejected() throws Exception {
        reject(Rev37JitFrameGuard.STALE, frame(), locator(), current(), 1601);
        reject(Rev37JitFrameGuard.STALE, frame(), locator(), current(), 999);
        assertTrue(compare(frame(), locator(), current(), 1600).readOnlyMatched());
    }
    @Test
    public void frameRouteAgeCannotBeOverridden() throws Exception {
        reject(Rev37JitFrameGuard.UNAVAILABLE,
                frame().put("max_age_ms", 9000), locator(), current(), 1450);
        reject(Rev37JitFrameGuard.UNAVAILABLE,
                frame().put("max_age_ms", "600"), locator(), current(), 1450);
    }
    @Test
    public void locatorFrameMismatchAndVersionMismatch() throws Exception {
        reject(Rev37JitFrameGuard.LOCATOR_MISMATCH,
                frame(), locator().put("frame_id", "frame-old"), current(), 1450);
        reject(Rev37JitFrameGuard.LOCATOR_MISMATCH,
                frame(), locator().put("locator_contract_version", "v0"), current(), 1450);
    }
    @Test
    public void rejectAmbiguousAndOutOfFrameTarget() throws Exception {
        reject(Rev37JitFrameGuard.LOCATOR_AMBIGUOUS,
                frame(), locator().put("ambiguous", true), current(), 1450);
        reject(Rev37JitFrameGuard.LOCATOR_AMBIGUOUS,
                frame(), locator().put("ambiguous", JSONObject.NULL), current(), 1450);
        reject(Rev37JitFrameGuard.LOCATOR_AMBIGUOUS,
                frame(), locator().put("bounds", new JSONArray().put(0).put(0).put(9000).put(100)),
                current(), 1450);
    }
    @Test
    public void rejectBootMismatchEpochAndRevisionAdvance() throws Exception {
        reject(Rev37JitFrameGuard.BOOT_MISMATCH,
                frame(), locator(), current().put("boot_id", "different-boot"), 1450);
        reject(Rev37JitFrameGuard.STALE,
                frame(), locator(), current().put("state_epoch", "epoch-new"), 1450);
        reject(Rev37JitFrameGuard.REVISION_STALE,
                frame(), locator(), current().put("revision", 43), 1450);
    }
    @Test
    public void rejectRotationGeometryDisplayAndForegroundDrift() throws Exception {
        reject(Rev37JitFrameGuard.ROTATION_CHANGED,
                frame(), locator(), current().put("rotation", 2), 1450);
        reject(Rev37JitFrameGuard.DISPLAY_CHANGED,
                frame(), locator(), current().put("width", 1700), 1450);
        reject(Rev37JitFrameGuard.DISPLAY_CHANGED,
                frame(), locator(), current().put("display_id", 1), 1450);
        reject(Rev37JitFrameGuard.FOREGROUND_DRIFT,
                frame(), locator(), current().put("foreground",
                        foreground().put("activity", "OtherActivity")), 1450);
    }
    @Test
    public void rejectKeyguardOverlayAndNoninteractive() throws Exception {
        reject(Rev37JitFrameGuard.STALE,
                frame(), locator(), current().put("keyguard_locked", true), 1450);
        reject(Rev37JitFrameGuard.STALE,
                frame(), locator(), current().put("blocking_overlay_present", true), 1450);
        reject(Rev37JitFrameGuard.STALE,
                frame(), locator(), current().put("blocking_overlay_present", JSONObject.NULL), 1450);
        reject(Rev37JitFrameGuard.STALE,
                frame(), locator(), current().put("screen_interactive", false), 1450);
    }
    @Test
    public void malformedOrMissingDataCannotProduceReadOnlyMatch() throws Exception {
        reject(Rev37JitFrameGuard.UNAVAILABLE,
                frame().put("observed_boot_id", JSONObject.NULL), locator(), current(), 1450);
        reject(Rev37JitFrameGuard.UNAVAILABLE,
                frame().put("revision", "42"), locator(), current(), 1450);
        reject(Rev37JitFrameGuard.UNAVAILABLE,
                frame().put("foreground", new JSONObject()), locator(), current(), 1450);
        reject(Rev37JitFrameGuard.BOOT_MISMATCH,
                frame(), locator(), current().put("boot_id", JSONObject.NULL), 1450);
    }
}
