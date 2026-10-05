package com.stanley.y700automation;

import android.app.Instrumentation;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.os.Debug;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.UiDevice;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Sprint V2 real-device benchmark for bundled ML Kit OCR.
 *
 * Runtime-private screenshots/ground truth are staged into the target app by
 * tests/collect_ocr_v2_dataset.py. This test never performs input actions.
 */
@RunWith(AndroidJUnit4.class)
public final class OcrV2MlKitBenchmarkTest {
    private static final long OCR_TIMEOUT_MS = 5000L;

    @Test
    public void benchmarkRealAppDataset() throws Exception {
        Instrumentation instrumentation = InstrumentationRegistry.getInstrumentation();
        Context context = instrumentation.getTargetContext();
        UiDevice device = UiDevice.getInstance(instrumentation);

        File datasetDir = new File(context.getFilesDir(), "ocr-v2-dataset");
        File manifestFile = new File(datasetDir, "manifest.json");
        Assert.assertTrue("OCR V2 manifest missing: " + manifestFile, manifestFile.isFile());

        JSONObject manifest = new JSONObject(readUtf8(manifestFile));
        JSONArray screens = manifest.getJSONArray("screens");

        Debug.MemoryInfo memoryBefore = new Debug.MemoryInfo();
        Debug.getMemoryInfo(memoryBefore);
        long nativeBefore = Debug.getNativeHeapAllocatedSize();
        Double tempBefore = batteryTemperatureC(device);

        JSONArray targetResults = new JSONArray();
        Map<String, List<Double>> warmLatencies = new HashMap<>();
        Map<String, Double> coldLatencies = new HashMap<>();
        Map<String, Integer> scriptRequests = new HashMap<>();
        int total = 0;
        int located = 0;
        int matchedWithConfidence = 0;
        int recognizedLineCount = 0;

        OcrMlKitCandidate ocr = new OcrMlKitCandidate();
        try {
            for (int s = 0; s < screens.length(); s++) {
                JSONObject screen = screens.getJSONObject(s);
                String imageName = screen.getString("image");
                Bitmap full = BitmapFactory.decodeFile(new File(datasetDir, imageName).getAbsolutePath());
                Assert.assertNotNull("decode failed: " + imageName, full);
                try {
                    JSONArray targets = screen.getJSONArray("targets");
                    for (int i = 0; i < targets.length(); i++) {
                        JSONObject target = targets.getJSONObject(i);
                        JSONArray roiJson = target.getJSONArray("roi");
                        Rect roi = rect(roiJson);
                        roi.intersect(0, 0, full.getWidth(), full.getHeight());
                        if (roi.width() <= 1 || roi.height() <= 1) continue;

                        Bitmap crop = Bitmap.createBitmap(
                                full, roi.left, roi.top, roi.width(), roi.height());
                        JSONObject recognized;
                        String script = target.optString(
                                "script",
                                OcrMlKitCandidate.scriptForPattern(target.optString("text", "")));
                        boolean wasLoaded = ocr.isLoaded(script);
                        try {
                            recognized = ocr.recognize(crop, script, OCR_TIMEOUT_MS);
                        } finally {
                            crop.recycle();
                        }

                        double latency = recognized.getDouble("latency_ms");
                        scriptRequests.put(script, scriptRequests.getOrDefault(script, 0) + 1);
                        if (!wasLoaded && !coldLatencies.containsKey(script)) {
                            coldLatencies.put(script, latency);
                        } else {
                            warmLatencies.computeIfAbsent(script, key -> new ArrayList<>())
                                    .add(latency);
                        }

                        JSONArray items = recognized.getJSONArray("items");
                        recognizedLineCount += items.length();
                        JSONObject score = scoreTarget(target, items, roi.left, roi.top);
                        boolean pass = score.getBoolean("located");
                        if (pass) located++;
                        if (pass && !score.isNull("confidence")) matchedWithConfidence++;
                        total++;

                        targetResults.put(new JSONObject()
                                .put("screen_id", screen.getString("id"))
                                .put("target_index", i)
                                .put("script", script)
                                .put("located", pass)
                                .put("latency_ms", latency)
                                .put("confidence", score.opt("confidence"))
                                .put("recognized_text", score.optString("recognized_text", ""))
                                .put("bbox", score.opt("bbox")));
                    }
                } finally {
                    full.recycle();
                }
            }
        } finally {
            ocr.close();
        }

        System.gc();
        Thread.sleep(250L);
        Debug.MemoryInfo memoryAfter = new Debug.MemoryInfo();
        Debug.getMemoryInfo(memoryAfter);
        long nativeAfter = Debug.getNativeHeapAllocatedSize();
        Double tempAfter = batteryTemperatureC(device);

        double accuracy = total == 0 ? 0.0 : located / (double) total;
        JSONObject warm = new JSONObject();
        for (Map.Entry<String, List<Double>> entry : warmLatencies.entrySet()) {
            warm.put(entry.getKey(), summarize(entry.getValue()));
        }
        JSONObject cold = new JSONObject();
        for (Map.Entry<String, Double> entry : coldLatencies.entrySet()) {
            cold.put(entry.getKey(), entry.getValue());
        }

        JSONObject result = new JSONObject()
                .put("schema_version", 1)
                .put("candidate", "mlkit-bundled")
                .put("dataset_created_at", manifest.optString("created_at"))
                .put("target_count", total)
                .put("located_count", located)
                .put("target_location_accuracy", accuracy)
                .put("confidence_available_count", matchedWithConfidence)
                .put("confidence_coverage",
                        located == 0 ? 0.0 : matchedWithConfidence / (double) located)
                .put("recognized_line_count", recognizedLineCount)
                .put("script_requests", new JSONObject(scriptRequests))
                .put("cold_latency_ms", cold)
                .put("warm_latency_ms", warm)
                .put("memory", new JSONObject()
                        .put("pss_before_kb", memoryBefore.getTotalPss())
                        .put("pss_after_kb", memoryAfter.getTotalPss())
                        .put("pss_delta_kb",
                                memoryAfter.getTotalPss() - memoryBefore.getTotalPss())
                        .put("native_before_bytes", nativeBefore)
                        .put("native_after_bytes", nativeAfter)
                        .put("native_delta_bytes", nativeAfter - nativeBefore))
                .put("thermal", new JSONObject()
                        .put("before_c", tempBefore == null ? JSONObject.NULL : tempBefore)
                        .put("after_c", tempAfter == null ? JSONObject.NULL : tempAfter)
                        .put("delta_c",
                                tempBefore == null || tempAfter == null
                                        ? JSONObject.NULL
                                        : tempAfter - tempBefore))
                .put("targets", targetResults);

        File outDir = new File(context.getFilesDir(), "ocr-v2-results");
        Assert.assertTrue(outDir.mkdirs() || outDir.isDirectory());
        File out = new File(outDir, "mlkit-bundled.json");
        try (FileOutputStream stream = new FileOutputStream(out)) {
            stream.write((result.toString(2) + "\n").getBytes(StandardCharsets.UTF_8));
        }

        System.out.println("[OCRV2] result=" + out.getAbsolutePath());
        System.out.println("[OCRV2] candidate=mlkit-bundled targets=" + total
                + " located=" + located
                + " accuracy=" + String.format(Locale.ROOT, "%.4f", accuracy)
                + " confidenceCoverage="
                + String.format(Locale.ROOT, "%.4f",
                        located == 0 ? 0.0 : matchedWithConfidence / (double) located));
        System.out.println("[OCRV2] cold=" + cold);
        System.out.println("[OCRV2] warm=" + warm);
        System.out.println("[OCRV2] thermal=" + result.getJSONObject("thermal"));
        System.out.println("[OCRV2] memory=" + result.getJSONObject("memory"));

        Assert.assertTrue("dataset unexpectedly empty", total >= 20);
    }

    private static JSONObject scoreTarget(
            JSONObject target,
            JSONArray items,
            int offsetX,
            int offsetY) throws Exception {
        String expected = OcrMlKitCandidate.normalize(target.getString("text"));
        Rect gt = rect(target.getJSONArray("bbox"));
        Rect expanded = new Rect(gt);
        expanded.inset(-24, -24);

        JSONObject best = null;
        double bestGeom = -1.0;
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.getJSONObject(i);
            String observed = OcrMlKitCandidate.normalize(item.optString("text", ""));
            if (observed.isEmpty() || expected.isEmpty()) continue;
            boolean textMatch = observed.equals(expected) || observed.contains(expected);
            if (!textMatch) continue;

            Rect local = rect(item.getJSONArray("bbox"));
            Rect global = new Rect(
                    local.left + offsetX,
                    local.top + offsetY,
                    local.right + offsetX,
                    local.bottom + offsetY);
            int cx = global.centerX();
            int cy = global.centerY();
            if (!expanded.contains(cx, cy)) continue;

            double geom = intersectionOverMinArea(global, gt);
            if (geom > bestGeom) {
                bestGeom = geom;
                best = new JSONObject()
                        .put("located", true)
                        .put("recognized_text", item.optString("text", ""))
                        .put("bbox", new JSONArray()
                                .put(global.left).put(global.top)
                                .put(global.right).put(global.bottom))
                        .put("confidence", item.opt("confidence"))
                        .put("geometry_score", geom);
            }
        }
        if (best != null) return best;
        return new JSONObject()
                .put("located", false)
                .put("recognized_text", "")
                .put("bbox", JSONObject.NULL)
                .put("confidence", JSONObject.NULL)
                .put("geometry_score", 0.0);
    }

    private static double intersectionOverMinArea(Rect a, Rect b) {
        int left = Math.max(a.left, b.left);
        int top = Math.max(a.top, b.top);
        int right = Math.min(a.right, b.right);
        int bottom = Math.min(a.bottom, b.bottom);
        if (right <= left || bottom <= top) return 0.0;
        double intersection = (double) (right - left) * (bottom - top);
        double minArea = Math.min(
                (double) a.width() * a.height(),
                (double) b.width() * b.height());
        return minArea <= 0.0 ? 0.0 : intersection / minArea;
    }

    private static JSONObject summarize(List<Double> values) throws Exception {
        if (values == null || values.isEmpty()) return new JSONObject();
        List<Double> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        double sum = 0.0;
        for (double v : sorted) sum += v;
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
        double idx = q * (sorted.size() - 1);
        int lo = (int) Math.floor(idx);
        int hi = (int) Math.ceil(idx);
        if (lo == hi) return sorted.get(lo);
        double frac = idx - lo;
        return sorted.get(lo) * (1.0 - frac) + sorted.get(hi) * frac;
    }

    private static Rect rect(JSONArray a) {
        return new Rect(
                a.optInt(0),
                a.optInt(1),
                a.optInt(2),
                a.optInt(3));
    }

    private static String readUtf8(File file) throws Exception {
        byte[] data = new byte[(int) file.length()];
        try (FileInputStream in = new FileInputStream(file)) {
            int offset = 0;
            while (offset < data.length) {
                int n = in.read(data, offset, data.length - offset);
                if (n < 0) break;
                offset += n;
            }
        }
        return new String(data, StandardCharsets.UTF_8);
    }

    private static Double batteryTemperatureC(UiDevice device) {
        try {
            String out = device.executeShellCommand("dumpsys battery");
            for (String line : out.split("\n")) {
                String trimmed = line.trim();
                if (trimmed.startsWith("temperature:")) {
                    String raw = trimmed.substring("temperature:".length()).trim();
                    return Integer.parseInt(raw) / 10.0;
                }
            }
        } catch (Throwable ignored) {
        }
        return null;
    }
}
