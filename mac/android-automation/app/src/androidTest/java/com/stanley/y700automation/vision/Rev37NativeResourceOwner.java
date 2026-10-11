package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.os.ParcelFileDescriptor;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;

/**
 * Independent Android action-time read of the EXISTING Linux android_ui
 * canonical Claim SOT. The owner marker supplied by a Host command is
 * a hint only and cannot grant an EXTERNAL_IRREVERSIBLE click.
 *
 * This class does not create, release, mutate or impersonate a Claim;
 * missing su/file, malformed Claim or mismatched exact owner -> BLOCKED.
 *
 * On the next source acceptance, Capability irrevocable actions still
 * require the separate native TikTok Publish authorization. This reader
 * can only prove which owner currently holds the resource.
 */
public final class Rev37NativeResourceOwner {
    private static final String CLAIM =
            "/data/local/y700-linux/rootfs/opt/y700/runtime/android-ui.claim.json";
    private static final int MAX_CHARS = 8192;

    private Rev37NativeResourceOwner() {}

    static JSONObject readFixedClaim(Instrumentation instrumentation) {
        if (instrumentation == null) return null;
        String command = "su -c 'cat " + CLAIM + "'";
        try (ParcelFileDescriptor descriptor = instrumentation
                .getUiAutomation().executeShellCommand(command)) {
            if (descriptor == null) return null;
            StringBuilder raw = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(new FileInputStream(
                            descriptor.getFileDescriptor())))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (raw.length() + line.length() + 1 > MAX_CHARS)
                        return null;
                    raw.append(line).append('\n');
                }
            }
            JSONObject result = new JSONObject(raw.toString().trim());
            if (result.optInt("claim_version", -1) != 1
                    || !"android_ui".equals(
                            result.optString("resource", ""))
                    || !(result.opt("claim_id") instanceof String)
                    || !result.optString("claim_id", "")
                            .startsWith("ui-claim-")
                    || !(result.opt("owner_id") instanceof String)
                    || result.optString("owner_id", "").isEmpty())
                return null;
            return result;
        } catch (Exception ignored) {
            return null;
        }
    }

    /**
     * Read exactly one Claim before external input. In the frozen
     * development state, only a positive matching LEGACY Claim can be
     * classified as Legacy. CAPABILITY is always denied here and must use
     * a separately accepted, one-shot native Publish dispatcher.
     */
    public static String classifyExternalEffect(
            Instrumentation instrumentation, String expectedClaimId,
            boolean hostMarkedCapability) {
        if (expectedClaimId == null || expectedClaimId.isEmpty())
            return "EXTERNAL_EFFECT_CLAIM_ID_MISSING";
        JSONObject current = readFixedClaim(instrumentation);
        if (current == null)
            return "EXTERNAL_EFFECT_NATIVE_CLAIM_UNAVAILABLE";
        if (!expectedClaimId.equals(current.optString("claim_id", "")))
            return "EXTERNAL_EFFECT_CLAIM_DRIFT";
        String kind = current.optString("owner_kind", "");
        if ("CAPABILITY".equals(kind) || hostMarkedCapability)
            return "CAPABILITY_NATIVE_EXTERNAL_EFFECT_GATE_CLOSED";
        if (!"LEGACY".equals(kind))
            return "EXTERNAL_EFFECT_OWNER_KIND_UNACCEPTED";
        return "EXACT_LEGACY_CLAIM_OBSERVED_READ_ONLY";
    }
}
