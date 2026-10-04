package com.stanley.y700automation;

import android.app.Activity;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.accessibility.AccessibilityEvent;

public class VisionBenchmarkActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle("Vision Benchmark");
        setContentView(new BenchmarkView());
    }

    final class BenchmarkView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF target = new RectF();
        private final RectF duplicateTarget = new RectF();
        private final boolean duplicate;
        private boolean clicked = false;

        BenchmarkView() {
            super(VisionBenchmarkActivity.this);
            duplicate = getIntent().getBooleanExtra("duplicate", false);
            // The visible target itself is drawn on Canvas and has no semantic
            // child. The parent view becomes semantically identifiable only
            // after a successful click so V1 can use the shared semantic
            // postcondition path.
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_YES);
            setContentDescription(null);
            setBackgroundColor(VisionBenchmarkPattern.BG_COLOR);
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
            VisionBenchmarkPattern.drawTarget(canvas, target, clicked);
            if (duplicate) {
                VisionBenchmarkPattern.drawTarget(canvas, duplicateTarget, clicked);
            }

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.LTGRAY);
            paint.setTextSize(34f * getResources().getDisplayMetrics().scaledDensity);
            canvas.drawText(clicked ? "VISION_V1_CLICKED" : "VISION_V1_IDLE",
                    48f, 72f * getResources().getDisplayMetrics().density, paint);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (event.getAction() == MotionEvent.ACTION_UP) {
                updateTargets();
                if (target.contains(event.getX(), event.getY()) ||
                        (duplicate && duplicateTarget.contains(event.getX(), event.getY()))) {
                    clicked = true;
                    setContentDescription("VISION_V1_CLICKED");
                    sendAccessibilityEvent(AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED);
                    invalidate();
                    return true;
                }
            }
            return true;
        }
    }
}
