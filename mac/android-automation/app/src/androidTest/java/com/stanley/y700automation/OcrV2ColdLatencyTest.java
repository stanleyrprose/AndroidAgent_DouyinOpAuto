package com.stanley.y700automation;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;

import java.io.File;
import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Measures repeated first-request latency after a confirmed OCR runtime unload. */
public final class OcrV2ColdLatencyTest extends PersistentOcrV2TestBase {
    private static final int RUNS = 20;
    private static final long WAIT_TIMEOUT_MS = 10_000L;

    @Test
    public void coldRequestsDocumentP50P95AfterConfirmedUnload() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context target = instrumentation.getTargetContext();
        Class<?> bridge = Class.forName(
                "com.stanley.y700automation.OcrRuntimeBridge",
                true,
                target.getClassLoader());
        Method configure = bridge.getMethod(
                "configureLifecycleForTest", long.class, long.class);
        Method reset = bridge.getMethod("resetLifecycleDefaults");
        Method recognize = bridge.getMethod(
                "recognize", Context.class, Bitmap.class, long.class);
        Method status = bridge.getMethod("statusJson");

        Bitmap crop = loadRepresentativeCrop(target);
        List<Double> wallMs = new ArrayList<>();
        List<Double> runtimeColdLoadMs = new ArrayList<>();
        configure.invoke(null, 25L, 0L);
        try {
            waitUntilUnloaded(status);

            long initialLoads = json(status.invoke(null)).optLong("load_count", 0L);
            for (int i = 0; i < RUNS; i++) {
                waitUntilUnloaded(status);
                JSONObject before = json(status.invoke(null));
                Assert.assertFalse("cold run must start unloaded", before.getBoolean("loaded"));
                Assert.assertEquals(0, before.getInt("in_flight"));

                long startedNs = SystemClock.elapsedRealtimeNanos();
                JSONObject raw = json(recognize.invoke(null, target, crop, 10_000L));
                double elapsedMs =
                        (SystemClock.elapsedRealtimeNanos() - startedNs) / 1_000_000.0;
                wallMs.add(elapsedMs);

                double coldLoad = raw.optDouble("cold_load_ms", Double.NaN);
                if (Double.isFinite(coldLoad) && coldLoad >= 0.0) {
                    runtimeColdLoadMs.add(coldLoad);
                }

                JSONObject after = json(status.invoke(null));
                Assert.assertTrue("runtime should be loaded immediately after cold request",
                        after.getBoolean("loaded"));
                Assert.assertEquals(0, after.getInt("in_flight"));
                Assert.assertEquals(
                        "every cold request must perform exactly one load",
                        initialLoads + i + 1L,
                        after.getLong("load_count"));
            }

            waitUntilUnloaded(status);
            JSONObject finalStatus = json(status.invoke(null));
            Assert.assertFalse(finalStatus.getBoolean("loaded"));
            Assert.assertEquals(0, finalStatus.getInt("in_flight"));

            JSONObject report = new JSONObject()
                    .put("runtime", "paddle-ppocrv6-tiny-onnx")
                    .put("runs", RUNS)
                    .put("cold_request_wall_latency_ms", summarize(wallMs))
                    .put("runtime_cold_load_ms", summarize(runtimeColdLoadMs))
                    .put("runtime_after", finalStatus);
            writePersistentArtifact("cold-latency-report.json", report);

            Assert.assertEquals(RUNS, wallMs.size());
            Assert.assertEquals(
                    "runtime must report cold-load timing for each cold request",
                    RUNS,
                    runtimeColdLoadMs.size());
        } finally {
            crop.recycle();
            reset.invoke(null);
        }
    }

    private static Bitmap loadRepresentativeCrop(Context target) throws Exception {
        File datasetDir = new File(target.getFilesDir(), "ocr-v2-dataset");
        JSONObject manifest = new JSONObject(new String(
                Files.readAllBytes(new File(datasetDir, "manifest.json").toPath()),
                StandardCharsets.UTF_8));
        JSONObject screen = manifest.getJSONArray("screens").getJSONObject(0);
        JSONObject targetRow = screen.getJSONArray("targets").getJSONObject(0);
        JSONArray rawRoi = targetRow.getJSONArray("roi");
        Rect roi = new Rect(
                rawRoi.getInt(0),
                rawRoi.getInt(1),
                rawRoi.getInt(2),
                rawRoi.getInt(3));
        Bitmap full = BitmapFactory.decodeFile(
                new File(datasetDir, screen.getString("image")).getAbsolutePath());
        Assert.assertNotNull("representative OCR screenshot missing", full);
        try {
            return Bitmap.createBitmap(
                    full, roi.left, roi.top, roi.width(), roi.height());
        } finally {
            full.recycle();
        }
    }

    private static void waitUntilUnloaded(Method status) throws Exception {
        long deadline = SystemClock.elapsedRealtime() + WAIT_TIMEOUT_MS;
        while (SystemClock.elapsedRealtime() < deadline) {
            JSONObject current = json(status.invoke(null));
            if (!current.optBoolean("loaded", false) &&
                    current.optInt("in_flight", 0) == 0) {
                return;
            }
            SystemClock.sleep(25L);
        }
        Assert.fail("OCR runtime did not reach unloaded state within timeout");
    }

    private static JSONObject summarize(List<Double> values) throws Exception {
        Assert.assertFalse("latency sample must be non-empty", values.isEmpty());
        List<Double> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        double sum = 0.0;
        for (double value : sorted) sum += value;
        return new JSONObject()
                .put("count", sorted.size())
                .put("mean_ms", sum / sorted.size())
                .put("p50_ms", percentile(sorted, 0.50))
                .put("p95_ms", percentile(sorted, 0.95))
                .put("min_ms", sorted.get(0))
                .put("max_ms", sorted.get(sorted.size() - 1));
    }

    private static double percentile(List<Double> sorted, double q) {
        if (sorted.size() == 1) return sorted.get(0);
        double index = q * (sorted.size() - 1);
        int low = (int) Math.floor(index);
        int high = (int) Math.ceil(index);
        if (low == high) return sorted.get(low);
        double fraction = index - low;
        return sorted.get(low) * (1.0 - fraction) + sorted.get(high) * fraction;
    }

    private static JSONObject json(Object raw) throws Exception {
        return new JSONObject(String.valueOf(raw));
    }
}
