package com.stanley.y700automation.vision;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.opencv.core.Core;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

@RunWith(AndroidJUnit4.class)
public class VisionV0BenchmarkInstrumentedTest {
    private static final double MIN_CONFIDENCE = 0.80;
    private static final double MIN_VARIANCE = 8.0;
    private static final double MIN_SECOND_BEST_DELTA = 0.03;

    @Test
    public void runVisionV0Benchmark() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context targetContext = instrumentation.getTargetContext();
        UiDevice device = UiDevice.getInstance(instrumentation);

        System.loadLibrary("opencv_java4");

        JSONObject report = new JSONObject();
        report.put("status", "STARTED");
        report.put("benchmark", "vision-v0");
        report.put("opencv", Core.VERSION);
        report.put("production_routing_enabled", false);
        report.put("ocr_enabled", false);

        device.wakeUp();
        try (ParcelFileDescriptor ignored =
                     instrumentation.getUiAutomation().executeShellCommand("wm dismiss-keyguard")) {
            // Command completion is enough; there is no stdout to consume.
        }
        SystemClock.sleep(350L);

        launchBenchmarkActivity(targetContext);
        String expectedPackage = targetContext.getPackageName();
        for (int i = 0; i < 30 && !expectedPackage.equals(device.getCurrentPackageName()); i++) {
            SystemClock.sleep(100L);
        }
        String currentPackage = device.getCurrentPackageName();
        report.put("current_package", currentPackage);
        assertEquals("benchmark app must be foreground before capture",
                expectedPackage, currentPackage);
        SystemClock.sleep(350L);

        // The visible target is drawn inside one Canvas view and deliberately has
        // no semantic child node. This proves the benchmark exercises the exact
        // gap Vision Locator is meant to fill.
        boolean semanticTargetPresent =
                device.findObject(By.text("VISION_V0_IDLE")) != null ||
                device.findObject(By.desc("VISION_V0_IDLE")) != null;
        report.put("semantic_target_present", semanticTargetPresent);
        assertFalse("Canvas target must not be semantically resolved", semanticTargetPresent);

        VisionV0Harness.resetCounters();
        long managedBefore = VisionV0Harness.managedHeapUsed();
        long nativeBefore = VisionV0Harness.nativeHeapUsed();

        List<Double> warmCapture = new ArrayList<>();
        for (int i = 0; i < 20; i++) {
            long t0 = SystemClock.elapsedRealtimeNanos();
            try (VisionV0Harness.Frame ignored =
                         VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                warmCapture.add(msSince(t0));
            }
        }
        report.put("capture_warm_20", VisionV0Harness.percentiles(warmCapture));

        List<Double> stabilityCapture = new ArrayList<>();
        for (int i = 0; i < 200; i++) {
            long t0 = SystemClock.elapsedRealtimeNanos();
            try (VisionV0Harness.Frame ignored =
                         VisionV0Harness.capture(instrumentation, device, null, 0L)) {
                stabilityCapture.add(msSince(t0));
            }
        }
        report.put("capture_stability_200", VisionV0Harness.percentiles(stabilityCapture));
        report.put("peak_concurrent_frames", VisionV0Harness.maxActiveFrames());
        assertTrue("frame ownership must remain bounded", VisionV0Harness.maxActiveFrames() <= 2);

        List<Double> rawCapture = new ArrayList<>();
        JSONObject rawProfile = null;
        for (int i = 0; i < 20; i++) {
            long t0 = SystemClock.elapsedRealtimeNanos();
            byte[] raw = VisionV0Harness.captureRawScreencap(instrumentation);
            rawCapture.add(msSince(t0));
            JSONObject parsed = VisionV0Harness.parseRawScreencap(raw);
            if (rawProfile == null) {
                rawProfile = parsed;
            }
        }
        report.put("raw_screencap_20", VisionV0Harness.percentiles(rawCapture));
        report.put("raw_screencap_profile", rawProfile);

        Bitmap idleTemplate = VisionV0Harness.makeBenchmarkTemplate(
                targetContext, false, false);
        Bitmap idleAlphaTemplate = VisionV0Harness.makeBenchmarkTemplate(
                targetContext, false, true);
        Bitmap clickedTemplate = VisionV0Harness.makeBenchmarkTemplate(
                targetContext, true, false);

        VisionV0Harness.VisionTarget target;
        Rect broadRoi;
        try (VisionV0Harness.Frame frame =
                     VisionV0Harness.capture(instrumentation, device, null, 0L)) {
            report.put("frame", frame.metadata());
            broadRoi = VisionV0Harness.resolveRoi(
                    frame.width, frame.height, null,
                    new double[]{0.42, 0.20, 0.98, 0.78});
            target = VisionV0Harness.matchTemplate(
                    frame, idleTemplate, broadRoi, false,
                    MIN_CONFIDENCE, MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
            report.put("single_scale_target", target.json());

            // Absolute and normalized ROI must agree on validity and the conflict
            // is rejected before any capture/action side effect.
            Rect absolute = VisionV0Harness.resolveRoi(
                    frame.width, frame.height,
                    new int[]{broadRoi.left, broadRoi.top, broadRoi.right, broadRoi.bottom},
                    null);
            assertEquals(broadRoi, absolute);
        }

        report.put("roi_mapping", roiMappingChecks());
        report.put("scale_set", scaleChecks());
        report.put("roi_conflict", roiConflictCheck());

        JSONObject templateBench = new JSONObject();
        try (VisionV0Harness.Frame frame =
                     VisionV0Harness.capture(instrumentation, device, null, 0L)) {
            Rect roi250 = VisionV0Harness.squareAround(
                    target.centerX, target.centerY, 250, frame.width, frame.height);
            Rect roi500 = VisionV0Harness.squareAround(
                    target.centerX, target.centerY, 500, frame.width, frame.height);
            Rect full = new Rect(0, 0, frame.width, frame.height);

            templateBench.put("roi_250", matchBench(frame, idleTemplate, roi250, false, 10));
            templateBench.put("roi_500", matchBench(frame, idleTemplate, roi500, false, 10));
            templateBench.put("full_screen", matchBench(frame, idleTemplate, full, false, 5));
            templateBench.put("alpha_mask", matchBench(
                    frame, idleAlphaTemplate, roi500, true, 10));
            List<Double> narrowScales =
                    VisionV0Harness.deterministicScales(0.90, 1.10, 0.05);
            templateBench.put("narrow_multi_scale", multiScaleBench(
                    frame, idleTemplate, roi500, false, narrowScales, 5));
        }
        report.put("template_benchmarks", templateBench);

        report.put("low_information_guard", lowInformationGuard());
        report.put("capture_retry", captureRetryChecks(instrumentation, device));
        report.put("memory_pressure_guard", memoryPressureCheck(instrumentation, device));
        report.put("rotation_race", rotationRaceCheck(target));
        report.put("stale_target", staleTargetCheck(target));

        // Benchmark-only locate -> UiDevice click -> visual postcondition.
        JSONObject e2e = new JSONObject();
        try (VisionV0Harness.Frame frame =
                     VisionV0Harness.capture(instrumentation, device, null, 0L)) {
            Rect roi = VisionV0Harness.resolveRoi(
                    frame.width, frame.height, null,
                    new double[]{0.42, 0.20, 0.98, 0.78});
            VisionV0Harness.VisionTarget fresh = VisionV0Harness.matchTemplate(
                    frame, idleTemplate, roi, false,
                    MIN_CONFIDENCE, MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
            VisionV0Harness.validatePreAction(
                    fresh, device.getDisplayRotation(), frame.width, frame.height, frame.fingerprint);
            e2e.put("target", fresh.json());
            e2e.put("click_policy", "EXACT");
            e2e.put("click_result", device.click(fresh.centerX, fresh.centerY));
        }
        SystemClock.sleep(350L);
        try (VisionV0Harness.Frame after =
                     VisionV0Harness.capture(instrumentation, device, null, 0L)) {
            Rect roi = VisionV0Harness.resolveRoi(
                    after.width, after.height, null,
                    new double[]{0.42, 0.20, 0.98, 0.78});
            VisionV0Harness.VisionTarget clicked = VisionV0Harness.matchTemplate(
                    after, clickedTemplate, roi, false,
                    MIN_CONFIDENCE, MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
            e2e.put("postcondition", "clicked-template-visible");
            e2e.put("postcondition_target", clicked.json());
            e2e.put("postcondition_pass", true);
        }
        report.put("locate_click_verify", e2e);

        idleTemplate.recycle();
        idleAlphaTemplate.recycle();
        clickedTemplate.recycle();

        System.gc();
        SystemClock.sleep(250L);
        long managedAfter = VisionV0Harness.managedHeapUsed();
        long nativeAfter = VisionV0Harness.nativeHeapUsed();
        report.put("memory", new JSONObject()
                .put("managed_before", managedBefore)
                .put("managed_after", managedAfter)
                .put("managed_delta", managedAfter - managedBefore)
                .put("native_before", nativeBefore)
                .put("native_after", nativeAfter)
                .put("native_delta", nativeAfter - nativeBefore));

        report.put("status", "PASS");
        Bundle status = new Bundle();
        status.putString("vision_v0_json", report.toString());
        instrumentation.sendStatus(0, status);
    }

    private static void launchBenchmarkActivity(Context targetContext) {
        Intent intent = new Intent();
        intent.setClassName(targetContext.getPackageName(),
                "com.stanley.y700automation.VisionBenchmarkActivity");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TASK);
        targetContext.startActivity(intent);
    }

    private static JSONObject matchBench(
            VisionV0Harness.Frame frame,
            Bitmap template,
            Rect roi,
            boolean alpha,
            int runs) throws Exception {
        List<Double> times = new ArrayList<>();
        VisionV0Harness.VisionTarget last = null;
        for (int i = 0; i < runs; i++) {
            long t0 = SystemClock.elapsedRealtimeNanos();
            last = VisionV0Harness.matchTemplate(
                    frame, template, roi, alpha,
                    MIN_CONFIDENCE, MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
            times.add(msSince(t0));
        }
        return new JSONObject()
                .put("latency", VisionV0Harness.percentiles(times))
                .put("last", last == null ? JSONObject.NULL : last.json());
    }

    private static JSONObject multiScaleBench(
            VisionV0Harness.Frame frame,
            Bitmap template,
            Rect roi,
            boolean alpha,
            List<Double> scales,
            int runs) throws Exception {
        List<Double> times = new ArrayList<>();
        VisionV0Harness.VisionTarget last = null;
        for (int i = 0; i < runs; i++) {
            long t0 = SystemClock.elapsedRealtimeNanos();
            last = VisionV0Harness.matchTemplateMultiScale(
                    frame, template, roi, alpha, scales,
                    MIN_CONFIDENCE, MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
            times.add(msSince(t0));
        }
        return new JSONObject()
                .put("scales", new JSONArray(scales))
                .put("latency", VisionV0Harness.percentiles(times))
                .put("last", last == null ? JSONObject.NULL : last.json());
    }

    private static JSONObject roiMappingChecks() throws Exception {
        Rect portrait = VisionV0Harness.resolveRoi(
                1600, 2560, null, new double[]{0.1, 0.2, 0.9, 0.8});
        Rect landscape = VisionV0Harness.resolveRoi(
                2560, 1600, null, new double[]{0.1, 0.2, 0.9, 0.8});
        Rect windowed = VisionV0Harness.resolveRoi(
                1200, 900, null, new double[]{0.1, 0.2, 0.9, 0.8});
        return new JSONObject()
                .put("portrait", rectJson(portrait))
                .put("landscape", rectJson(landscape))
                .put("window_geometry", rectJson(windowed));
    }

    private static JSONObject scaleChecks() throws Exception {
        List<Double> a = VisionV0Harness.deterministicScales(0.90, 1.10, 0.07);
        List<Double> b = VisionV0Harness.deterministicScales(0.90, 1.10, 0.07);
        assertEquals(a, b);
        assertEquals(1.10, a.get(a.size() - 1), 0.0);
        int maxCount = 0;
        for (double v : a) if (Double.compare(v, 1.10) == 0) maxCount++;
        assertEquals(1, maxCount);
        boolean invalidBlocked = false;
        try {
            VisionV0Harness.deterministicScales(1.10, 0.90, 0.05);
        } catch (VisionV0Harness.VisionFailure e) {
            invalidBlocked = VisionV0Harness.ERR_TEMPLATE_CONFIG.equals(e.code);
        }
        assertTrue(invalidBlocked);
        return new JSONObject()
                .put("samples", new JSONArray(a))
                .put("deterministic", true)
                .put("max_included_once", true)
                .put("invalid_config_blocked", true);
    }

    private static JSONObject roiConflictCheck() throws Exception {
        boolean blocked = false;
        try {
            VisionV0Harness.resolveRoi(
                    1000, 1000,
                    new int[]{0, 0, 500, 500},
                    new double[]{0.0, 0.0, 0.5, 0.5});
        } catch (VisionV0Harness.VisionFailure e) {
            blocked = VisionV0Harness.ERR_INVALID_ROI.equals(e.code);
        }
        assertTrue(blocked);
        return new JSONObject().put("blocked", true).put("error", VisionV0Harness.ERR_INVALID_ROI);
    }

    private static JSONObject captureRetryChecks(
            Instrumentation instrumentation, UiDevice device) throws Exception {
        VisionV0Harness.resetCounters();
        try (VisionV0Harness.Frame ignored = VisionV0Harness.capture(
                instrumentation, device, new AtomicInteger(1), 0L)) {
            // exactly one injected failure then success
        }
        int retriesOnSuccess = VisionV0Harness.captureRetryCount();
        assertEquals(1, retriesOnSuccess);

        VisionV0Harness.resetCounters();
        boolean failedClosed = false;
        try {
            VisionV0Harness.capture(
                    instrumentation, device, new AtomicInteger(2), 0L);
        } catch (VisionV0Harness.VisionFailure e) {
            failedClosed = VisionV0Harness.ERR_CAPTURE_FAILED.equals(e.code);
        }
        assertTrue(failedClosed);
        assertEquals(1, VisionV0Harness.captureRetryCount());
        return new JSONObject()
                .put("first_failure_then_success_retries", retriesOnSuccess)
                .put("repeated_failure_fail_closed", true)
                .put("max_retries", 1);
    }

    private static JSONObject memoryPressureCheck(
            Instrumentation instrumentation, UiDevice device) throws Exception {
        boolean throttled = false;
        try {
            VisionV0Harness.capture(instrumentation, device, null, 1L);
        } catch (VisionV0Harness.VisionFailure e) {
            throttled = VisionV0Harness.ERR_OOM_THROTTLED.equals(e.code);
        }
        assertTrue(throttled);
        return new JSONObject()
                .put("simulated", true)
                .put("throttled", true)
                .put("error", VisionV0Harness.ERR_OOM_THROTTLED);
    }

    private static JSONObject rotationRaceCheck(
            VisionV0Harness.VisionTarget target) throws Exception {
        boolean blocked = false;
        boolean clickAttempted = false;
        try {
            VisionV0Harness.validatePreAction(
                    target,
                    (target.rotation + 1) % 4,
                    target.frameWidth,
                    target.frameHeight,
                    null);
            clickAttempted = true;
        } catch (VisionV0Harness.VisionFailure e) {
            blocked = VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code);
        }
        assertTrue(blocked);
        assertFalse(clickAttempted);
        return new JSONObject()
                .put("blocked", true)
                .put("click_attempted", false)
                .put("error", VisionV0Harness.ERR_ROTATION_MISMATCH);
    }

    private static JSONObject staleTargetCheck(
            VisionV0Harness.VisionTarget target) throws Exception {
        boolean blocked = false;
        try {
            VisionV0Harness.validatePreAction(
                    target,
                    target.rotation,
                    target.frameWidth,
                    target.frameHeight,
                    target.frameFingerprint + 1L);
        } catch (VisionV0Harness.VisionFailure e) {
            blocked = VisionV0Harness.ERR_STALE_TARGET.equals(e.code);
        }
        assertTrue(blocked);
        return new JSONObject()
                .put("blocked", true)
                .put("error", VisionV0Harness.ERR_STALE_TARGET);
    }

    private static JSONObject lowInformationGuard() throws Exception {
        Bitmap frame = Bitmap.createBitmap(256, 256, Bitmap.Config.ARGB_8888);
        frame.eraseColor(Color.WHITE);
        Bitmap template = Bitmap.createBitmap(64, 64, Bitmap.Config.ARGB_8888);
        template.eraseColor(Color.TRANSPARENT);
        android.graphics.Canvas c = new android.graphics.Canvas(template);
        android.graphics.Paint p = new android.graphics.Paint();
        p.setColor(Color.WHITE);
        c.drawRect(8, 8, 56, 56, p);
        double unsafe = VisionV0Harness.unsafeMaskedBestScoreForBenchmark(frame, template);
        double variance = VisionV0Harness.bitmapVariance(template, true);
        boolean guarded = false;

        VisionV0Harness.Frame synthetic = new VisionV0Harness.Frame(frame, 0);
        try {
            VisionV0Harness.matchTemplate(
                    synthetic,
                    template,
                    new Rect(0, 0, 256, 256),
                    true,
                    0.80,
                    MIN_VARIANCE,
                    MIN_SECOND_BEST_DELTA);
        } catch (VisionV0Harness.VisionFailure e) {
            guarded = VisionV0Harness.ERR_TEMPLATE_NOT_FOUND.equals(e.code);
        } finally {
            synthetic.close();
            template.recycle();
        }
        assertTrue("low-information template must be rejected", guarded);
        return new JSONObject()
                .put("unsafe_masked_score", unsafe)
                .put("template_variance", variance)
                .put("guard_rejected", true);
    }

    private static JSONArray rectJson(Rect r) {
        return new JSONArray().put(r.left).put(r.top).put(r.right).put(r.bottom);
    }

    private static double msSince(long startNs) {
        return (SystemClock.elapsedRealtimeNanos() - startNs) / 1_000_000.0;
    }
}
