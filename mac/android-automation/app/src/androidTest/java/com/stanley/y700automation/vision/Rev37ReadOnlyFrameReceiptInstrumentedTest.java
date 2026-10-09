package com.stanley.y700automation.vision;

import static org.junit.Assert.assertFalse;

import android.app.Instrumentation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.UiAutomation;
import android.app.KeyguardManager;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityWindowInfo;
import android.os.ParcelFileDescriptor;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiObject2;

import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;

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


    /**
     * Cross-frame TikTok CREATE target probe (no Android input).
     *
     * A reference patch is cropped from capture A using an INDEPENDENT
     * accessibility bound for the verified "创建" button. That patch is then
     * matched against capture B, not A. Current accessibility bounds, package,
     * rotation, interactive/keyguard and boot observations are independently
     * re-read after matching. This is a read-only diagnostic, not an approved
     * prepackaged/template-versioned production locator.
     */
    @Test
    public void readOnlyTikTokCreateCrossFrameLocator() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        UiDevice device = UiDevice.getInstance(instrumentation);
        Context context = instrumentation.getTargetContext();
        PowerManager power = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        KeyguardManager keyguard = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);
        JSONObject report = alwaysClosedReport()
                .put("probe", "rev37-tiktok-create-cross-frame-readonly-v1")
                .put("target_identity", "TIKTOK_CREATE_ACCESSIBILITY_ANCHOR")
                .put("reference_template_persisted", false)
                .put("cross_frame_locator_attempted", false)
                .put("boot_id_readable", false)
                .put("boot_id_consistent", false);
        Bitmap reference = null;
        try {
            if (!"com.zhiliaoapp.musically".equals(device.getCurrentPackageName())
                    || power == null || !power.isInteractive()
                    || keyguard == null || keyguard.isKeyguardLocked()) {
                report.put("status", "READ_ONLY_FOREGROUND_OR_LOCKED");
            } else {
                List<UiObject2> candidates = device.findObjects(By.desc("创建"));
                if (candidates.size() == 0) {
                    candidates = device.findObjects(By.text("创建"));
                }
                report.put("semantic_candidate_count", candidates.size());
                if (candidates.size() != 1) {
                    report.put("status", "READ_ONLY_SEMANTIC_TARGET_UNAVAILABLE");
                } else {
                    Rect beforeBounds = candidates.get(0).getVisibleBounds();
                    String bootBefore = readBootId(instrumentation);
                    report.put("boot_id_readable", bootBefore != null);
                    System.loadLibrary("opencv_java4");
                    long startA = SystemClock.elapsedRealtimeNanos();
                    try (VisionV0Harness.Frame captureA =
                                 VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                        long endA = SystemClock.elapsedRealtimeNanos();
                        report.put("reference_capture_ms", (endA - startA) / NS_PER_MS);
                        if (captureA.width <= 0 || captureA.height <= 0
                                || beforeBounds.width() < 96 || beforeBounds.height() < 96
                                || beforeBounds.centerX() - 48 < 0
                                || beforeBounds.centerY() - 48 < 0
                                || beforeBounds.centerX() + 48 > captureA.width
                                || beforeBounds.centerY() + 48 > captureA.height) {
                            report.put("status", "READ_ONLY_TARGET_GEOMETRY_UNAVAILABLE");
                        } else {
                            // Image A is the reference; image B is never used
                            // to construct this reference template.
                            reference = Bitmap.createBitmap(
                                    captureA.bitmap,
                                    beforeBounds.centerX() - 48,
                                    beforeBounds.centerY() - 48,
                                    96, 96);
                            double variance = VisionV0Harness.bitmapVariance(reference, false);
                            if (!Double.isFinite(variance) || variance < 8.0) {
                                report.put("status", "READ_ONLY_REFERENCE_LOW_INFORMATION");
                            } else {
                                long startB = SystemClock.elapsedRealtimeNanos();
                                try (VisionV0Harness.Frame captureB =
                                             VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                                    long endB = SystemClock.elapsedRealtimeNanos();
                                    report.put("target_capture_ms", (endB - startB) / NS_PER_MS)
                                            .put("capture_to_capture_start_ms", (startB - startA) / NS_PER_MS)
                                            .put("distinct_frame_generations", captureA.generation != captureB.generation)
                                            .put("cross_frame_locator_attempted", true);
                                    String frameIdB = "frame-" + UUID.randomUUID();
                                    Receipt bReceipt = new Receipt(frameIdB, startB, captureB);
                                    Rect roi = new Rect(
                                            Math.max(0, beforeBounds.left - 120),
                                            Math.max(0, beforeBounds.top - 120),
                                            Math.min(captureB.width, beforeBounds.right + 120),
                                            Math.min(captureB.height, beforeBounds.bottom + 120));
                                    long locateStart = SystemClock.elapsedRealtimeNanos();
                                    try {
                                        VisionV0Harness.VisionTarget target =
                                                VisionV0Harness.matchTemplate(
                                                        captureB, reference, roi, false,
                                                        0.90, 8.0, 0.03);
                                        long locateEnd = SystemClock.elapsedRealtimeNanos();
                                        List<UiObject2> currentNodes = device.findObjects(By.desc("创建"));
                                        if (currentNodes.size() == 0) {
                                            currentNodes = device.findObjects(By.text("创建"));
                                        }
                                        String bootAfter = readBootId(instrumentation);
                                        boolean bootSame = bootBefore != null && bootBefore.equals(bootAfter);
                                        boolean frameSame = exactFrameBinding(bReceipt, frameIdB, target);
                                        boolean distinctFrames = captureA.generation != captureB.generation;
                                        boolean packageSame = "com.zhiliaoapp.musically".equals(
                                                device.getCurrentPackageName())
                                                && "com.zhiliaoapp.musically".equals(captureA.packageName)
                                                && "com.zhiliaoapp.musically".equals(captureB.packageName);
                                        boolean rotationSame = captureA.rotation == captureB.rotation
                                                && captureB.rotation == device.getDisplayRotation();
                                        boolean geometrySame = captureA.width == captureB.width
                                                && captureA.height == captureB.height
                                                && captureB.width == device.getDisplayWidth()
                                                && captureB.height == device.getDisplayHeight();
                                        boolean semanticConsistent = false;
                                        if (currentNodes.size() == 1) {
                                            Rect currentBounds = currentNodes.get(0).getVisibleBounds();
                                            semanticConsistent = currentBounds.contains(
                                                    target.centerX, target.centerY)
                                                    && Math.abs(currentBounds.centerX() - target.centerX) <= 48
                                                    && Math.abs(currentBounds.centerY() - target.centerY) <= 48;
                                        }
                                        boolean awake = power.isInteractive();
                                        boolean unlocked = !keyguard.isKeyguardLocked();
                                        long checkedNs = SystemClock.elapsedRealtimeNanos();
                                        report.put("locator_latency_ms", (locateEnd - locateStart) / NS_PER_MS)
                                                .put("frame_age_at_locator_ms", (locateEnd - startB) / NS_PER_MS)
                                                .put("frame_age_at_observation_ms", (checkedNs - startB) / NS_PER_MS)
                                                .put("locator_exact_frame_id", frameSame)
                                                .put("semantic_target_consistent", semanticConsistent)
                                                .put("distinct_frame_generations", distinctFrames)
                                                .put("boot_id_consistent", bootSame)
                                                .put("package_unchanged", packageSame)
                                                .put("rotation_unchanged", rotationSame)
                                                .put("geometry_unchanged", geometrySame)
                                                .put("screen_interactive", awake)
                                                .put("keyguard_unlocked", unlocked)
                                                .put("status", frameSame && semanticConsistent
                                                        && distinctFrames && bootSame
                                                        && packageSame && rotationSame
                                                        && geometrySame && awake && unlocked
                                                        ? "READ_ONLY_CROSS_FRAME_TARGET_LOCATED"
                                                        : "READ_ONLY_CROSS_FRAME_CONTEXT_NOT_VERIFIED");
                                    } catch (VisionV0Harness.VisionFailure failure) {
                                        report.put("status", "READ_ONLY_CROSS_FRAME_LOCATOR_BLOCKED")
                                                .put("error_code", failure.code);
                                    }
                                }
                            }
                        }
                    }
                }
            }
        } catch (Exception failure) {
            report.put("status", "READ_ONLY_CROSS_FRAME_UNAVAILABLE")
                    .put("error_kind", failure.getClass().getSimpleName());
        } finally {
            if (reference != null && !reference.isRecycled()) reference.recycle();
            emit(instrumentation, report);
        }
        assertFalse(report.optBoolean("production_dg3_passed", true));
        assertFalse(report.optBoolean("visual_dispatch_allowed", true));
    }

    private static String readBootId(Instrumentation instrumentation) {
        // Reads Android kernel boot identity in shell context; never logs the
        // value, does not write it to disk, and fails closed if inaccessible.
        try (ParcelFileDescriptor fd = instrumentation.getUiAutomation()
                .executeShellCommand("cat /proc/sys/kernel/random/boot_id")) {
            if (fd == null) return null;
            try (BufferedReader input = new BufferedReader(new InputStreamReader(
                    new FileInputStream(fd.getFileDescriptor())))) {
                String value = input.readLine();
                if (value == null || !value.matches("[0-9a-fA-F-]{36}")) return null;
                return value;
            }
        } catch (Exception failure) {
            return null;
        }
    }


    /** Isolated kernel boot identity diagnostic; safe even while locked. */
    @Test
    public void readOnlyBootIdentity() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        JSONObject report = alwaysClosedReport()
                .put("probe", "rev37-readonly-boot-id")
                .put("status", "READ_ONLY_BOOT_UNAVAILABLE");
        String before = readBootId(instrumentation);
        String after = readBootId(instrumentation);
        boolean verified = before != null && before.equals(after);
        report.put("boot_id_readable", before != null)
                .put("boot_id_consistent", verified)
                .put("status", verified ? "READ_ONLY_BOOT_STABLE" : "READ_ONLY_BOOT_UNAVAILABLE");
        emit(instrumentation, report);
        assertFalse(report.optBoolean("production_dg3_passed", true));
        assertFalse(report.optBoolean("visual_dispatch_allowed", true));
    }


    /**
     * Real-screen negative JIT proof: current physical fields are reread
     * independently. Debian authoritative epoch/revision and overlay
     * classification are UNAVAILABLE, so this can never authorize a click.
     * Only the delayed-frame branch injects explicit fixture-only fields.
     */
    @Test
    public void readOnlyLivePhysicalJitFailClosed() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        UiDevice device = UiDevice.getInstance(instrumentation);
        Context context = instrumentation.getTargetContext();
        PowerManager power = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        KeyguardManager keyguard = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);
        JSONObject report = alwaysClosedReport()
                .put("probe", "rev37-real-physical-jit-readonly-v1")
                .put("status", "READ_ONLY_PHYSICAL_UNAVAILABLE")
                .put("semantic_sot_readable", false)
                .put("overlay_classification_verified", false)
                .put("foreground_activity_verified", false)
                .put("fixture_fields_not_authority", true)
                .put("pixel_locator_verified", false)
                .put("target_identity", "SYNTHETIC_CENTRE_REGION_NOT_SEMANTIC");
        final int fixtureMaxAgeMs = 600; // synthetic-only, NOT a calibrated route contract
        try {
            if (power == null || !power.isInteractive()
                    || keyguard == null || keyguard.isKeyguardLocked()
                    || device.getCurrentPackageName() == null) {
                report.put("status", "READ_ONLY_FOREGROUND_OR_LOCKED");
            } else {
                if (device.getDisplayWidth() < 160 || device.getDisplayHeight() < 160) {
                    report.put("status", "READ_ONLY_DISPLAY_TOO_SMALL");
                } else {
                    Rect rect = new Rect(device.getDisplayWidth() / 2 - 48,
                            device.getDisplayHeight() / 2 - 48,
                            device.getDisplayWidth() / 2 + 48,
                            device.getDisplayHeight() / 2 + 48);
                    String initialBoot = readBootId(instrumentation);
                    long frameStartNs = SystemClock.elapsedRealtimeNanos();
                    try (VisionV0Harness.Frame pixels =
                                 VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                        long frameEndNs = SystemClock.elapsedRealtimeNanos();
                        if (initialBoot == null || rect.isEmpty()
                                || rect.left < 0 || rect.top < 0
                                || rect.right > pixels.width || rect.bottom > pixels.height
                                || pixels.packageName == null
                                || !pixels.packageName.equals(device.getCurrentPackageName())) {
                            report.put("status", "READ_ONLY_CAPTURE_CONTEXT_INVALID");
                        } else {
                            String frameId = "frame-" + UUID.randomUUID();
                            JSONObject foregroundFixture = new JSONObject()
                                    .put("package", pixels.packageName)
                                    .put("activity", "fixture-activity-UNVERIFIED");
                            JSONObject tokenFixture = new JSONObject()
                                    .put("frame_token_version", 1)
                                    .put("frame_id", frameId)
                                    .put("source", "SCREENSHOT")
                                    .put("observed_boot_id", initialBoot)
                                    .put("captured_boottime_ms", frameStartNs / NS_PER_MS)
                                    .put("state_epoch", "epoch-fixture-NOT-SOT")
                                    .put("revision", 0)
                                    .put("display_id", 0)
                                    .put("rotation", pixels.rotation)
                                    .put("width", pixels.width)
                                    .put("height", pixels.height)
                                    .put("foreground", foregroundFixture)
                                    .put("max_age_ms", fixtureMaxAgeMs);
                            JSONObject locatorFixture = new JSONObject()
                                    .put("frame_id", frameId)
                                    .put("locator_contract_version", "readonly-hardware-fixture-v1")
                                    .put("target_identity", "synthetic-center-region-only")
                                    .put("ambiguous", false)
                                    .put("bounds", new org.json.JSONArray()
                                            .put(rect.left).put(rect.top)
                                            .put(rect.right).put(rect.bottom));
                            JSONObject live = new JSONObject()
                                    .put("boot_id", readBootId(instrumentation))
                                    .put("display_id", 0)
                                    .put("rotation", device.getDisplayRotation())
                                    .put("width", device.getDisplayWidth())
                                    .put("height", device.getDisplayHeight())
                                    .put("foreground", new JSONObject()
                                            .put("package", device.getCurrentPackageName())
                                            .put("activity", "fixture-activity-UNVERIFIED"))
                                    .put("screen_interactive", power.isInteractive())
                                    .put("keyguard_locked", keyguard.isKeyguardLocked());
                            // Epoch/revision and overlay are deliberately
                            // MISSING, not self-attested or supplied by caller.
                            long clock = SystemClock.elapsedRealtimeNanos() / NS_PER_MS;
                            Rev37JitFrameGuard.Verdict withoutSot =
                                    Rev37JitFrameGuard.compareFixtureReadOnly(
                                            tokenFixture, locatorFixture, live,
                                            "readonly-hardware-fixture-v1",
                                            fixtureMaxAgeMs, clock);
                            org.junit.Assert.assertFalse(withoutSot.readOnlyMatched());
                            Rev37JitFrameGuard.Verdict wrongFrame =
                                    Rev37JitFrameGuard.compareFixtureReadOnly(
                                            tokenFixture,
                                            new JSONObject(locatorFixture.toString())
                                                    .put("frame_id", "frame-invalid"),
                                            live, "readonly-hardware-fixture-v1",
                                            fixtureMaxAgeMs, clock);
                            org.junit.Assert.assertEquals(
                                    Rev37JitFrameGuard.LOCATOR_MISMATCH, wrongFrame.code);
                            // Actually wait for this specific captured frame
                            // to expire on the device monotonic clock.
                            SystemClock.sleep(fixtureMaxAgeMs + 180L);
                            JSONObject later = new JSONObject(live.toString())
                                    .put("boot_id", readBootId(instrumentation))
                                    .put("rotation", device.getDisplayRotation())
                                    .put("width", device.getDisplayWidth())
                                    .put("height", device.getDisplayHeight())
                                    .put("screen_interactive", power.isInteractive())
                                    .put("keyguard_locked", keyguard.isKeyguardLocked())
                                    .put("foreground", new JSONObject()
                                            .put("package", device.getCurrentPackageName())
                                            .put("activity", "fixture-activity-UNVERIFIED"))
                                    // Test fixture only: NOT independent
                                    // trusted state or classified overlay.
                                    .put("state_epoch", "epoch-fixture-NOT-SOT")
                                    .put("revision", 0)
                                    .put("blocking_overlay_present", false);
                            long laterClock = SystemClock.elapsedRealtimeNanos() / NS_PER_MS;
                            Rev37JitFrameGuard.Verdict stale =
                                    Rev37JitFrameGuard.compareFixtureReadOnly(
                                            tokenFixture, locatorFixture, later,
                                            "readonly-hardware-fixture-v1",
                                            fixtureMaxAgeMs, laterClock);
                            org.junit.Assert.assertFalse(stale.readOnlyMatched());
                            org.junit.Assert.assertFalse(
                                    Rev37JitFrameGuard.verifyForProductionDispatch(
                                            tokenFixture, locatorFixture, later).readOnlyMatched());
                            long age = laterClock - frameStartNs / NS_PER_MS;
                            org.junit.Assert.assertTrue(age > fixtureMaxAgeMs);
                            report.put("capture_latency_ms", (frameEndNs - frameStartNs) / NS_PER_MS)
                                    .put("real_elapsed_frame_age_ms", age)
                                    .put("live_boot_observed", live.optString("boot_id").length() == 36)
                                    .put("missing_sot_jit_verdict", withoutSot.code)
                                    .put("frame_mismatch_jit_verdict", wrongFrame.code)
                                    .put("expired_real_clock_jit_verdict", stale.code)
                                    .put("status", Rev37JitFrameGuard.STALE.equals(withoutSot.code)
                                            && Rev37JitFrameGuard.STALE.equals(stale.code)
                                            && Rev37JitFrameGuard.LOCATOR_MISMATCH.equals(wrongFrame.code)
                                            ? "READ_ONLY_REAL_JIT_REFUSAL_VERIFIED"
                                            : "READ_ONLY_REAL_CONTEXT_DRIFT_BLOCKED");
                        }
                    }
                }
            }
        } catch (Exception failure) {
            report.put("status", "READ_ONLY_REAL_JIT_UNAVAILABLE")
                    .put("error_kind", failure.getClass().getSimpleName());
        } finally {
            emit(instrumentation, report);
        }
        assertFalse(report.optBoolean("production_dg3_passed", true));
        assertFalse(report.optBoolean("visual_dispatch_allowed", true));
        org.junit.Assert.assertEquals(0, report.getInt("action_attempts"));
    }


    /**
     * Raw top-level Android accessibility window FACTS ONLY.
     * A visible second window is not automatically a blocking overlay.
     * No window content, text, package or pixel is exported. Classification
     * requires separate versioned action-specific policy; remain unavailable.
     */
    @Test
    public void readOnlyOverlayWindowFacts() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        JSONObject report = alwaysClosedReport()
                .put("probe", "rev37-overlay-window-facts-readonly-v1")
                .put("status", "READ_ONLY_WINDOW_FACTS_UNAVAILABLE")
                .put("blocking_overlay_classification_available", false)
                .put("authoritative_overlay_clear", false)
                .put("window_pixels_persisted", false);
        UiAutomation automation = instrumentation.getUiAutomation();
        AccessibilityServiceInfo serviceInfo = null;
        int priorFlags = -1;
        try {
            serviceInfo = automation.getServiceInfo();
            if (serviceInfo != null) {
                priorFlags = serviceInfo.flags;
                serviceInfo.flags = priorFlags
                        | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
                automation.setServiceInfo(serviceInfo);
            }
            List<AccessibilityWindowInfo> windows = automation.getWindows();
            if (windows != null && !windows.isEmpty()) {
                int application = 0;
                int inputMethod = 0;
                int system = 0;
                int accessibilityOverlay = 0;
                int other = 0;
                int focused = 0;
                int active = 0;
                for (AccessibilityWindowInfo window : windows) {
                    if (window == null) continue;
                    switch (window.getType()) {
                        case AccessibilityWindowInfo.TYPE_APPLICATION:
                            application++;
                            break;
                        case AccessibilityWindowInfo.TYPE_INPUT_METHOD:
                            inputMethod++;
                            break;
                        case AccessibilityWindowInfo.TYPE_SYSTEM:
                            system++;
                            break;
                        case AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY:
                            accessibilityOverlay++;
                            break;
                        default:
                            other++;
                    }
                    if (window.isFocused()) focused++;
                    if (window.isActive()) active++;
                }
                report.put("window_count", windows.size())
                        .put("application_windows", application)
                        .put("input_method_windows", inputMethod)
                        .put("system_windows", system)
                        .put("accessibility_overlay_windows", accessibilityOverlay)
                        .put("other_windows", other)
                        .put("focused_window_count", focused)
                        .put("active_window_count", active)
                        .put("status", "READ_ONLY_WINDOW_FACTS_OBSERVED");
            }
        } catch (Exception failure) {
            report.put("status", "READ_ONLY_WINDOW_FACTS_UNAVAILABLE")
                    .put("error_kind", failure.getClass().getSimpleName());
        } finally {
            if (serviceInfo != null && priorFlags >= 0) {
                try {
                    serviceInfo.flags = priorFlags;
                    automation.setServiceInfo(serviceInfo);
                    report.put("ui_automation_window_flags_restored", true);
                } catch (Exception failure) {
                    report.put("status", "READ_ONLY_WINDOW_FLAGS_RESTORE_FAILED");
                    report.put("ui_automation_window_flags_restored", false);
                }
            }
            emit(instrumentation, report);
        }
        assertFalse(report.optBoolean("production_dg3_passed", true));
        assertFalse(report.optBoolean("visual_dispatch_allowed", true));
        assertFalse(report.optBoolean("authoritative_overlay_clear", true));
        org.junit.Assert.assertEquals(0, report.getInt("action_attempts"));
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
