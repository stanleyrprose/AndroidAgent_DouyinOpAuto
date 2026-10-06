package com.stanley.y700automation.vision;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import android.os.SystemClock;

import androidx.test.platform.app.InstrumentationRegistry;

import com.stanley.y700automation.PersistentOcrV2TestBase;

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

/**
 * Canonical Sprint V2 real-app accuracy gate.
 *
 * Uses the target app's production OcrRuntimeBridge plus the same normalization,
 * min-confidence and two-stage inference-context policy as OcrTextLocator. Ground
 * truth comes only from the runtime-private approved Settings dataset.
 */
public final class OcrV2RealDatasetBenchmarkTest extends PersistentOcrV2TestBase {
    private static final double MIN_CONFIDENCE = 0.85;
    private static final int LOCATION_TOLERANCE_PX = 24;
    private static final int MIN_CONTEXT_HEIGHT_PX = 512;
    private static final long REQUEST_TIMEOUT_MS = 10_000L;

    @Test
    public void cleanSettingsDatasetMeetsTargetLocationGate() throws Exception {
        Context target = InstrumentationRegistry.getInstrumentation().getTargetContext();
        File datasetDir = new File(target.getFilesDir(), "ocr-v2-dataset");
        File manifestFile = new File(datasetDir, "manifest.json");
        Assert.assertTrue("runtime-private OCR V2 manifest missing", manifestFile.isFile());

        JSONObject manifest = new JSONObject(new String(
                Files.readAllBytes(manifestFile.toPath()),
                StandardCharsets.UTF_8));
        JSONArray screens = manifest.getJSONArray("screens");

        Class<?> bridge = Class.forName(
                "com.stanley.y700automation.OcrRuntimeBridge",
                true,
                target.getClassLoader());
        Method recognize = bridge.getMethod(
                "recognize", Context.class, Bitmap.class, long.class);

        int total = 0;
        int located = 0;
        int contextRetries = 0;
        JSONArray failures = new JSONArray();
        List<Double> targetWallMs = new ArrayList<>();

        for (int si = 0; si < screens.length(); si++) {
            JSONObject screen = screens.getJSONObject(si);
            String screenId = screen.getString("id");
            File imageFile = new File(datasetDir, screen.getString("image"));
            Bitmap full = BitmapFactory.decodeFile(imageFile.getAbsolutePath());
            Assert.assertNotNull("unable to decode " + imageFile, full);
            try {
                Assert.assertEquals(screen.getInt("width"), full.getWidth());
                Assert.assertEquals(screen.getInt("height"), full.getHeight());
                JSONArray targets = screen.getJSONArray("targets");
                for (int ti = 0; ti < targets.length(); ti++) {
                    JSONObject groundTruth = targets.getJSONObject(ti);
                    Rect requestRoi = rect(groundTruth.getJSONArray("roi"));
                    Rect gtBox = rect(groundTruth.getJSONArray("bbox"));
                    String expected = groundTruth.getString("text");

                    long startedNs = SystemClock.elapsedRealtimeNanos();
                    Selection selection = recognizeAndSelect(
                            target, recognize, full, requestRoi, requestRoi, expected);

                    boolean retried = false;
                    if (selection.candidates.size() == 0) {
                        Rect expanded = OcrTextLocator.expandInferenceContext(
                                requestRoi,
                                full.getWidth(),
                                full.getHeight(),
                                MIN_CONTEXT_HEIGHT_PX);
                        if (!expanded.equals(requestRoi)) {
                            retried = true;
                            contextRetries++;
                            selection = recognizeAndSelect(
                                    target, recognize, full, requestRoi, expanded, expected);
                        }
                    }
                    double elapsedMs =
                            (SystemClock.elapsedRealtimeNanos() - startedNs) / 1_000_000.0;
                    targetWallMs.add(elapsedMs);
                    total++;

                    boolean correct = false;
                    Candidate candidate = null;
                    if (selection.candidates.size() == 1) {
                        candidate = selection.candidates.get(0);
                        Rect tolerated = new Rect(
                                Math.max(0, gtBox.left - LOCATION_TOLERANCE_PX),
                                Math.max(0, gtBox.top - LOCATION_TOLERANCE_PX),
                                Math.min(full.getWidth(), gtBox.right + LOCATION_TOLERANCE_PX),
                                Math.min(full.getHeight(), gtBox.bottom + LOCATION_TOLERANCE_PX));
                        correct = tolerated.contains(
                                candidate.bbox.centerX(), candidate.bbox.centerY());
                    }
                    if (correct) {
                        located++;
                    } else {
                        failures.put(new JSONObject()
                                .put("screen_id", screenId)
                                .put("target_index", ti)
                                .put("expected", expected)
                                .put("request_roi", rectJson(requestRoi))
                                .put("ground_truth_bbox", rectJson(gtBox))
                                .put("context_retry", retried)
                                .put("eligible_candidate_count", selection.candidates.size())
                                .put("recognized_text",
                                        candidate == null ? JSONObject.NULL : candidate.text)
                                .put("confidence",
                                        candidate == null ? JSONObject.NULL : candidate.confidence)
                                .put("recognized_bbox",
                                        candidate == null ? JSONObject.NULL : rectJson(candidate.bbox)));
                    }
                }
            } finally {
                full.recycle();
            }
        }

        double accuracy = total == 0 ? 0.0 : located / (double) total;
        JSONObject report = new JSONObject()
                .put("runtime", "paddle-ppocrv6-tiny-onnx")
                .put("dataset_kind", "clean-real-settings")
                .put("screen_count", screens.length())
                .put("target_count", total)
                .put("located_count", located)
                .put("target_location_accuracy", accuracy)
                .put("required_accuracy", 0.96)
                .put("min_confidence", MIN_CONFIDENCE)
                .put("location_tolerance_px", LOCATION_TOLERANCE_PX)
                .put("min_inference_context_height_px", MIN_CONTEXT_HEIGHT_PX)
                .put("context_retry_count", contextRetries)
                .put("target_wall_latency_ms", summarize(targetWallMs))
                .put("failures", failures);
        writePersistentArtifact("accuracy-report.json", report);

        Assert.assertEquals("approved clean dataset target count changed", 99, total);
        Assert.assertTrue(
                "target-location accuracy must be >= 96%, got " + accuracy,
                accuracy >= 0.96);
    }

    private static Selection recognizeAndSelect(
            Context context,
            Method recognize,
            Bitmap full,
            Rect requestRoi,
            Rect inferenceRoi,
            String expected) throws Exception {
        Bitmap crop = Bitmap.createBitmap(
                full,
                inferenceRoi.left,
                inferenceRoi.top,
                inferenceRoi.width(),
                inferenceRoi.height());
        JSONObject raw;
        try {
            raw = new JSONObject(String.valueOf(
                    recognize.invoke(null, context, crop, REQUEST_TIMEOUT_MS)));
        } finally {
            crop.recycle();
        }

        String normalizedExpected = OcrTextLocator.normalize(expected);
        JSONArray items = raw.optJSONArray("items");
        List<Candidate> candidates = new ArrayList<>();
        if (items == null) return new Selection(candidates);

        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null) continue;
            String text = item.optString("text", "");
            if (!OcrTextLocator.normalize(text).contains(normalizedExpected)) continue;

            double confidence = item.optDouble("confidence", Double.NaN);
            if (!Double.isFinite(confidence) || confidence < MIN_CONFIDENCE) continue;

            JSONArray localBox = item.optJSONArray("bbox");
            if (localBox == null || localBox.length() < 4) continue;
            Rect global = new Rect(
                    localBox.optInt(0) + inferenceRoi.left,
                    localBox.optInt(1) + inferenceRoi.top,
                    localBox.optInt(2) + inferenceRoi.left,
                    localBox.optInt(3) + inferenceRoi.top);
            if (global.width() <= 0 || global.height() <= 0) continue;
            if (global.left < requestRoi.left || global.top < requestRoi.top ||
                    global.right > requestRoi.right || global.bottom > requestRoi.bottom) {
                continue;
            }
            candidates.add(new Candidate(text, confidence, global));
        }
        return new Selection(candidates);
    }

    private static Rect rect(JSONArray raw) {
        return new Rect(
                raw.optInt(0),
                raw.optInt(1),
                raw.optInt(2),
                raw.optInt(3));
    }

    private static JSONArray rectJson(Rect rect) {
        return new JSONArray()
                .put(rect.left)
                .put(rect.top)
                .put(rect.right)
                .put(rect.bottom);
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

    private static final class Selection {
        final List<Candidate> candidates;
        Selection(List<Candidate> candidates) {
            this.candidates = candidates;
        }
    }

    private static final class Candidate {
        final String text;
        final double confidence;
        final Rect bbox;
        Candidate(String text, double confidence, Rect bbox) {
            this.text = text;
            this.confidence = confidence;
            this.bbox = bbox;
        }
    }
}
