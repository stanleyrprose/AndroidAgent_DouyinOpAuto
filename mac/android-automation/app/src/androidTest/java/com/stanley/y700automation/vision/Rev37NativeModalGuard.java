package com.stanley.y700automation.vision;

import androidx.test.uiautomator.By;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;

import java.util.List;

/**
 * Frozen action-specific semantic modal watchlist for Android JIT.
 *
 * Never accepts a caller-supplied "modal_clear" boolean. A positive
 * observation needs a reviewed application contract with versioned,
 * verified blocking selectors AND a positive read of every selector.
 *
 * Currently none of the real TikTok modal signatures have acceptance:
 * the entire path is fail-closed pending final device contract acceptance.
 * Only inert read-only monitoring is possible here; no input injection.
 */
public final class Rev37NativeModalGuard {
    private static final class Contract {
        final String id;
        final String packageName;
        final String[] blockerResourceIds;
        final boolean accepted;
        Contract(String id, String packageName, String[] blockerResourceIds,
                 boolean accepted) {
            this.id = id;
            this.packageName = packageName;
            this.blockerResourceIds = blockerResourceIds;
            this.accepted = accepted;
        }
    }

    // These are candidates for future reviewed package/signature-specific
    // selectors, NEVER generic strings from a workflow/LLM request.
    private static final Contract SETTINGS = new Contract(
            "android.settings.observe.v1", "com.android.settings",
            new String[]{}, false);
    private static final Contract TIKTOK = new Contract(
            "tiktok.create.observe.v1", "com.zhiliaoapp.musically",
            new String[]{}, false);
    private static final Contract TIKTOK_PUBLISH = new Contract(
            "tiktok.publish-control.v1", "com.zhiliaoapp.musically",
            new String[]{}, false);

    private Rev37NativeModalGuard() {}

    private static Contract route(String id) {
        if (SETTINGS.id.equals(id)) return SETTINGS;
        if (TIKTOK.id.equals(id)) return TIKTOK;
        if (TIKTOK_PUBLISH.id.equals(id)) return TIKTOK_PUBLISH;
        return null;
    }

    public static final class Verdict {
        public final String code;
        private Verdict(String code) { this.code = code; }
        public boolean readOnlyClear() {
            return "READ_ONLY_SEMANTIC_MODAL_GUARD_CLEAR".equals(code);
        }
    }

    public static Verdict observe(
            UiDevice device, String frozenRouteId, String foregroundPackage) {
        if (device == null || frozenRouteId == null
                || foregroundPackage == null)
            return new Verdict("SEMANTIC_MODAL_OBSERVER_UNAVAILABLE");
        Contract contract = route(frozenRouteId);
        if (contract == null || !contract.packageName.equals(foregroundPackage))
            return new Verdict("SEMANTIC_MODAL_CONTRACT_MISMATCH");
        if (!contract.accepted || contract.blockerResourceIds.length == 0)
            return new Verdict("SEMANTIC_MODAL_CONTRACT_NOT_ACCEPTED");
        if (!foregroundPackage.equals(device.getCurrentPackageName()))
            return new Verdict("FRAME_FOREGROUND_DRIFT");
        try {
            for (String fixedSelector : contract.blockerResourceIds) {
                if (fixedSelector == null || fixedSelector.isEmpty())
                    return new Verdict("SEMANTIC_MODAL_SELECTOR_UNAVAILABLE");
                List<UiObject2> candidates = device.findObjects(By.res(fixedSelector));
                if (candidates == null)
                    return new Verdict("SEMANTIC_MODAL_QUERY_UNAVAILABLE");
                for (UiObject2 candidate : candidates) {
                    if (candidate == null)
                        return new Verdict("SEMANTIC_MODAL_QUERY_UNAVAILABLE");
                    if (candidate.isEnabled() && candidate.getVisibleBounds() != null
                            && !candidate.getVisibleBounds().isEmpty()) {
                        return new Verdict("UNEXPECTED_BLOCKING_OVERLAY");
                    }
                }
            }
        } catch (Exception ignored) {
            return new Verdict("SEMANTIC_MODAL_QUERY_UNAVAILABLE");
        }
        // Only a reviewed, complete contract and successfully observed
        // selector set may return read-only CLEAR. This is NOT dispatch.
        return new Verdict("READ_ONLY_SEMANTIC_MODAL_GUARD_CLEAR");
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
