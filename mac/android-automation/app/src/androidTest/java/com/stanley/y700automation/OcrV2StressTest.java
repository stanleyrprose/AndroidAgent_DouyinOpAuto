package com.stanley.y700automation;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.Debug;
import android.os.SystemClock;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;

import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

public final class OcrV2StressTest extends PersistentOcrV2TestBase {
    private static final int RUNS = 200;

    @Test
    public void warmStressHasNoLoadUnloadChurnAndDocumentsResources() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context target = instrumentation.getTargetContext();
        UiDevice device = UiDevice.getInstance(instrumentation);
        Class<?> bridge = Class.forName(
                "com.stanley.y700automation.OcrRuntimeBridge",
                true,
                target.getClassLoader());

        Method recognize = bridge.getMethod(
                "recognize", Context.class, Bitmap.class, long.class);
        Method status = bridge.getMethod("statusJson");
        Method configure = bridge.getMethod(
                "configureLifecycleForTest", long.class, long.class);
        Method reset = bridge.getMethod("resetLifecycleDefaults");

        Bitmap bitmap = benchmarkBitmap();
        Double tempBefore = batteryTemperatureC(device);
        Debug.MemoryInfo memoryBefore = memoryInfo();
        long nativeBefore = Debug.getNativeHeapAllocatedSize();

        JSONObject baseline = json(status.invoke(null));
        long loadBefore = baseline.optLong("load_count", 0L);
        long unloadBefore = baseline.optLong("unload_count", 0L);
        long successBefore = baseline.optLong("success_count", 0L);

        List<Double> warmMs = new ArrayList<>();
        try {
            // One request performs any lazy load and is excluded from warm percentiles.
            String first = String.valueOf(recognize.invoke(null, target, bitmap, 10_000L));
            Assert.assertTrue("warm-up should produce OCR items",
                    new JSONObject(first).getJSONArray("items").length() > 0);

            JSONObject warmed = json(status.invoke(null));
            long warmedLoadCount = warmed.getLong("load_count");
            Assert.assertEquals("warm-up must load exactly once when initially unloaded",
                    loadBefore + (baseline.optBoolean("loaded", false) ? 0 : 1),
                    warmedLoadCount);

            for (int i = 0; i < RUNS; i++) {
                long started = SystemClock.elapsedRealtimeNanos();
                String raw = String.valueOf(recognize.invoke(null, target, bitmap, 10_000L));
                double elapsedMs =
                        (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0;
                warmMs.add(elapsedMs);

                JSONObject result = new JSONObject(raw);
                Assert.assertTrue("OCR stress result must contain items at run=" + i,
                        result.getJSONArray("items").length() > 0);
            }

            JSONObject afterWarm = json(status.invoke(null));
            Assert.assertEquals("warm requests must not reload runtime",
                    warmedLoadCount, afterWarm.getLong("load_count"));
            Assert.assertEquals("runtime must not unload during active stress",
                    unloadBefore, afterWarm.getLong("unload_count"));
            Assert.assertEquals(0, afterWarm.getInt("in_flight"));
            Assert.assertEquals(
                    "every stress request should complete successfully",
                    successBefore + RUNS + 1L,
                    afterWarm.getLong("success_count"));

            Debug.MemoryInfo memoryAfterWarm = memoryInfo();
            long nativeAfterWarm = Debug.getNativeHeapAllocatedSize();
            Double tempAfterWarm = batteryTemperatureC(device);

            JSONObject report = new JSONObject()
                    .put("runs", RUNS)
                    .put("warm_latency_ms", summarize(warmMs))
                    .put("thermal", new JSONObject()
                            .put("before_c", nullable(tempBefore))
                            .put("after_c", nullable(tempAfterWarm))
                            .put("delta_c",
                                    tempBefore == null || tempAfterWarm == null
                                            ? JSONObject.NULL
                                            : tempAfterWarm - tempBefore))
                    .put("memory", new JSONObject()
                            .put("pss_before_kb", memoryBefore.getTotalPss())
                            .put("pss_after_warm_kb", memoryAfterWarm.getTotalPss())
                            .put("pss_delta_kb",
                                    memoryAfterWarm.getTotalPss() - memoryBefore.getTotalPss())
                            .put("native_before_bytes", nativeBefore)
                            .put("native_after_warm_bytes", nativeAfterWarm)
                            .put("native_delta_bytes", nativeAfterWarm - nativeBefore))
                    .put("runtime_after_warm", afterWarm);

            System.out.println("[OCRV2-STRESS] " + report.toString());

            // Exercise one bounded idle transition after stress; it must unload
            // exactly once, never while a request is in flight.
            configure.invoke(null, 200L, 0L);
            long deadline = SystemClock.elapsedRealtime() + 3000L;
            JSONObject unloaded;
            do {
                unloaded = json(status.invoke(null));
                if (!unloaded.optBoolean("loaded", true)) break;
                SystemClock.sleep(50L);
            } while (SystemClock.elapsedRealtime() < deadline);

            unloaded = json(status.invoke(null));
            Assert.assertFalse("runtime should unload after bounded idle",
                    unloaded.getBoolean("loaded"));
            Assert.assertEquals(0, unloaded.getInt("in_flight"));
            Assert.assertEquals("stress teardown must perform exactly one unload",
                    unloadBefore + 1L, unloaded.getLong("unload_count"));

            System.gc();
            SystemClock.sleep(300L);
            Debug.MemoryInfo memoryAfterUnload = memoryInfo();
            long nativeAfterUnload = Debug.getNativeHeapAllocatedSize();
            JSONObject unloadReport = new JSONObject()
                    .put("runtime", unloaded)
                    .put("memory_after_unload", new JSONObject()
                            .put("pss_kb", memoryAfterUnload.getTotalPss())
                            .put("pss_reclaimed_from_warm_kb",
                                    memoryAfterWarm.getTotalPss() - memoryAfterUnload.getTotalPss())
                            .put("native_bytes", nativeAfterUnload)
                            .put("native_reclaimed_from_warm_bytes",
                                    nativeAfterWarm - nativeAfterUnload));
            System.out.println("[OCRV2-STRESS] unloaded=" + unloadReport);
            writePersistentArtifact(
                    "stress-report.json",
                    new JSONObject()
                            .put("warm", report)
                            .put("unload", unloadReport));
        } finally {
            bitmap.recycle();
            reset.invoke(null);
        }
    }

    private static Bitmap benchmarkBitmap() {
        Bitmap bitmap = Bitmap.createBitmap(640, 512, Bitmap.Config.ARGB_8888);
        Canvas canvas = new Canvas(bitmap);
        canvas.drawColor(Color.WHITE);

        Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        RectF target = new RectF(110f, 150f, 530f, 360f);
        paint.setColor(Color.rgb(18, 20, 24));
        canvas.drawRoundRect(target, 20f, 20f, paint);

        paint.setColor(Color.WHITE);
        paint.setTextAlign(Paint.Align.CENTER);
        paint.setTextSize(96f);
        Paint.FontMetrics fm = paint.getFontMetrics();
        float baseline = target.centerY() - (fm.ascent + fm.descent) / 2f;
        canvas.drawText("继续", target.centerX(), baseline, paint);
        return bitmap;
    }

    private static Debug.MemoryInfo memoryInfo() {
        Debug.MemoryInfo info = new Debug.MemoryInfo();
        Debug.getMemoryInfo(info);
        return info;
    }

    private static Double batteryTemperatureC(UiDevice device) {
        try {
            String raw = device.executeShellCommand("dumpsys battery");
            for (String line : raw.split("\n")) {
                String trimmed = line.trim();
                if (trimmed.startsWith("temperature:")) {
                    return Integer.parseInt(
                            trimmed.substring("temperature:".length()).trim()) / 10.0;
                }
            }
        } catch (Throwable ignored) {
        }
        return null;
    }

    private static Object nullable(Double value) {
        return value == null ? JSONObject.NULL : value;
    }

    private static JSONObject summarize(List<Double> values) throws Exception {
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
