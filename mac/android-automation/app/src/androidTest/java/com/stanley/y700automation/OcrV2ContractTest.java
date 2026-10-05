package com.stanley.y700automation;

import com.stanley.y700automation.vision.OcrTextLocator;
import com.stanley.y700automation.vision.VisionTemplateLocator;
import com.stanley.y700automation.vision.VisionV0Harness;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Assert;
import org.junit.Test;

public final class OcrV2ContractTest {
    @Test
    public void substringSpecValidates() throws Exception {
        OcrTextLocator.validateTextSpec(new JSONObject()
                .put("type", "vision_text")
                .put("pattern", "继续")
                .put("match", "substring")
                .put("min_confidence", 0.85)
                .put("roi_ratio", new JSONArray().put(0.0).put(0.0).put(1.0).put(1.0)));
    }

    @Test
    public void boundedRegexValidates() throws Exception {
        OcrTextLocator.validateTextSpec(new JSONObject()
                .put("type", "vision_text")
                .put("pattern", "[0-9]+元抢购")
                .put("match", "regex")
                .put("min_confidence", 0.9));
    }

    @Test
    public void catastrophicRegexIsRejected() throws Exception {
        assertInvalidPattern(new JSONObject()
                .put("type", "vision_text")
                .put("pattern", "(a+)+$")
                .put("match", "regex"));
    }

    @Test
    public void regexAlternationIsRejected() throws Exception {
        assertInvalidPattern(new JSONObject()
                .put("type", "vision_text")
                .put("pattern", "确定|确认")
                .put("match", "regex"));
    }

    @Test
    public void conflictingRoiIsRejected() throws Exception {
        try {
            OcrTextLocator.validateTextSpec(new JSONObject()
                    .put("type", "vision_text")
                    .put("pattern", "设置")
                    .put("roi", new JSONArray().put(0).put(0).put(100).put(100))
                    .put("roi_ratio", new JSONArray().put(0.0).put(0.0).put(1.0).put(1.0)));
            Assert.fail("expected VISION_INVALID_ROI");
        } catch (VisionV0Harness.VisionFailure e) {
            Assert.assertEquals(VisionV0Harness.ERR_INVALID_ROI, e.code);
        }
    }

    @Test
    public void ocrFeatureFlagDefaultsOff() throws Exception {
        VisionTemplateLocator.Config config =
                new VisionTemplateLocator.Config(new JSONObject().put("enabled", true));
        Assert.assertFalse(config.ocrEnabled);
    }

    @Test
    public void ocrFeatureFlagCanBeExplicitlyEnabled() throws Exception {
        VisionTemplateLocator.Config config =
                new VisionTemplateLocator.Config(new JSONObject()
                        .put("enabled", true)
                        .put("ocr_enabled", true));
        Assert.assertTrue(config.ocrEnabled);
    }

    private static void assertInvalidPattern(JSONObject spec) throws Exception {
        try {
            OcrTextLocator.validateTextSpec(spec);
            Assert.fail("expected VISION_INVALID_PATTERN");
        } catch (VisionV0Harness.VisionFailure e) {
            Assert.assertEquals(OcrTextLocator.ERR_INVALID_PATTERN, e.code);
        }
    }
}
