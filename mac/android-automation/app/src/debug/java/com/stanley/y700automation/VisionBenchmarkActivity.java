package com.stanley.y700automation;

import android.app.Activity;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.graphics.Color;

public class VisionBenchmarkActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setTitle("Vision V0 Benchmark");
        setContentView(new BenchmarkView());
    }

    final class BenchmarkView extends View {
        private final Paint paint = new Paint(Paint.ANTI_ALIAS_FLAG);
        private final RectF target = new RectF();
        private boolean clicked = false;

        BenchmarkView() {
            super(VisionBenchmarkActivity.this);
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
            setBackgroundColor(VisionBenchmarkPattern.BG_COLOR);
        }

        private void updateTarget() {
            float d = getResources().getDisplayMetrics().density;
            float w = VisionBenchmarkPattern.TARGET_WIDTH_DP * d;
            float h = VisionBenchmarkPattern.TARGET_HEIGHT_DP * d;
            float cx = getWidth() * 0.72f;
            float cy = getHeight() * 0.46f;
            target.set(cx - w / 2f, cy - h / 2f, cx + w / 2f, cy + h / 2f);
        }

        @Override
        protected void onDraw(Canvas canvas) {
            super.onDraw(canvas);
            updateTarget();
            VisionBenchmarkPattern.drawTarget(canvas, target, clicked);

            paint.setStyle(Paint.Style.FILL);
            paint.setColor(Color.LTGRAY);
            paint.setTextSize(34f * getResources().getDisplayMetrics().scaledDensity);
            canvas.drawText(clicked ? "VISION_V0_CLICKED" : "VISION_V0_IDLE",
                    48f, 72f * getResources().getDisplayMetrics().density, paint);
        }

        @Override
        public boolean onTouchEvent(MotionEvent event) {
            if (event.getAction() == MotionEvent.ACTION_UP) {
                updateTarget();
                if (target.contains(event.getX(), event.getY())) {
                    clicked = true;
                    invalidate();
                    return true;
                }
            }
            return true;
        }
    }
}
