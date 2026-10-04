package com.stanley.y700automation;

import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.graphics.RectF;

public final class VisionBenchmarkPattern {
    public static final int BG_COLOR = Color.rgb(31, 36, 44);
    public static final int IDLE_COLOR = Color.rgb(24, 119, 242);
    public static final int CLICKED_COLOR = Color.rgb(32, 180, 96);
    public static final int TARGET_WIDTH_DP = 72;
    public static final int TARGET_HEIGHT_DP = 44;

    private VisionBenchmarkPattern() {}

    public static void drawTarget(Canvas canvas, RectF rect, boolean clicked) {
        Paint p = new Paint(Paint.ANTI_ALIAS_FLAG);
        p.setStyle(Paint.Style.FILL);
        p.setColor(clicked ? CLICKED_COLOR : IDLE_COLOR);
        canvas.drawRoundRect(rect, 18f, 18f, p);

        float cx = rect.centerX();
        float cy = rect.centerY();
        float r = Math.min(rect.width(), rect.height()) * 0.27f;

        p.setStyle(Paint.Style.STROKE);
        p.setStrokeWidth(Math.max(4f, r * 0.13f));
        p.setColor(Color.WHITE);
        canvas.drawCircle(cx, cy, r, p);
        canvas.drawLine(cx - r * 0.75f, cy, cx + r * 0.75f, cy, p);
        canvas.drawLine(cx, cy - r * 0.75f, cx, cy + r * 0.75f, p);

        p.setStyle(Paint.Style.FILL);
        p.setColor(Color.rgb(255, 212, 64));
        canvas.drawCircle(cx, cy, Math.max(5f, r * 0.17f), p);
    }
}
