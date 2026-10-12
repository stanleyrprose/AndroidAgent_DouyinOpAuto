package com.stanley.y700automation.vision;

import android.accessibilityservice.AccessibilityServiceInfo;
import android.app.Instrumentation;
import android.app.KeyguardManager;
import android.app.UiAutomation;
import android.content.Context;
import android.graphics.Rect;
import android.os.ParcelFileDescriptor;
import android.os.PowerManager;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import androidx.test.uiautomator.UiDevice;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Rev3.7 candidate READ-ONLY native Android JIT state observer.
 *
 * Fixed root-owned State Integrity SOT via KernelSU shell, foreground
 * Activity via Android activity service, and typed accessibility windows.
 * A production driver must call from the immediate mutation boundary, not
 * a stale host snapshot. This class NEVER injects events or enables D-G3.
 *
 * Unknown/incomplete window inventory or unsupported KernelSU read ->
 * UNAVAILABLE; it is never interpreted as no overlay.
 *
 * This new development source is UNTESTED and not deployed.
 */
public final class Rev37NativeStateObserver {
    private static final String SOT =
            "/data/local/y700-linux/rootfs/opt/y700/runtime/ui-state/device-state.json";
    private static final Pattern BOOT = Pattern.compile(
            "^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}$");
    private static final Pattern TOP = Pattern.compile(
            "topResumedActivity=ActivityRecord\\{[^\\n]*?\\su\\d+\\s+([^\\s/]+)/([^\\s]+)");
    private static final Pattern EPOCH = Pattern.compile("^epoch-[0-9a-f]{32}$");
    private static final int MAX_CAPTURE_CHARS = 8192;
    // Conservative read-only observation budget, not a calibrated JIT
    // frame age or authorization to dispatch any UI mutation.
    private static final long MAX_OBSERVATION_MS = 750L;

    private Rev37NativeStateObserver() {}

    public static final class Observation {
        public final String reason;
        public final JSONObject current;
        private Observation(String reason, JSONObject current) {
            this.reason = reason;
            this.current = current;
        }
        public boolean available() {
            return "READ_ONLY_NATIVE_STATE_OBSERVED".equals(reason);
        }
    }

    private static Observation unavailable(String code) {
        return new Observation(code, null);
    }

    private static String fixedShell(Instrumentation i, String command) {
        try (ParcelFileDescriptor fd = i.getUiAutomation()
                .executeShellCommand(command)) {
            if (fd == null) return null;
            StringBuilder out = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(new FileInputStream(
                            fd.getFileDescriptor())))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (out.length() + line.length() > MAX_CAPTURE_CHARS)
                        return null;
                    out.append(line).append('\n');
                }
            }
            return out.toString();
        } catch (Exception ignored) {
            return null;
        }
    }

    private static String foregroundComponent(Instrumentation i) {
        // Bound the output of a potentially very large dumpsys report.
        // The command is a fixed literal, never derived from an action.
        String raw = fixedShell(i,
                "dumpsys activity activities | grep topResumedActivity=");
        if (raw == null) return null;
        Matcher match = TOP.matcher(raw);
        if (!match.find()) return null;
        String component = match.group(1) + "/" + match.group(2);
        // Multiple resumed activities in the same service snapshot are
        // ambiguous for a single-display exact foreground contract.
        if (match.find()) return null;
        return component;
    }

    private static String rootStateMetadata(Instrumentation i) {
        // GNU stat without -L observes the inode at the fixed path, so a
        // symlink is never accepted as the root-owned SOT. Metadata is
        // rechecked around the fixed-path read to detect replacement.
        String raw = fixedShell(i, "su -c 'stat -c \"%u %a %F %d %i %h %s %Y %Z\" "
                + SOT + "'");
        if (raw == null) return null;
        String[] fields = raw.trim().split(" ");
        if (fields.length != 10 || !"0".equals(fields[0])
                || !"600".equals(fields[1])
                || !"regular".equals(fields[2])
                || !"file".equals(fields[3])) return null;
        try {
            long size = Long.parseLong(fields[7]);
            if (!"1".equals(fields[6])) return null;
            if (size <= 0 || size > MAX_CAPTURE_CHARS) return null;
            for (int index : new int[]{4, 5, 8, 9}) {
                if (Long.parseLong(fields[index]) < 0) return null;
            }
        } catch (NumberFormatException ignored) {
            return null;
        }
        return raw.trim();
    }

    private static JSONObject rootState(Instrumentation i) {
        // The trusted host SOT is fixed, root-owned, mode 0600 and regular.
        // A raw su cat result without filesystem identity is insufficient.
        String metadataBefore = rootStateMetadata(i);
        if (metadataBefore == null) return null;
        String raw = fixedShell(i, "su -c 'cat " + SOT + "'");
        String metadataAfter = rootStateMetadata(i);
        if (raw == null || raw.trim().isEmpty()
                || !metadataBefore.equals(metadataAfter)) return null;
        try {
            JSONObject state = new JSONObject(raw.trim());
            if (state.optInt("state_version", -1) != 1
                    || !"semantic-v1".equals(
                            state.optString("fingerprint_version", ""))
                    || !EPOCH.matcher(state.optString("state_epoch", "")).matches()
                    || !(state.opt("revision") instanceof Integer)
                    || state.optInt("revision", -1) < 0) return null;
            return state;
        } catch (Exception ignored) {
            return null;
        }
    }

    private static String classifyWindows(
            Instrumentation i, String expectedPackage, Rect targetBounds) {
        // This is a conservative top-level candidate guard, NOT proof of a
        // versioned in-app modal blocking_selector. Production release still
        // needs that independent semantic watched-property observer.
        UiAutomation automation = i.getUiAutomation();
        AccessibilityServiceInfo info = null;
        int originalFlags = -1;
        try {
            info = automation.getServiceInfo();
            if (info == null) return "WINDOW_INVENTORY_UNAVAILABLE";
            originalFlags = info.flags;
            info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            automation.setServiceInfo(info);
            List<AccessibilityWindowInfo> windows = automation.getWindows();
            if (windows == null || windows.isEmpty()
                    || windows.size() > 80) return "WINDOW_INVENTORY_UNAVAILABLE";
            int focused = 0;
            int activeTargetRoots = 0;
            int targetRoots = 0;
            for (AccessibilityWindowInfo window : windows) {
                if (window == null) return "WINDOW_INVENTORY_INCOMPLETE";
                if (window.isFocused()) focused++;
                AccessibilityNodeInfo root = window.getRoot();
                if (root == null || root.getPackageName() == null)
                    return "WINDOW_ROOT_UNAVAILABLE";
                String owner = root.getPackageName().toString();
                Rect bounds = new Rect();
                window.getBoundsInScreen(bounds);
                boolean overlaps = Rect.intersects(bounds, targetBounds);
                boolean targetRoot = window.getType()
                        == AccessibilityWindowInfo.TYPE_APPLICATION
                        && expectedPackage.equals(owner);
                if (targetRoot) targetRoots++;
                if (targetRoot && window.isActive()) activeTargetRoots++;
                if (window.getType() == AccessibilityWindowInfo.TYPE_INPUT_METHOD) {
                    // A keyboard that covers the intended tap or owns focus
                    // is not an ignorable overlay. Do not infer that a
                    // future action-specific contract will reject it.
                    if (overlaps || window.isFocused() || window.isActive())
                        return "UNEXPECTED_BLOCKING_OVERLAY";
                    continue;
                }
                if (!targetRoot && (window.isFocused() || window.isActive()
                        || overlaps)) {
                    return "UNEXPECTED_BLOCKING_OVERLAY";
                }
                if (targetRoot && !window.isActive() && overlaps) {
                    return "WINDOW_TARGET_ROOT_AMBIGUOUS";
                }
            }
            if (focused != 1 || activeTargetRoots != 1 || targetRoots != 1)
                return "WINDOW_FOCUS_OR_TARGET_ROOT_UNAVAILABLE";
            return "READ_ONLY_WINDOW_INVENTORY_CLASSIFIED";
        } catch (Exception ignored) {
            return "WINDOW_INVENTORY_UNAVAILABLE";
        } finally {
            if (info != null && originalFlags >= 0) {
                try {
                    info.flags = originalFlags;
                    automation.setServiceInfo(info);
                } catch (Exception ignored) {
                    // A caller still cannot authorize dispatch from this
                    // observer; release gate must stay closed.
                }
            }
        }
    }

    /**
     * In-memory native observation only. Does not export raw boot ID or
     * epoch to logs, file, screenshot metadata or a controller.
     */
    public static Observation observe(
            Instrumentation instrumentation, UiDevice device,
            String expectedPackage, Rect targetBounds,
            String frozenRouteContractId) {
        if (instrumentation == null || device == null || targetBounds == null
                || expectedPackage == null || expectedPackage.isEmpty())
            return unavailable("FRAME_UNAVAILABLE");
        long observationStartedMs = SystemClock.elapsedRealtimeNanos() / 1_000_000L;
        // The caller cannot attest that no modal is present: require a
        // complete accepted, versioned native watchlist observed right now.
        Rev37NativeAppContract.Result app =
                Rev37NativeAppContract.inspect(
                        instrumentation, frozenRouteContractId);
        if (!app.matches())
            return unavailable(app.reason);
        Rev37NativeModalGuard.Verdict modal = Rev37NativeModalGuard.observe(
                device, frozenRouteContractId, expectedPackage);
        if (!modal.readOnlyClear())
            return unavailable(modal.code);
        Context context = instrumentation.getTargetContext();
        PowerManager power = (PowerManager) context.getSystemService(
                Context.POWER_SERVICE);
        KeyguardManager keyguard = (KeyguardManager) context.getSystemService(
                Context.KEYGUARD_SERVICE);
        if (power == null || keyguard == null || !power.isInteractive()
                || keyguard.isKeyguardLocked())
            return unavailable("FRAME_STALE");
        String bootBefore = fixedShell(instrumentation,
                "cat /proc/sys/kernel/random/boot_id");
        JSONObject stateBefore = rootState(instrumentation);
        if (bootBefore == null || stateBefore == null)
            return unavailable("STATE_SOT_UNAVAILABLE");
        String boot = bootBefore.trim();
        if (!BOOT.matcher(boot).matches())
            return unavailable("BOOT_ID_INVALID");
        int rotationBefore = device.getDisplayRotation();
        int widthBefore = device.getDisplayWidth();
        int heightBefore = device.getDisplayHeight();
        if (widthBefore <= 0 || heightBefore <= 0
                || rotationBefore < 0 || rotationBefore > 3)
            return unavailable("FRAME_DISPLAY_UNAVAILABLE");
        String component = foregroundComponent(instrumentation);
        if (component == null || !component.startsWith(expectedPackage + "/")
                || !expectedPackage.equals(device.getCurrentPackageName()))
            return unavailable("FRAME_FOREGROUND_DRIFT");
        String windowsReason = classifyWindows(
                instrumentation, expectedPackage, targetBounds);
        if (!"READ_ONLY_WINDOW_INVENTORY_CLASSIFIED".equals(windowsReason))
            return unavailable(windowsReason);
        String bootAfter = fixedShell(instrumentation,
                "cat /proc/sys/kernel/random/boot_id");
        JSONObject stateAfter = rootState(instrumentation);
        if (bootAfter == null || stateAfter == null
                || !boot.equals(bootAfter.trim()))
            return unavailable("FRAME_BOOT_MISMATCH");
        if (!stateBefore.optString("state_epoch").equals(
                stateAfter.optString("state_epoch"))
                || stateBefore.optInt("revision", -1)
                != stateAfter.optInt("revision", -2))
            return unavailable("FRAME_REVISION_STALE");
        // Window enumeration and root SOT reads may take long enough for
        // Android to switch the foreground Activity. Never return a mixed
        // snapshot assembled from a prior Activity and later SOT revision.
        String componentAfter = foregroundComponent(instrumentation);
        if (!component.equals(componentAfter)
                || !expectedPackage.equals(device.getCurrentPackageName())
                || !power.isInteractive() || keyguard.isKeyguardLocked())
            return unavailable("FRAME_FOREGROUND_DRIFT");
        // A transient overlay can appear after the first window walk while
        // the state file stays unchanged. Require a second native inventory
        // observation rather than treating the first as current forever.
        String finalWindowsReason = classifyWindows(
                instrumentation, expectedPackage, targetBounds);
        if (!"READ_ONLY_WINDOW_INVENTORY_CLASSIFIED".equals(finalWindowsReason))
            return unavailable(finalWindowsReason);
        Rev37NativeModalGuard.Verdict finalModal = Rev37NativeModalGuard.observe(
                device, frozenRouteContractId, expectedPackage);
        if (!finalModal.readOnlyClear())
            return unavailable(finalModal.code);
        // The second window walk and semantic selectors are also async
        // reads. Reobserve Activity before issuing the final snapshot.
        if (!component.equals(foregroundComponent(instrumentation))
                || !expectedPackage.equals(device.getCurrentPackageName())
                || rotationBefore != device.getDisplayRotation()
                || widthBefore != device.getDisplayWidth()
                || heightBefore != device.getDisplayHeight())
            return unavailable("FRAME_FOREGROUND_DRIFT");
        // The second window/modal walk may race an external Core mutation.
        // Re-read the authoritative SOT and boot identity after that walk;
        // never issue a token from a state observed before the last guard.
        JSONObject finalState = rootState(instrumentation);
        String finalBoot = fixedShell(instrumentation,
                "cat /proc/sys/kernel/random/boot_id");
        if (finalState == null || finalBoot == null
                || !boot.equals(finalBoot.trim())
                || !stateAfter.optString("state_epoch").equals(
                        finalState.optString("state_epoch"))
                || stateAfter.optInt("revision", -1)
                        != finalState.optInt("revision", -2))
            return unavailable("FRAME_REVISION_STALE");
        long observationFinishedMs = SystemClock.elapsedRealtimeNanos() / 1_000_000L;
        if (observationFinishedMs < observationStartedMs
                || observationFinishedMs - observationStartedMs > MAX_OBSERVATION_MS)
            return unavailable("STATE_OBSERVATION_STALE");
        String activity = component.substring(expectedPackage.length() + 1);
        try {
            JSONObject current = new JSONObject()
                    .put("boot_id", boot)
                    .put("state_epoch", stateAfter.getString("state_epoch"))
                    .put("revision", stateAfter.getInt("revision"))
                    .put("display_id", 0)
                    .put("rotation", rotationBefore)
                    .put("width", widthBefore)
                    .put("height", heightBefore)
                    .put("foreground", new JSONObject()
                            .put("package", expectedPackage)
                            .put("activity", activity))
                    .put("screen_interactive", power.isInteractive())
                    .put("keyguard_locked", keyguard.isKeyguardLocked())
                    .put("blocking_overlay_present", false)
                    .put("observed_boottime_ms",
                            SystemClock.elapsedRealtimeNanos() / 1_000_000L);
            // Always fail closed at the production dispatch boundary until
            // the separate native release authority accepts D-G3.
            return new Observation("READ_ONLY_NATIVE_STATE_OBSERVED", current);
        } catch (Exception ignored) {
            return unavailable("STATE_OBSERVATION_MALFORMED");
        }
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
