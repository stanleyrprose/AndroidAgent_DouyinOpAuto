package com.stanley.y700automation;

import org.opencv.android.OpenCVLoader;
import org.opencv.core.Core;

/**
 * Loads OpenCV from the target application's class loader / native namespace.
 *
 * Instrumentation classes live in the androidTest package and cannot reliably
 * resolve target-app native libraries via their own System.loadLibrary() call.
 */
public final class OpenCvBootstrap {
    private static boolean loaded = false;

    private OpenCvBootstrap() {}

    public static synchronized String ensureLoaded() {
        if (!loaded) {
            if (!OpenCVLoader.initLocal()) {
                throw new UnsatisfiedLinkError("OpenCVLoader.initLocal() returned false");
            }
            // Prove JNI binding works, not just that dlopen returned.
            Core.getVersionString();
            loaded = true;
        }
        return Core.getVersionString();
    }
}
