package com.stanley.y700automation.vision;

import static org.junit.Assert.assertFalse;

import android.app.Instrumentation;
import android.app.KeyguardManager;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.PowerManager;
import android.os.SystemClock;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;

/**
 * Rev3.7 Sprint 1A read-only, real-pixel Frame->Locator timing probe.
 *
 * No touch/press/swipe, activity launch, keyguard dismissal, screenshot file,
 * file upload, screenshot hash output, or mutation authorization. This test is
 * intentionally separate from the legacy benchmark which clicks a canvas.
 *
 * Locate operates on the EXACT captured Bitmap. Template is a temporary crop
 * from that same frame: this validates frame identity and matching mechanics,
 * NOT business-target localization accuracy or the full D-G3 acceptance.
 * No authoritative epoch/revision, blocking overlay or trusted activity is
 * available here, so production_dg3_passed ALWAYS remains false.
 */
@RunWith(AndroidJUnit4.class)
public final class Rev37ReadOnlyFrameReceiptInstrumentedTest {
    private static final long NS_PER_MS = 1_000_000L;
    private static final int PATCH = 88;
    private static final int SEARCH_RADIUS = 110;

    private static final class Receipt {
        final String frameId;
        final long generation;
        final long captureStartNs;
        final int rotation;
        final int width;
        final int height;
        final String packageName;

        Receipt(String frameId, long captureStartNs, VisionV0Harness.Frame frame) {
            this.frameId = frameId;
            this.generation = frame.generation;
            this.captureStartNs = captureStartNs;
            this.rotation = frame.rotation;
            this.width = frame.width;
            this.height = frame.height;
            this.packageName = frame.packageName;
        }
    }

    private static boolean sameFrameId(String expected, String provided) {
        return expected != null && expected.startsWith("frame-")
                && expected.equals(provided);
    }

    private static boolean exactFrameBinding(
            Receipt receipt, String locatorFrameId, VisionV0Harness.VisionTarget target) {
        return receipt != null && sameFrameId(receipt.frameId, locatorFrameId)
                && target != null && target.frameGeneration == receipt.generation
                && target.rotation == receipt.rotation
                && target.frameWidth == receipt.width && target.frameHeight == receipt.height;
    }

    private static JSONObject alwaysClosedReport() throws Exception {
        return new JSONObject()
                .put("probe", "rev37-real-pixel-readonly-v1")
                .put("status", "READ_ONLY_UNAVAILABLE")
                .put("production_dg3_passed", false)
                .put("dg3_status", "OPEN")
                .put("visual_dispatch_allowed", false)
                .put("action_attempts", 0)
                .put("pixel_persisted", false)
                .put("frame_token_authoritative", false)
                .put("semantic_epoch_revision_verified", false)
                .put("foreground_activity_verified", false)
                .put("blocking_overlay_verified", false)
                .put("route_age_calibrated", false);
    }

    private static void emit(Instrumentation instrumentation, JSONObject report) {
        Bundle bundle = new Bundle();
        bundle.putString("rev37_frame_receipt_json", report.toString());
        instrumentation.sendStatus(0, bundle);
    }

    /**
     * Observe the current foreground without changing it, with one real
     * screenshot and bounded same-pixel template localization.
     */
    @Test
    public void readOnlyPixelBoundLocator() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        UiDevice device = UiDevice.getInstance(instrumentation);
        Context context = instrumentation.getTargetContext();
        PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        KeyguardManager km = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);
        JSONObject report = alwaysClosedReport();
        Bitmap template = null;

        try {
            report.put("screen_interactive_before_capture", pm != null && pm.isInteractive())
                    .put("keyguard_unlocked_before_capture", km != null && !km.isKeyguardLocked());
            System.loadLibrary("opencv_java4");
            long captureStartNs = SystemClock.elapsedRealtimeNanos();
            try (VisionV0Harness.Frame frame =
                         VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                long captureEndNs = SystemClock.elapsedRealtimeNanos();
                Receipt receipt = new Receipt("frame-" + UUID.randomUUID(), captureStartNs, frame);
                report.put("capture_latency_ms", (captureEndNs - captureStartNs) / NS_PER_MS)
                        .put("frame_age_anchored_at_capture_start", true)
                        .put("exact_capture_generation_available", true);

                if (frame.width < 350 || frame.height < 350) {
                    report.put("status", "READ_ONLY_FRAME_TOO_SMALL");
                } else {
                    // Choose a non-flat patch strictly inside the current frame.
                    // All pixels remain in-memory; only the patch and a bounded
                    // search ROI are passed to the existing OpenCV matcher.
                    // Try at most nine independent, non-flat patches. Never
                    // suppress the matcher's confidence or ambiguity rules.
                    // All retries are on the SAME immutable captured frame.
                    List<Rect> patches = new ArrayList<>();
                    int[][] centers = {
                            {frame.width / 2, frame.height / 2},
                            {frame.width / 3, frame.height / 3},
                            {frame.width * 2 / 3, frame.height / 3},
                            {frame.width / 3, frame.height * 2 / 3},
                            {frame.width * 2 / 3, frame.height * 2 / 3},
                            {frame.width / 2, frame.height / 4},
                            {frame.width / 2, frame.height * 3 / 4},
                            {frame.width / 4, frame.height / 2},
                            {frame.width * 3 / 4, frame.height / 2}
                    };
                    for (int[] center : centers) {
                        int left = Math.max(0, Math.min(frame.width - PATCH,
                                center[0] - PATCH / 2));
                        int top = Math.max(0, Math.min(frame.height - PATCH,
                                center[1] - PATCH / 2));
                        Bitmap candidate = Bitmap.createBitmap(
                                frame.bitmap, left, top, PATCH, PATCH);
                        try {
                            double variance = VisionV0Harness.bitmapVariance(candidate, false);
                            if (Double.isFinite(variance) && variance >= 8.0) {
                                patches.add(new Rect(left, top, left + PATCH, top + PATCH));
                            }
                        } finally {
                            candidate.recycle();
                        }
                    }
                    report.put("eligible_patch_count", patches.size());
                    if (patches.isEmpty()) {
                        report.put("status", "READ_ONLY_LOW_INFORMATION");
                    } else {
                        long locatorStartNs = SystemClock.elapsedRealtimeNanos();
                        VisionV0Harness.VisionTarget target = null;
                        Rect selectedPatch = null;
                        VisionV0Harness.VisionFailure rejected = null;
                        int ambiguousCount = 0;
                        int attempts = 0;
                        for (Rect patch : patches) {
                            attempts++;
                            template = Bitmap.createBitmap(
                                    frame.bitmap, patch.left, patch.top,
                                    patch.width(), patch.height());
                            try {
                                Rect roi = new Rect(
                                        Math.max(0, patch.left - SEARCH_RADIUS),
                                        Math.max(0, patch.top - SEARCH_RADIUS),
                                        Math.min(frame.width, patch.right + SEARCH_RADIUS),
                                        Math.min(frame.height, patch.bottom + SEARCH_RADIUS));
                                target = VisionV0Harness.matchTemplate(
                                        frame, template, roi, false, 0.90, 8.0, 0.03);
                                selectedPatch = patch;
                                break;
                            } catch (VisionV0Harness.VisionFailure failure) {
                                rejected = failure;
                                if (VisionV0Harness.ERR_TEMPLATE_AMBIGUOUS.equals(failure.code)) {
                                    ambiguousCount++;
                                } else if (!VisionV0Harness.ERR_TEMPLATE_NOT_FOUND.equals(failure.code)) {
                                    break;
                                }
                            } finally {
                                template.recycle();
                                template = null;
                            }
                        }

                        long locatorEndNs = SystemClock.elapsedRealtimeNanos();
                        report.put("locator_attempts", attempts)
                                .put("ambiguous_candidate_count", ambiguousCount)
                                .put("locator_latency_ms",
                                        (locatorEndNs - locatorStartNs) / NS_PER_MS)
                                .put("frame_age_at_locator_ms",
                                        (locatorEndNs - captureStartNs) / NS_PER_MS);
                        if (target == null) {
                            report.put("status", "READ_ONLY_LOCATOR_BLOCKED")
                                    .put("error_code", rejected == null
                                            ? "VISION_TEMPLATE_NOT_FOUND" : rejected.code);
                        } else {
                            String locatorFrameId = receipt.frameId;
                            boolean exact = exactFrameBinding(receipt, locatorFrameId, target);
                            boolean correctPatch = selectedPatch.equals(target.bbox);
                            boolean screenInteractive = pm != null && pm.isInteractive();
                            boolean keyguardUnlocked = km != null && !km.isKeyguardLocked();
                            boolean packageUnchanged = receipt.packageName != null
                                    && receipt.packageName.equals(device.getCurrentPackageName());
                            boolean rotationUnchanged =
                                    receipt.rotation == device.getDisplayRotation();
                            boolean geometryUnchanged =
                                    receipt.width == device.getDisplayWidth()
                                    && receipt.height == device.getDisplayHeight();
                            long observedNs = SystemClock.elapsedRealtimeNanos();
                            report.put("frame_age_at_observation_ms",
                                            (observedNs - captureStartNs) / NS_PER_MS)
                                    .put("locator_exact_frame_id", exact)
                                    .put("locator_expected_patch", correctPatch)
                                    .put("screen_interactive", screenInteractive)
                                    .put("keyguard_unlocked", keyguardUnlocked)
                                    .put("package_unchanged", packageUnchanged)
                                    .put("rotation_unchanged", rotationUnchanged)
                                    .put("geometry_unchanged", geometryUnchanged)
                                    .put("status", exact && correctPatch
                                            && packageUnchanged && rotationUnchanged
                                            && geometryUnchanged && screenInteractive
                                            && keyguardUnlocked
                                            ? "READ_ONLY_PIXEL_LOCATED"
                                            : "READ_ONLY_CONTEXT_NOT_VERIFIED");
                        }
                    }
                }
            }
        } catch (Exception failure) {
            // No exceptions can cause a click or set any production gate true.
            report.put("status", "READ_ONLY_PROBE_UNAVAILABLE")
                    .put("error_kind", failure.getClass().getSimpleName());
        } finally {
            if (template != null && !template.isRecycled()) template.recycle();
            emit(instrumentation, report);
        }
        assertFalse("read-only receipt cannot authorize visual mutation",
                report.optBoolean("production_dg3_passed", true));
        assertFalse("read-only receipt cannot authorize dispatch",
                report.optBoolean("visual_dispatch_allowed", true));
    }

    /** No Android input. Synthetic frame-id mismatch must never validate. */
    @Test
    public void frameIdMismatchCannotValidate() {
        assertFalse(sameFrameId("frame-new", "frame-old"));
        assertFalse(sameFrameId("frame-new", null));
        assertFalse(sameFrameId(null, "frame-new"));
        assertFalse(exactFrameBinding(null, "frame-old", null));
    }
}
