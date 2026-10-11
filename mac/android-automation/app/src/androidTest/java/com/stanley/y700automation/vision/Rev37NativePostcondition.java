package com.stanley.y700automation.vision;

import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;

import java.util.List;

/**
 * Exact versioned TikTok Create-screen positive postcondition.
 * A caller-provided expect=true or mere successful UiDevice.click is never
 * a verification result. Fixed markers must be reviewed for exact APK
 * version/signing certificate during real-device acceptance.
 */
public final class Rev37NativePostcondition {
    private static final String PACKAGE = "com.zhiliaoapp.musically";
    private static final String CONTRACT = "tiktok.create.observe.v1";
    private static final boolean CREATE_POSTCONDITION_ACCEPTED = false;
    private static final String[] CREATE_SCREEN_MARKERS = {};

    private Rev37NativePostcondition() {}

    public static boolean createVisiblePositive(
            UiDevice device, String contractId) {
        if (!CREATE_POSTCONDITION_ACCEPTED
                || CREATE_SCREEN_MARKERS.length == 0
                || device == null
                || !CONTRACT.equals(contractId)
                || !PACKAGE.equals(device.getCurrentPackageName()))
            return false;
        try {
            for (String id : CREATE_SCREEN_MARKERS) {
                if (id == null || !id.startsWith(PACKAGE + ":id/"))
                    return false;
                List<UiObject2> elements = device.findObjects(By.res(id));
                if (elements == null || elements.size() != 1)
                    return false;
                UiObject2 node = elements.get(0);
                if (node == null || !node.isEnabled()
                        || node.getVisibleBounds() == null
                        || node.getVisibleBounds().isEmpty())
                    return false;
            }
            return true;
        } catch (Exception ignored) {
            return false;
        }
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
