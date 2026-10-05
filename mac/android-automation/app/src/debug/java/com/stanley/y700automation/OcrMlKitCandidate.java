package com.stanley.y700automation;

import android.graphics.Bitmap;
import android.graphics.Point;
import android.graphics.Rect;
import android.os.SystemClock;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;

import org.json.JSONArray;
import org.json.JSONObject;

import java.lang.reflect.Method;
import java.util.Locale;
import java.util.concurrent.TimeUnit;

/**
 * Debug-only Sprint V2 benchmark adapter for bundled ML Kit OCR.
 *
 * Production routing is intentionally not wired here. V2 selects a runtime only
 * after real-Y700 benchmark evidence is accepted.
 */
public final class OcrMlKitCandidate implements AutoCloseable {
    private TextRecognizer latinRecognizer;
    private TextRecognizer chineseRecognizer;

    public synchronized boolean isLoaded(String script) {
        return "chinese".equals(script)
                ? chineseRecognizer != null
                : latinRecognizer != null;
    }

    private synchronized TextRecognizer recognizer(String script) {
        if ("chinese".equals(script)) {
            if (chineseRecognizer == null) {
                chineseRecognizer = TextRecognition.getClient(
                        new ChineseTextRecognizerOptions.Builder().build());
            }
            return chineseRecognizer;
        }
        if (latinRecognizer == null) {
            latinRecognizer = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
        }
        return latinRecognizer;
    }

    public JSONObject recognize(Bitmap bitmap, String script, long timeoutMs) throws Exception {
        if (bitmap == null || bitmap.isRecycled()) {
            throw new IllegalArgumentException("bitmap unavailable");
        }
        long started = SystemClock.elapsedRealtimeNanos();
        TextRecognizer recognizer = recognizer(script);
        Text result = Tasks.await(
                recognizer.process(InputImage.fromBitmap(bitmap, 0)),
                Math.max(250L, timeoutMs),
                TimeUnit.MILLISECONDS);
        double latencyMs = (SystemClock.elapsedRealtimeNanos() - started) / 1_000_000.0;

        JSONArray items = new JSONArray();
        for (Text.TextBlock block : result.getTextBlocks()) {
            for (Text.Line line : block.getLines()) {
                Rect bbox = line.getBoundingBox();
                if (bbox == null) continue;
                JSONObject item = new JSONObject()
                        .put("text", line.getText())
                        .put("bbox", rectJson(bbox))
                        .put("polygon", pointsJson(line.getCornerPoints()));
                Double confidence = reflectedConfidence(line);
                if (confidence == null) {
                    // Fall back to the mean element confidence when the concrete
                    // ML Kit artifact does not expose line confidence directly.
                    double total = 0.0;
                    int count = 0;
                    for (Text.Element element : line.getElements()) {
                        Double one = reflectedConfidence(element);
                        if (one != null && Double.isFinite(one)) {
                            total += one;
                            count++;
                        }
                    }
                    confidence = count == 0 ? null : total / count;
                }
                item.put("confidence", confidence == null ? JSONObject.NULL : confidence);
                items.put(item);
            }
        }
        return new JSONObject()
                .put("runtime", "mlkit-bundled")
                .put("script", script)
                .put("latency_ms", latencyMs)
                .put("text", result.getText())
                .put("items", items);
    }

    public synchronized void closeScript(String script) {
        if ("chinese".equals(script)) {
            if (chineseRecognizer != null) {
                chineseRecognizer.close();
                chineseRecognizer = null;
            }
        } else if (latinRecognizer != null) {
            latinRecognizer.close();
            latinRecognizer = null;
        }
    }

    @Override
    public synchronized void close() {
        if (latinRecognizer != null) {
            latinRecognizer.close();
            latinRecognizer = null;
        }
        if (chineseRecognizer != null) {
            chineseRecognizer.close();
            chineseRecognizer = null;
        }
    }

    private static JSONArray rectJson(Rect r) {
        return new JSONArray()
                .put(r.left)
                .put(r.top)
                .put(r.right)
                .put(r.bottom);
    }

    private static JSONArray pointsJson(Point[] points) {
        JSONArray out = new JSONArray();
        if (points == null) return out;
        for (Point p : points) {
            out.put(new JSONArray().put(p.x).put(p.y));
        }
        return out;
    }

    private static Double reflectedConfidence(Object value) {
        try {
            Method m = value.getClass().getMethod("getConfidence");
            Object out = m.invoke(value);
            if (out instanceof Number) {
                double d = ((Number) out).doubleValue();
                if (Double.isFinite(d)) return d;
            }
        } catch (Throwable ignored) {
            // Some ML Kit OCR artifacts do not expose confidence at every level.
        }
        return null;
    }

    public static String scriptForPattern(String pattern) {
        if (pattern == null) return "latin";
        for (int i = 0; i < pattern.length();) {
            int cp = pattern.codePointAt(i);
            Character.UnicodeScript script = Character.UnicodeScript.of(cp);
            if (script == Character.UnicodeScript.HAN) return "chinese";
            i += Character.charCount(cp);
        }
        return "latin";
    }

    public static String normalize(String text) {
        if (text == null) return "";
        return text.replaceAll("\\s+", "").toLowerCase(Locale.ROOT);
    }
}
