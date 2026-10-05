package com.stanley.y700automation.vision;

import android.graphics.Rect;

import org.junit.Assert;
import org.junit.Test;

public final class OcrTextLocatorNormalizationTest {
    @Test
    public void stripsWhitespaceAndCaseFolds() {
        Assert.assertEquals("wlan", OcrTextLocator.normalize(" W L A N "));
    }

    @Test
    public void removesOnlyHanInternalOcrVerticalSeparator() {
        Assert.assertEquals(
                OcrTextLocator.normalize("快应用引擎插件"),
                OcrTextLocator.normalize("快应用引|擎插件"));
        Assert.assertEquals(
                OcrTextLocator.normalize("快应用引擎插件"),
                OcrTextLocator.normalize("快应用引｜擎插件"));
        Assert.assertEquals(
                OcrTextLocator.normalize("快应用引擎插件"),
                OcrTextLocator.normalize("快应用引¦擎插件"));
    }

    @Test
    public void preservesLatinVerticalSeparator() {
        Assert.assertEquals("a|b", OcrTextLocator.normalize("A|B"));
    }

    @Test
    public void doesNotConfuseZeroWithLetterO() {
        Assert.assertNotEquals(
                OcrTextLocator.normalize("BAIC_DVR_860CADA3"),
                OcrTextLocator.normalize("BAIC_DVR_86OCADA3"));
    }

    @Test
    public void doesNotConfuseOneWithLetterL() {
        Assert.assertNotEquals(
                OcrTextLocator.normalize("K1"),
                OcrTextLocator.normalize("Kl"));
    }

    @Test
    public void inferenceContextExpandsToMinimumHeightWithoutChangingWidth() {
        Rect roi = new Rect(96, 58, 505, 348);
        Rect context = OcrTextLocator.expandInferenceContext(
                roi, 1904, 3040, 512);
        Assert.assertEquals(96, context.left);
        Assert.assertEquals(505, context.right);
        Assert.assertEquals(512, context.height());
        Assert.assertTrue(context.top <= roi.top);
        Assert.assertTrue(context.bottom >= roi.bottom);
    }

    @Test
    public void inferenceContextClampsAtFrameBoundaryAndPreservesTargetHeight() {
        Rect roi = new Rect(100, 10, 500, 180);
        Rect context = OcrTextLocator.expandInferenceContext(
                roi, 1904, 3040, 512);
        Assert.assertEquals(0, context.top);
        Assert.assertEquals(512, context.bottom);
    }
}
