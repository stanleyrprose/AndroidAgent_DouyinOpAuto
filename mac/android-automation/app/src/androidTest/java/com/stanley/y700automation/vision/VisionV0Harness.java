package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Rect;
import android.graphics.RectF;
import android.os.Debug;
import android.os.ParcelFileDescriptor;
import android.os.SystemClock;

import androidx.test.uiautomator.UiDevice;

import com.stanley.y700automation.VisionBenchmarkPattern;

import org.json.JSONArray;
import org.json.JSONObject;
import org.opencv.android.Utils;
import org.opencv.core.Core;
import org.opencv.core.CvType;
import org.opencv.core.Mat;
import org.opencv.core.MatOfDouble;
import org.opencv.core.Point;
import org.opencv.core.Scalar;
import org.opencv.imgproc.Imgproc;

import java.io.ByteArrayOutputStream;
import java.io.FileInputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

public final class VisionV0Harness {
    public static final String ERR_CAPTURE_FAILED = "VISION_CAPTURE_FAILED";
    public static final String ERR_INVALID_ROI = "VISION_INVALID_ROI";
    public static final String ERR_TEMPLATE_CONFIG = "VISION_TEMPLATE_CONFIG_INVALID";
    public static final String ERR_TEMPLATE_NOT_FOUND = "VISION_TEMPLATE_NOT_FOUND";
    public static final String ERR_TEMPLATE_AMBIGUOUS = "VISION_TEMPLATE_AMBIGUOUS";
    public static final String ERR_ROTATION_MISMATCH = "VISION_ROTATION_MISMATCH";
    public static final String ERR_STALE_TARGET = "VISION_STALE_TARGET";
    public static final String ERR_UNSUPPORTED_FRAME = "VISION_UNSUPPORTED_FRAME_FORMAT";
    public static final String ERR_OOM_THROTTLED = "VISION_OOM_THROTTLED";

    private static final AtomicLong GENERATION = new AtomicLong();
    private static final AtomicInteger ACTIVE_FRAMES = new AtomicInteger();
    private static final AtomicInteger MAX_ACTIVE_FRAMES = new AtomicInteger();
    private static final AtomicInteger CAPTURE_RETRY_COUNT = new AtomicInteger();
    private static final int MAX_DIMENSION = 8192;
    private static final int MAX_SCALE_SAMPLES = 64;

    private VisionV0Harness() {}

    public static final class VisionFailure extends Exception {
        public final String code;
        public VisionFailure(String code, String message) {
            super(message);
            this.code = code;
        }
    }

    public static final class Frame implements AutoCloseable {
        public final Bitmap bitmap;
        public final int width;
        public final int height;
        public final int rotation;
        public final long capturedAtNs;
        public final long generation;
        public final long fingerprint;
        public final String packageName;
        public final String activityName;
        private boolean closed;

        Frame(Bitmap bitmap, int rotation) {
            this(bitmap, rotation, null, null);
        }

        Frame(Bitmap bitmap, int rotation, String packageName, String activityName) {
            this.bitmap = bitmap;
            this.width = bitmap.getWidth();
            this.height = bitmap.getHeight();
            this.rotation = rotation;
            this.capturedAtNs = SystemClock.elapsedRealtimeNanos();
            this.generation = GENERATION.incrementAndGet();
            this.fingerprint = fingerprint(bitmap);
            this.packageName = packageName;
            this.activityName = activityName;
            int active = ACTIVE_FRAMES.incrementAndGet();
            MAX_ACTIVE_FRAMES.accumulateAndGet(active, Math::max);
        }

        @Override
        public void close() {
            if (!closed) {
                closed = true;
                if (!bitmap.isRecycled()) bitmap.recycle();
                ACTIVE_FRAMES.decrementAndGet();
            }
        }

        public JSONObject metadata() throws Exception {
            return new JSONObject()
                    .put("width", width)
                    .put("height", height)
                    .put("display_rotation", rotation)
                    .put("captured_at_monotonic_ns", capturedAtNs)
                    .put("screen_generation", generation)
                    .put("fingerprint", Long.toUnsignedString(fingerprint))
                    .put("package", packageName == null ? JSONObject.NULL : packageName)
                    .put("activity", activityName == null ? JSONObject.NULL : activityName);
        }
    }

    public static final class VisionTarget {
        public final Rect bbox;
        public final int centerX;
        public final int centerY;
        public final double confidence;
        public final double secondBest;
        public final int rotation;
        public final int frameWidth;
        public final int frameHeight;
        public final long frameGeneration;
        public final long frameFingerprint;
        public final String source;
        public final String method;
        public final double variance;
        public final double scale;

        VisionTarget(
                Rect bbox,
                double confidence,
                double secondBest,
                Frame frame,
                String method,
                double variance,
                double scale) {
            this.bbox = bbox;
            this.centerX = bbox.centerX();
            this.centerY = bbox.centerY();
            this.confidence = confidence;
            this.secondBest = secondBest;
            this.rotation = frame.rotation;
            this.frameWidth = frame.width;
            this.frameHeight = frame.height;
            this.frameGeneration = frame.generation;
            this.frameFingerprint = frame.fingerprint;
            this.source = "vision_template";
            this.method = method;
            this.variance = variance;
            this.scale = scale;
        }

        public JSONObject json() throws Exception {
            return new JSONObject()
                    .put("bbox", new JSONArray()
                            .put(bbox.left).put(bbox.top).put(bbox.right).put(bbox.bottom))
                    .put("center", new JSONArray().put(centerX).put(centerY))
                    .put("source", source)
                    .put("confidence", confidence)
                    .put("screen_generation", frameGeneration)
                    .put("source_context", new JSONObject()
                            .put("method", method)
                            .put("scale", scale)
                            .put("second_best", secondBest)
                            .put("candidate_variance", variance));
        }
    }

    public static void resetCounters() {
        MAX_ACTIVE_FRAMES.set(ACTIVE_FRAMES.get());
        CAPTURE_RETRY_COUNT.set(0);
    }

    public static int maxActiveFrames() {
        return MAX_ACTIVE_FRAMES.get();
    }

    public static int captureRetryCount() {
        return CAPTURE_RETRY_COUNT.get();
    }

    public static long managedHeapUsed() {
        Runtime r = Runtime.getRuntime();
        return r.totalMemory() - r.freeMemory();
    }

    public static long nativeHeapUsed() {
        return Debug.getNativeHeapAllocatedSize();
    }

    public static Frame capture(
            Instrumentation instrumentation,
            UiDevice device,
            AtomicInteger injectedFailures,
            long managedHeapWatermarkBytes) throws VisionFailure {
        if (managedHeapWatermarkBytes > 0 && managedHeapUsed() >= managedHeapWatermarkBytes) {
            throw new VisionFailure(ERR_OOM_THROTTLED,
                    "managed heap watermark reached before capture");
        }

        Throwable last = null;
        for (int attempt = 0; attempt < 2; attempt++) {
            try {
                if (injectedFailures != null && injectedFailures.getAndUpdate(v -> Math.max(0, v - 1)) > 0) {
                    throw new IllegalStateException("injected capture failure");
                }
                Bitmap bitmap = instrumentation.getUiAutomation().takeScreenshot();
                if (bitmap == null || bitmap.getWidth() <= 0 || bitmap.getHeight() <= 0) {
                    throw new IllegalStateException("null/invalid screenshot");
                }
                return new Frame(
                        bitmap,
                        device.getDisplayRotation(),
                        device.getCurrentPackageName(),
                        null);
            } catch (Throwable t) {
                last = t;
                if (attempt == 0) {
                    CAPTURE_RETRY_COUNT.incrementAndGet();
                    SystemClock.sleep(50L);
                }
            }
        }
        throw new VisionFailure(ERR_CAPTURE_FAILED,
                "capture failed after exactly one retry: " +
                        (last == null ? "unknown" : last.getClass().getSimpleName()));
    }

    public static byte[] captureRawScreencap(Instrumentation instrumentation) throws Exception {
        ParcelFileDescriptor pfd = instrumentation.getUiAutomation().executeShellCommand("screencap");
        if (pfd == null) throw new VisionFailure(ERR_CAPTURE_FAILED, "screencap returned null fd");
        try (ParcelFileDescriptor ignored = pfd;
             FileInputStream in = new FileInputStream(pfd.getFileDescriptor());
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[64 * 1024];
            int n;
            while ((n = in.read(buf)) >= 0) {
                if (n > 0) out.write(buf, 0, n);
            }
            return out.toByteArray();
        }
    }

    public static JSONObject parseRawScreencap(byte[] raw) throws VisionFailure {
        JSONObject current = tryParseRaw(raw, 16, "ANDROID_4FIELD_V1", true);
        if (current != null) return current;
        JSONObject legacy = tryParseRaw(raw, 12, "LEGACY_3FIELD", false);
        if (legacy != null) return legacy;
        throw new VisionFailure(ERR_UNSUPPORTED_FRAME,
                "raw screencap did not match an explicitly supported profile");
    }

    private static JSONObject tryParseRaw(
            byte[] raw, int headerBytes, String profile, boolean hasDataspace) {
        try {
            if (raw == null || raw.length <= headerBytes) return null;
            ByteBuffer b = ByteBuffer.wrap(raw).order(ByteOrder.LITTLE_ENDIAN);
            int width = b.getInt();
            int height = b.getInt();
            int pixelFormat = b.getInt();
            int dataspace = hasDataspace ? b.getInt() : 0;
            if (width <= 0 || height <= 0 || width > MAX_DIMENSION || height > MAX_DIMENSION) {
                return null;
            }
            int bpp = bytesPerPixel(pixelFormat);
            if (bpp == 0) return null;
            long payload = raw.length - (long) headerBytes;
            long minRow = (long) width * bpp;
            long minPayload = minRow * height;
            if (payload < minPayload || payload % height != 0) return null;
            long rowBytes = payload / height;
            if (rowBytes < minRow || rowBytes > (long) MAX_DIMENSION * 8L) return null;
            return new JSONObject()
                    .put("profile", profile)
                    .put("header_bytes", headerBytes)
                    .put("width", width)
                    .put("height", height)
                    .put("pixel_format", pixelFormat)
                    .put("dataspace", hasDataspace ? dataspace : JSONObject.NULL)
                    .put("bytes_per_pixel", bpp)
                    .put("row_bytes", rowBytes)
                    .put("payload_bytes", payload)
                    .put("total_bytes", raw.length)
                    .put("tightly_packed", rowBytes == minRow);
        } catch (Throwable ignored) {
            return null;
        }
    }

    private static int bytesPerPixel(int pixelFormat) {
        switch (pixelFormat) {
            case 1: // RGBA_8888
            case 2: // RGBX_8888
            case 5: // BGRA_8888 on some platform paths
                return 4;
            case 3: // RGB_888
                return 3;
            case 4: // RGB_565
                return 2;
            default:
                return 0;
        }
    }

    public static Rect resolveRoi(
            int width,
            int height,
            int[] roi,
            double[] roiRatio) throws VisionFailure {
        if (roi != null && roiRatio != null) {
            throw new VisionFailure(ERR_INVALID_ROI, "roi and roi_ratio are mutually exclusive");
        }
        if (roi != null) {
            if (roi.length != 4) throw new VisionFailure(ERR_INVALID_ROI, "roi must have 4 entries");
            Rect r = new Rect(roi[0], roi[1], roi[2], roi[3]);
            validateRoi(width, height, r);
            return r;
        }
        if (roiRatio != null) {
            if (roiRatio.length != 4) {
                throw new VisionFailure(ERR_INVALID_ROI, "roi_ratio must have 4 entries");
            }
            for (double v : roiRatio) {
                if (!Double.isFinite(v) || v < 0.0 || v > 1.0) {
                    throw new VisionFailure(ERR_INVALID_ROI, "roi_ratio values must be within [0,1]");
                }
            }
            if (!(roiRatio[0] < roiRatio[2] && roiRatio[1] < roiRatio[3])) {
                throw new VisionFailure(ERR_INVALID_ROI, "roi_ratio must define positive area");
            }
            Rect r = new Rect(
                    (int) Math.floor(width * roiRatio[0]),
                    (int) Math.floor(height * roiRatio[1]),
                    (int) Math.ceil(width * roiRatio[2]),
                    (int) Math.ceil(height * roiRatio[3]));
            r.right = Math.min(width, r.right);
            r.bottom = Math.min(height, r.bottom);
            validateRoi(width, height, r);
            return r;
        }
        return new Rect(0, 0, width, height);
    }

    private static void validateRoi(int width, int height, Rect r) throws VisionFailure {
        if (r.left < 0 || r.top < 0 || r.right > width || r.bottom > height ||
                r.left >= r.right || r.top >= r.bottom) {
            throw new VisionFailure(ERR_INVALID_ROI,
                    String.format(Locale.US, "invalid roi=%s frame=%dx%d", r, width, height));
        }
    }

    public static List<Double> deterministicScales(
            double min, double max, double step) throws VisionFailure {
        if (!Double.isFinite(min) || !Double.isFinite(max) || !Double.isFinite(step) ||
                min <= 0.0 || max <= 0.0 || step <= 0.0 || min > max) {
            throw new VisionFailure(ERR_TEMPLATE_CONFIG, "invalid min/max/step");
        }
        List<Double> out = new ArrayList<>();
        double eps = 1e-9;
        for (double v = min; v <= max + eps; v += step) {
            if (out.size() >= MAX_SCALE_SAMPLES) {
                throw new VisionFailure(ERR_TEMPLATE_CONFIG, "scale sample limit exceeded");
            }
            double x = v > max ? max : v;
            if (out.isEmpty() || Math.abs(out.get(out.size() - 1) - x) > eps) out.add(x);
            if (x >= max - eps) break;
        }
        if (out.isEmpty() || Math.abs(out.get(out.size() - 1) - max) > eps) {
            if (out.size() >= MAX_SCALE_SAMPLES) {
                throw new VisionFailure(ERR_TEMPLATE_CONFIG, "scale sample limit exceeded");
            }
            out.add(max);
        } else {
            out.set(out.size() - 1, max);
        }
        return Collections.unmodifiableList(out);
    }

    public static Bitmap makeBenchmarkTemplate(
            android.content.Context context,
            boolean clicked,
            boolean alpha) {
        float d = context.getResources().getDisplayMetrics().density;
        int targetW = Math.max(1, Math.round(VisionBenchmarkPattern.TARGET_WIDTH_DP * d));
        int targetH = Math.max(1, Math.round(VisionBenchmarkPattern.TARGET_HEIGHT_DP * d));
        int margin = Math.max(8, Math.round(8f * d));
        Bitmap b = Bitmap.createBitmap(
                targetW + margin * 2,
                targetH + margin * 2,
                Bitmap.Config.ARGB_8888);
        Canvas c = new Canvas(b);
        if (!alpha) c.drawColor(VisionBenchmarkPattern.BG_COLOR);
        RectF target = new RectF(margin, margin, margin + targetW, margin + targetH);
        VisionBenchmarkPattern.drawTarget(c, target, clicked);
        return b;
    }

    public static VisionTarget matchTemplate(
            Frame frame,
            Bitmap template,
            Rect roi,
            boolean useAlphaMask,
            double minConfidence,
            double minVariance,
            double minSecondBestDelta) throws Exception {
        if (template == null || template.isRecycled()) {
            throw new VisionFailure(ERR_TEMPLATE_CONFIG, "template unavailable");
        }
        if (roi.width() < template.getWidth() || roi.height() < template.getHeight()) {
            throw new VisionFailure(ERR_TEMPLATE_CONFIG, "template larger than roi");
        }
        double templateVariance = bitmapVariance(template, useAlphaMask);
        if (!Double.isFinite(templateVariance) || templateVariance < minVariance) {
            throw new VisionFailure(ERR_TEMPLATE_NOT_FOUND,
                    String.format(Locale.US,
                            "template low-information variance=%.5f", templateVariance));
        }

        Mat frameMat = new Mat();
        Mat templateMat = new Mat();
        Mat roiMat = null;
        Mat result = null;
        Mat mask = null;
        Mat gray = null;
        Mat candidate = null;
        MatOfDouble mean = new MatOfDouble();
        MatOfDouble stddev = new MatOfDouble();
        try {
            Utils.bitmapToMat(frame.bitmap, frameMat);
            Utils.bitmapToMat(template, templateMat);
            roiMat = new Mat(frameMat, new org.opencv.core.Rect(
                    roi.left, roi.top, roi.width(), roi.height()));

            int method = useAlphaMask ? Imgproc.TM_CCORR_NORMED : Imgproc.TM_CCOEFF_NORMED;
            if (useAlphaMask) {
                List<Mat> channels = new ArrayList<>();
                Core.split(templateMat, channels);
                if (channels.size() < 4) {
                    for (Mat ch : channels) ch.release();
                    throw new VisionFailure(ERR_TEMPLATE_CONFIG, "alpha template has no alpha channel");
                }
                mask = channels.get(3);
                for (int i = 0; i < channels.size() - 1; i++) channels.get(i).release();
                Imgproc.threshold(mask, mask, 0.0, 255.0, Imgproc.THRESH_BINARY);
            }

            int rows = roiMat.rows() - templateMat.rows() + 1;
            int cols = roiMat.cols() - templateMat.cols() + 1;
            if (rows <= 0 || cols <= 0) {
                throw new VisionFailure(ERR_TEMPLATE_CONFIG, "invalid result geometry");
            }
            result = new Mat(rows, cols, CvType.CV_32FC1);
            if (useAlphaMask) {
                Imgproc.matchTemplate(roiMat, templateMat, result, method, mask);
            } else {
                Imgproc.matchTemplate(roiMat, templateMat, result, method);
            }

            Core.MinMaxLocResult mm = Core.minMaxLoc(result);
            double best = mm.maxVal;
            Point bestLoc = mm.maxLoc;

            Mat secondSearch = result.clone();
            // Suppress the full overlap neighborhood so second-best measures a
            // genuinely distinct candidate rather than a one-pixel shift of the winner.
            int suppressX0 = Math.max(0, (int) bestLoc.x - template.getWidth());
            int suppressY0 = Math.max(0, (int) bestLoc.y - template.getHeight());
            int suppressX1 = Math.min(secondSearch.cols(), (int) bestLoc.x + template.getWidth() + 1);
            int suppressY1 = Math.min(secondSearch.rows(), (int) bestLoc.y + template.getHeight() + 1);
            if (suppressX1 > suppressX0 && suppressY1 > suppressY0) {
                Mat suppressed = new Mat(secondSearch, new org.opencv.core.Rect(
                        suppressX0, suppressY0, suppressX1 - suppressX0, suppressY1 - suppressY0));
                suppressed.setTo(new Scalar(-1.0));
                suppressed.release();
            }
            double second = Core.minMaxLoc(secondSearch).maxVal;
            secondSearch.release();

            if (!Double.isFinite(best) || best < minConfidence) {
                throw new VisionFailure(ERR_TEMPLATE_NOT_FOUND,
                        String.format(Locale.US, "best=%.5f threshold=%.5f", best, minConfidence));
            }
            if (Double.isFinite(second) && best - second < minSecondBestDelta) {
                throw new VisionFailure(ERR_TEMPLATE_AMBIGUOUS,
                        String.format(Locale.US, "best=%.5f second=%.5f delta=%.5f",
                                best, second, best - second));
            }

            int left = roi.left + (int) Math.round(bestLoc.x);
            int top = roi.top + (int) Math.round(bestLoc.y);
            Rect bbox = new Rect(left, top, left + template.getWidth(), top + template.getHeight());
            candidate = new Mat(frameMat, new org.opencv.core.Rect(
                    bbox.left, bbox.top, bbox.width(), bbox.height()));
            gray = new Mat();
            Imgproc.cvtColor(candidate, gray, Imgproc.COLOR_RGBA2GRAY);
            Core.meanStdDev(gray, mean, stddev);
            double variance = Math.pow(stddev.get(0, 0)[0], 2.0);
            if (!Double.isFinite(variance) || variance < minVariance) {
                throw new VisionFailure(ERR_TEMPLATE_NOT_FOUND,
                        String.format(Locale.US, "candidate low-information variance=%.5f", variance));
            }
            return new VisionTarget(
                    bbox,
                    best,
                    second,
                    frame,
                    useAlphaMask ? "TM_CCORR_NORMED_MASKED" : "TM_CCOEFF_NORMED",
                    variance,
                    1.0);
        } finally {
            mean.release();
            stddev.release();
            if (candidate != null) candidate.release();
            if (gray != null) gray.release();
            if (mask != null) mask.release();
            if (result != null) result.release();
            if (roiMat != null) roiMat.release();
            templateMat.release();
            frameMat.release();
        }
    }

    public static VisionTarget matchTemplateMultiScale(
            Frame frame,
            Bitmap template,
            Rect roi,
            boolean useAlphaMask,
            List<Double> scales,
            double minConfidence,
            double minVariance,
            double minSecondBestDelta) throws Exception {
        if (scales == null || scales.isEmpty()) {
            throw new VisionFailure(ERR_TEMPLATE_CONFIG, "scale set must be non-empty");
        }

        VisionTarget best = null;
        for (double scale : scales) {
            if (!Double.isFinite(scale) || scale <= 0.0) {
                throw new VisionFailure(ERR_TEMPLATE_CONFIG, "scale must be finite and > 0");
            }
            int width = Math.max(1, (int) Math.round(template.getWidth() * scale));
            int height = Math.max(1, (int) Math.round(template.getHeight() * scale));
            if (width > roi.width() || height > roi.height()) {
                continue;
            }

            Bitmap scaled = Math.abs(scale - 1.0) < 1e-9
                    ? template
                    : Bitmap.createScaledBitmap(template, width, height, true);
            try {
                VisionTarget candidate = matchTemplate(
                        frame, scaled, roi, useAlphaMask,
                        0.0, minVariance, 0.0);
                if (best == null || candidate.confidence > best.confidence) {
                    best = new VisionTarget(
                            candidate.bbox,
                            candidate.confidence,
                            candidate.secondBest,
                            frame,
                            candidate.method + "_MULTISCALE",
                            candidate.variance,
                            scale);
                }
            } catch (VisionFailure e) {
                if (!ERR_TEMPLATE_NOT_FOUND.equals(e.code)) {
                    throw e;
                }
            } finally {
                if (scaled != template && !scaled.isRecycled()) {
                    scaled.recycle();
                }
            }
        }

        if (best == null || !Double.isFinite(best.confidence) ||
                best.confidence < minConfidence) {
            throw new VisionFailure(ERR_TEMPLATE_NOT_FOUND,
                    String.format(Locale.US, "multi-scale best below threshold=%.5f",
                            minConfidence));
        }
        if (Double.isFinite(best.secondBest) &&
                best.confidence - best.secondBest < minSecondBestDelta) {
            throw new VisionFailure(ERR_TEMPLATE_AMBIGUOUS,
                    String.format(Locale.US,
                            "multi-scale best=%.5f second=%.5f delta=%.5f scale=%.4f",
                            best.confidence, best.secondBest,
                            best.confidence - best.secondBest, best.scale));
        }
        return best;
    }

    public static void validatePreAction(
            VisionTarget target,
            int currentRotation,
            int currentWidth,
            int currentHeight,
            Long currentFingerprint) throws VisionFailure {
        if (target.rotation != currentRotation ||
                target.frameWidth != currentWidth ||
                target.frameHeight != currentHeight) {
            throw new VisionFailure(ERR_ROTATION_MISMATCH,
                    "target frame geometry changed before action");
        }
        if (currentFingerprint != null && currentFingerprint.longValue() != target.frameFingerprint) {
            throw new VisionFailure(ERR_STALE_TARGET,
                    "frame fingerprint changed before action");
        }
        if (target.centerX < 0 || target.centerY < 0 ||
                target.centerX >= currentWidth || target.centerY >= currentHeight) {
            throw new VisionFailure(ERR_STALE_TARGET, "target center outside current screen");
        }
    }

    public static Rect squareAround(int cx, int cy, int size, int width, int height) {
        int half = size / 2;
        int left = Math.max(0, cx - half);
        int top = Math.max(0, cy - half);
        int right = Math.min(width, left + size);
        int bottom = Math.min(height, top + size);
        left = Math.max(0, right - size);
        top = Math.max(0, bottom - size);
        return new Rect(left, top, right, bottom);
    }

    public static double unsafeMaskedBestScoreForBenchmark(Bitmap frame, Bitmap template) throws Exception {
        Mat frameMat = new Mat();
        Mat templateMat = new Mat();
        Mat mask = null;
        Mat result = null;
        try {
            Utils.bitmapToMat(frame, frameMat);
            Utils.bitmapToMat(template, templateMat);
            List<Mat> channels = new ArrayList<>();
            Core.split(templateMat, channels);
            if (channels.size() < 4) {
                for (Mat ch : channels) ch.release();
                throw new VisionFailure(ERR_TEMPLATE_CONFIG, "benchmark template has no alpha");
            }
            mask = channels.get(3);
            for (int i = 0; i < channels.size() - 1; i++) channels.get(i).release();
            Imgproc.threshold(mask, mask, 0.0, 255.0, Imgproc.THRESH_BINARY);
            result = new Mat(
                    frameMat.rows() - templateMat.rows() + 1,
                    frameMat.cols() - templateMat.cols() + 1,
                    CvType.CV_32FC1);
            Imgproc.matchTemplate(frameMat, templateMat, result, Imgproc.TM_CCORR_NORMED, mask);
            return Core.minMaxLoc(result).maxVal;
        } finally {
            if (result != null) result.release();
            if (mask != null) mask.release();
            templateMat.release();
            frameMat.release();
        }
    }

    public static double bitmapVariance(Bitmap bitmap, boolean alphaAware) {
        long n = 0L;
        double mean = 0.0;
        double m2 = 0.0;
        for (int y = 0; y < bitmap.getHeight(); y++) {
            for (int x = 0; x < bitmap.getWidth(); x++) {
                int c = bitmap.getPixel(x, y);
                if (alphaAware && Color.alpha(c) == 0) continue;
                double gray = (Color.red(c) * 77.0 + Color.green(c) * 150.0 +
                        Color.blue(c) * 29.0) / 256.0;
                n++;
                double delta = gray - mean;
                mean += delta / n;
                m2 += delta * (gray - mean);
            }
        }
        return n > 1 ? m2 / (n - 1) : 0.0;
    }

    private static long fingerprint(Bitmap b) {
        final int gx = 24;
        final int gy = 24;
        long h = 0xcbf29ce484222325L;
        for (int yy = 0; yy < gy; yy++) {
            int y = Math.min(b.getHeight() - 1, (int) ((yy + 0.5) * b.getHeight() / gy));
            for (int xx = 0; xx < gx; xx++) {
                int x = Math.min(b.getWidth() - 1, (int) ((xx + 0.5) * b.getWidth() / gx));
                int c = b.getPixel(x, y);
                int gray = (Color.red(c) * 77 + Color.green(c) * 150 + Color.blue(c) * 29) >> 8;
                h ^= (gray & 0xff);
                h *= 0x100000001b3L;
            }
        }
        return h;
    }

    public static JSONObject percentiles(List<Double> samples) throws Exception {
        if (samples.isEmpty()) return new JSONObject();
        ArrayList<Double> sorted = new ArrayList<>(samples);
        Collections.sort(sorted);
        return new JSONObject()
                .put("count", sorted.size())
                .put("p50_ms", percentile(sorted, 0.50))
                .put("p95_ms", percentile(sorted, 0.95))
                .put("min_ms", sorted.get(0))
                .put("max_ms", sorted.get(sorted.size() - 1));
    }

    private static double percentile(List<Double> sorted, double p) {
        if (sorted.size() == 1) return sorted.get(0);
        double pos = p * (sorted.size() - 1);
        int lo = (int) Math.floor(pos);
        int hi = (int) Math.ceil(pos);
        if (lo == hi) return sorted.get(lo);
        double f = pos - lo;
        return sorted.get(lo) * (1.0 - f) + sorted.get(hi) * f;
    }
}
