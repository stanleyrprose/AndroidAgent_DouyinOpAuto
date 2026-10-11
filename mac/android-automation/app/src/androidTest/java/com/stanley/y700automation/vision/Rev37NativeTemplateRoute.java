package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;

import androidx.test.uiautomator.UiDevice;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.security.MessageDigest;

/**
 * Rev3.7 independent versioned Create template bound to native screenshot.
 *
 * Template bytes originate ONLY from a packaged, reviewed Android test
 * asset with a hardcoded SHA-256 digest. No runtime request filename,
 * external screenshot crop, external download, OCR fallback, or caller
 * supplied confidence threshold can change the route.
 *
 * The real TikTok version-specific asset is NOT accepted. Until frozen
 * image bytes/hash, actual foreground contract and JIT threshold have
 * completed device review, all methods block without UI action.
 */
public final class Rev37NativeTemplateRoute {
    private static final String ASSET = "rev37/tiktok-create-icon-v1.png";
    private static final String EXPECTED_SHA256 = "";
    private static final boolean TEMPLATE_ACCEPTED = false;
    private static final double MATCH_CONFIDENCE = 0.90;
    private static final double MIN_VARIANCE = 8.0;
    private static final double MIN_SECOND_BEST_DELTA = 0.10;
    private static final int TEMPLATE_BYTES_MAX = 256 * 1024;
    private static final int TEMPLATE_DIMENSION_MAX = 512;

    private Rev37NativeTemplateRoute() {}

    public static final class Resolved implements AutoCloseable {
        public final JSONObject token;
        public final JSONObject locator;
        private final Rev37NativeFrameRegistry.IssuedFrame captured;

        private Resolved(Rev37NativeFrameRegistry.IssuedFrame captured,
                         JSONObject locator) {
            this.captured = captured;
            this.token = captured.token;
            this.locator = locator;
        }
        @Override public void close() {
            captured.close();
        }
    }

    private static String digest(byte[] bytes) throws Exception {
        byte[] encoded = MessageDigest.getInstance("SHA-256").digest(bytes);
        StringBuilder out = new StringBuilder();
        for (byte b : encoded) {
            out.append(Character.forDigit((b >>> 4) & 15, 16));
            out.append(Character.forDigit(b & 15, 16));
        }
        return out.toString();
    }

    private static Bitmap immutableTemplate(Instrumentation instrumentation)
            throws Exception {
        if (!TEMPLATE_ACCEPTED
                || !EXPECTED_SHA256.matches("[0-9a-f]{64}"))
            throw new IllegalStateException("TEMPLATE_CONTRACT_NOT_ACCEPTED");
        byte[] bytes;
        try (InputStream stream = instrumentation.getContext()
                .getAssets().open(ASSET);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = stream.read(buffer)) >= 0) {
                if (count > 0) output.write(buffer, 0, count);
                if (output.size() > TEMPLATE_BYTES_MAX)
                    throw new IllegalStateException("TEMPLATE_TOO_LARGE");
            }
            bytes = output.toByteArray();
        }
        if (bytes.length == 0 || !EXPECTED_SHA256.equals(digest(bytes)))
            throw new IllegalStateException("TEMPLATE_HASH_MISMATCH");
        Bitmap bitmap = BitmapFactory.decodeByteArray(
                bytes, 0, bytes.length);
        if (bitmap == null || bitmap.getWidth() <= 0
                || bitmap.getHeight() <= 0
                || bitmap.getWidth() > TEMPLATE_DIMENSION_MAX
                || bitmap.getHeight() > TEMPLATE_DIMENSION_MAX)
            throw new IllegalStateException("TEMPLATE_DIMENSIONS_INVALID");
        return bitmap;
    }

    public static Resolved resolveCreateReadOnly(
            Instrumentation instrumentation, UiDevice device)
            throws Exception {
        if (instrumentation == null || device == null)
            throw new IllegalStateException("NATIVE_ROUTE_UNAVAILABLE");
        VisionTemplateLocator.ensureOpenCvForNativeReadOnlyRoute(
                instrumentation);
        Bitmap template = immutableTemplate(instrumentation);
        try {
            Rect display = new Rect(
                    0, 0, device.getDisplayWidth(), device.getDisplayHeight());
            Rev37NativeFrameRegistry.IssuedFrame frame =
                    Rev37NativeFrameRegistry.captureReadOnly(
                            instrumentation, device, display);
            boolean success = false;
            try {
                VisionV0Harness.VisionTarget match =
                        VisionV0Harness.matchTemplate(
                                frame.frame, template, display,
                                false, MATCH_CONFIDENCE,
                                MIN_VARIANCE, MIN_SECOND_BEST_DELTA);
                // bindMatchedLocator independently verifies exact frame
                // generation/fingerprint and accepted route policy.
                JSONObject locator =
                        Rev37NativeFrameRegistry.bindMatchedLocator(
                                frame, match);
                success = true;
                return new Resolved(frame, locator);
            } finally {
                if (!success) frame.close();
            }
        } catch (Exception exc) {
            Rev37NativeFrameRegistry.invalidate();
            throw exc;
        } finally {
            if (!template.isRecycled()) template.recycle();
        }
    }

    public static boolean templateContractAccepted() {
        return TEMPLATE_ACCEPTED
                && EXPECTED_SHA256.matches("[0-9a-f]{64}");
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
