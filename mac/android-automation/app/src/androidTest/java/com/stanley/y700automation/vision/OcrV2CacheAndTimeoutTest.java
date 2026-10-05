package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.os.SystemClock;

import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class OcrV2CacheAndTimeoutTest {
    private static final String PACKAGE = "com.stanley.y700automation";

    @Test
    public void staticFrameHitsCacheAndVisualChangeInvalidatesIt() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        UiDevice device = UiDevice.getInstance(instrumentation);
        prepareBenchmark(instrumentation, device, "继续");

        VisionTemplateLocator.Config config = new VisionTemplateLocator.Config(
                new JSONObject()
                        .put("enabled", true)
                        .put("mode", "fallback")
                        .put("ocr_enabled", true));
        OcrTextLocator locator = new OcrTextLocator(instrumentation, device, config);
        JSONObject spec = new JSONObject()
                .put("type", "vision_text")
                .put("pattern", "继续")
                .put("match", "substring")
                .put("roi_ratio", new JSONArray().put(0.60).put(0.38).put(0.84).put(0.55))
                .put("min_confidence", 0.85)
                .put("expected_package", PACKAGE);

        OcrTextLocator.Resolved first = locator.resolve(spec, 5000L);
        OcrTextLocator.Resolved second = locator.resolve(spec, 5000L);
        Assert.assertFalse(first.metadata.getJSONObject("source_context")
                .getBoolean("cache_hit"));
        Assert.assertTrue(second.metadata.getJSONObject("source_context")
                .getBoolean("cache_hit"));
        Assert.assertEquals(first.bbox, second.bbox);

        device.click(first.centerX, first.centerY);
        SystemClock.sleep(350L);

        OcrTextLocator.Resolved third = locator.resolve(spec, 5000L);
        Assert.assertFalse("changed pixels must invalidate OCR cache",
                third.metadata.getJSONObject("source_context").getBoolean("cache_hit"));

        JSONObject metrics = locator.metrics().json();
        Assert.assertEquals(3, metrics.getInt("ocr_request_count"));
        Assert.assertEquals(3, metrics.getInt("ocr_success_count"));
        Assert.assertEquals(1, metrics.getInt("ocr_cache_hit_count"));
    }

    @Test
    public void runtimeTimeoutMapsToStructuredOcrTimeoutAndDrainsInflight() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context target = instrumentation.getTargetContext();
        UiDevice device = UiDevice.getInstance(instrumentation);

        VisionTemplateLocator.Config config = new VisionTemplateLocator.Config(
                new JSONObject()
                        .put("enabled", true)
                        .put("mode", "fallback")
                        .put("ocr_enabled", true));
        OcrTextLocator locator = new OcrTextLocator(instrumentation, device, config);

        Method invokeRuntime = OcrTextLocator.class.getDeclaredMethod(
                "invokeRuntime", Bitmap.class, long.class);
        invokeRuntime.setAccessible(true);
        Bitmap bitmap = Bitmap.createBitmap(640, 512, Bitmap.Config.ARGB_8888);
        bitmap.eraseColor(Color.WHITE);
        try {
            try {
                invokeRuntime.invoke(locator, bitmap, 1L);
                Assert.fail("expected structured OCR timeout");
            } catch (InvocationTargetException expected) {
                Throwable cause = expected.getCause();
                Assert.assertTrue(cause instanceof VisionV0Harness.VisionFailure);
                VisionV0Harness.VisionFailure failure =
                        (VisionV0Harness.VisionFailure) cause;
                Assert.assertEquals(OcrTextLocator.ERR_TIMEOUT, failure.code);
            }

            long deadline = SystemClock.elapsedRealtime() + 10_000L;
            JSONObject status;
            do {
                status = locator.runtimeStatus();
                if (status.optInt("in_flight", 0) == 0) break;
                SystemClock.sleep(50L);
            } while (SystemClock.elapsedRealtime() < deadline);

            status = locator.runtimeStatus();
            Assert.assertEquals("native task must release its in-flight reference",
                    0, status.getInt("in_flight"));
            Assert.assertTrue("runtime timeout metric must increment",
                    status.getLong("timeout_count") >= 1L);
        } finally {
            bitmap.recycle();
        }
    }

    private static void prepareBenchmark(
            Instrumentation instrumentation,
            UiDevice device,
            String text) throws Exception {
        device.wakeUp();
        device.executeShellCommand("wm dismiss-keyguard");
        Context target = instrumentation.getTargetContext();
        Intent intent = new Intent();
        intent.setClassName(PACKAGE, PACKAGE + ".VisionBenchmarkActivity");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                Intent.FLAG_ACTIVITY_CLEAR_TOP |
                Intent.FLAG_ACTIVITY_SINGLE_TOP);
        intent.putExtra("ocr_text", text);
        intent.putExtra("clicked", false);
        intent.putExtra("duplicate", false);
        target.startActivity(intent);

        long deadline = SystemClock.elapsedRealtime() + 3000L;
        while (SystemClock.elapsedRealtime() < deadline) {
            if (PACKAGE.equals(device.getCurrentPackageName())) {
                SystemClock.sleep(250L);
                return;
            }
            SystemClock.sleep(100L);
        }
        Assert.fail("VisionBenchmarkActivity did not become foreground");
    }
}
