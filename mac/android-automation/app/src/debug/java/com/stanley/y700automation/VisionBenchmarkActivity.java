package com.stanley.y700automation;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.Bundle;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.accessibility.AccessibilityEvent;
import android.widget.Button;
import android.widget.FrameLayout;

public class VisionBenchmarkActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setShowWhenLocked(true);
        setTurnScreenOn(true);
        setTitle("Vision Benchmark");
        render(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        render(intent);
    }

    private void render(Intent intent) {
        FrameLayout root = new FrameLayout(this);
        BenchmarkView benchmark = new BenchmarkView(intent);
        root.addView(benchmark, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT));

        if (intent != null && intent.getBooleanExtra("popup", false)) {
            FrameLayout overlay = new FrameLayout(this);
            overlay.setBackgroundColor(Color.rgb(12, 14, 18));
            overlay.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);

            Button dismiss = new Button(this);
            dismiss.setText("Dismiss");
            dismiss.setContentDescription("VISION_V3_POPUP_DISMISS");
            dismiss.setOnClickListener(v -> root.removeView(overlay));
            FrameLayout.LayoutParams button = new FrameLayout.LayoutParams(
                    Math.round(220f * getResources().getDisplayMetrics().density),
                    Math.round(72f * getResources().getDisplayMetrics().density));
            button.gravity = Gravity.CENTER;
            overlay.addView(dismiss, button);
            root.addView(overlay, new FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT));
        }
        setContentView(root);
    }

    final class BenchmarkView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF target = new RectF();
        private final RectF duplicateTarget = new RectF();
        private final boolean duplicate;
        private final String ocrText;
        private final boolean staleVariant;
        private final boolean trackClickCount;
        private boolean clicked;
        private int targetClickCount;

        BenchmarkView(Intent intent) {
            super(VisionBenchmarkActivity.this);
            Intent source = intent == null ? new Intent() : intent;
            duplicate = source.getBooleanExtra("duplicate", false);
            ocrText = source.getStringExtra("ocr_text");
            clicked = source.getBooleanExtra("clicked", false);
            staleVariant = source.getBooleanExtra("stale_variant", false);
            trackClickCount = source.getBooleanExtra("track_click_count", false);
            targetClickCount = clicked ? 1 : 0;
            // The visible target itself is drawn on Canvas and has no semantic
            // child. The parent view becomes semantically identifiable only
            // after a successful click so V1/V3 use the shared postcondition.
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
            updateContentDescription();
            setBackgroundColor(staleVariant
                    ? Color.rgb(52, 39, 62)
                    : VisionBenchmarkPattern.BG_COLOR);
        }

        private void updateContentDescription() {
            if (!clicked) {
                setContentDescription(null);
                return;
            }
            if (trackClickCount) {
                setContentDescription("VISION_V3_CLICKED_COUNT_" + targetClickCount);
            } else {
                setContentDescription("VISION_V1_CLICKED");
            }
        }

        private void updateTargets() {
            float d = getResources().getDisplayMetrics().density;
            float w = VisionBenchmarkPattern.TARGET_WIDTH_DP * d;
            float h = VisionBenchmarkPattern.TARGET_HEIGHT_DP * d;
            float cy = getHeight() * 0.46f;
            float cx = getWidth() * 0.72f;
            target.set(cx - w / 2f, cy - h / 2f, cx + w / 2f, cy + h / 2f);

            float cx2 = getWidth() * 0.30f;
            duplicateTarget.set(
                    cx2 - w / 2f, cy - h / 2f, cx2 + w / 2f, cy + h / 2f);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            updateTargets();
            if (ocrText != null && !ocrText.isEmpty()) {
                drawOcrTarget(canvas, target, ocrText, clicked);
                if (duplicate) {
                    drawOcrTarget(canvas, duplicateTarget, ocrText, clicked);
                }
            } else {
                VisionBenchmarkPattern.drawTarget(canvas, target, clicked);
                if (duplicate) {
                    VisionBenchmarkPattern.drawTarget(canvas, duplicateTarget, clicked);
                }
            }

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.LTGRAY);
            paint.setTextSize(34f * getResources().getDisplayMetrics().scaledDensity);
            canvas.drawText(clicked ? "VISION_V1_CLICKED" : "VISION_V1_IDLE",
                    48f, 72f * getResources().getDisplayMetrics().density, paint);
        }

        private void drawOcrTarget(
                Canvas canvas,
                RectF rect,
                String text,
                boolean isClicked) {
            paint.setStyle(Paint.Style.FILL);
            paint.setColor(isClicked ? Color.rgb(32, 180, 96) : Color.rgb(18, 20, 24));
            canvas.drawRoundRect(rect, 18f, 18f, paint);

            paint.setColor(Color.WHITE);
            paint.setTextAlign(Paint.Align.CENTER);
            paint.setTextSize(rect.height() * 0.50f);
            Paint.FontMetrics fm = paint.getFontMetrics();
            float baseline = rect.centerY() - (fm.ascent + fm.descent) / 2f;
            canvas.drawText(text, rect.centerX(), baseline, paint);
            paint.setTextAlign(Paint.Align.LEFT);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (event.getAction() == MotionEvent.ACTION_UP) {
                updateTargets();
                if (target.contains(event.getX(), event.getY()) ||
                        (duplicate && duplicateTarget.contains(event.getX(), event.getY()))) {
                    clicked = true;
                    targetClickCount++;
                    updateContentDescription();
                    sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
                    invalidate();
                    return true;
                }
            }
            return true;
        }
    }
}
