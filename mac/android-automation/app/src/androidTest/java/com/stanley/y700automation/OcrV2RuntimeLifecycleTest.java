package com.stanley.y700automation;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.os.SystemClock;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;

import java.lang.reflect.Method;

public final class OcrV2RuntimeLifecycleTest extends PersistentOcrV2TestBase {
    @Test
    public void lazyLoadWarmReuseIdleUnloadAndReload() throws Exception {
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

        configure.invoke(null, 200L, 3000L);
        Bitmap bitmap = Bitmap.createBitmap(320, 160, Bitmap.Config.ARGB_8888);
        bitmap.eraseColor(Color.WHITE);
        try {
            JSONObject before = json(status.invoke(null));
            long initialLoads = before.optLong("load_count", 0L);
            long initialUnloads = before.optLong("unload_count", 0L);

            recognize.invoke(null, target, bitmap, 10_000L);
            JSONObject first = json(status.invoke(null));
            Assert.assertTrue(first.getBoolean("loaded"));
            Assert.assertEquals(0, first.getInt("in_flight"));
            Assert.assertEquals(initialLoads + 1L, first.getLong("load_count"));

            recognize.invoke(null, target, bitmap, 10_000L);
            JSONObject warm = json(status.invoke(null));
            Assert.assertEquals(first.getLong("load_count"), warm.getLong("load_count"));
            Assert.assertTrue(warm.getBoolean("loaded"));

            SystemClock.sleep(350L);
            JSONObject residency = json(status.invoke(null));
            Assert.assertTrue("minimum residency must prevent early unload",
                    residency.getBoolean("loaded"));

            SystemClock.sleep(3100L);
            JSONObject unloaded = json(status.invoke(null));
            Assert.assertFalse("runtime should unload after idle+minimum residency",
                    unloaded.getBoolean("loaded"));
            Assert.assertEquals(initialUnloads + 1L, unloaded.getLong("unload_count"));
            Assert.assertEquals(0, unloaded.getInt("in_flight"));

            recognize.invoke(null, target, bitmap, 10_000L);
            JSONObject reloaded = json(status.invoke(null));
            Assert.assertTrue(reloaded.getBoolean("loaded"));
            Assert.assertEquals(initialLoads + 2L, reloaded.getLong("load_count"));
        } finally {
            bitmap.recycle();
            reset.invoke(null);
        }
    }

    private static JSONObject json(Object raw) throws Exception {
        return new JSONObject(String.valueOf(raw));
    }
}
