package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.graphics.Rect;
import android.os.ParcelFileDescriptor;

import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiObject2;
import androidx.test.uiautomator.By;

import java.util.List;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.util.regex.Pattern;

/**
 * Rev3.7 NATIVE CAPABILITY irreversible Publish pre-dispatch witness.
 *
 * This is NOT a second Publisher and does not click. The existing v2
 * Android Driver invokes this check immediately before one semantic
 * Publish click, AFTER the existing Publisher has durably entered
 * COMMITTING and AFTER the sole Capability effect-boundary was fsynced.
 *
 * No request-supplied policy/approval/version/boot/claim positive booleans
 * count. All evidence is read again from fixed root-controlled paths and
 * compared to independent current Android state.
 *
 * Genuine TikTok version/certificate, modal signatures and full native
 * PostConfig semantic contract are NOT YET accepted. The release constant
 * deliberately keeps all CAPABILITY publishing CLOSED.
 */
public final class Rev37NativePublishBoundary {
    private static final boolean NATIVE_PUBLISH_ACCEPTED = false;
    private static final String ROUTE = "tiktok.publish-control.v1";
    private static final String PACKAGE = "com.zhiliaoapp.musically";
    private static final String JOB_ROOT =
            "/data/local/y700-linux/rootfs/opt/y700/capability-jobs/active/";
    private static final String PUBLISH_STATE =
            "/data/local/y700-linux/rootfs/opt/y700/runtime/state/publisher.json";
    private static final Pattern CAP = Pattern.compile("^cap-[0-9a-f]{48}$");
    private static final Pattern BACKEND = Pattern.compile(
            "^cap-[0-9a-f]{48}--publisher-01$");
    private static final Pattern SHA = Pattern.compile("^[0-9a-f]{64}$");
    private static final Pattern PUBLISHER_ID = Pattern.compile(
            "^[A-Za-z0-9_.-]{1,96}$");
    private static final int MAX_RECEIPT = 8192;
    // Requires real-device calibrated accepted boundary age, never a
    // caller-provided window or a guessed production number.
    private static final int ACCEPTED_BOUNDARY_AGE_MS = -1;

    private Rev37NativePublishBoundary() {}

    public static final class Verdict {
        public final String code;
        private Verdict(String code) { this.code = code; }
        public boolean authorizesOnce() {
            return NATIVE_PUBLISH_ACCEPTED
                    && "NATIVE_CAPABILITY_PUBLISH_BOUNDARY_VERIFIED"
                            .equals(code);
        }
    }

    private static Verdict deny(String reason) {
        return new Verdict(reason);
    }

    private static JSONObject readRestrictedJson(
            Instrumentation instrumentation, String fixedPath) {
        // 'fixedPath' is assembled exclusively from validated exact
        // claim identity, never workflow/request-supplied path data.
        if (instrumentation == null || fixedPath == null
                || fixedPath.contains("'") || fixedPath.contains("\n"))
            return null;
        String command = "su -c 'cat " + fixedPath + "'";
        try (ParcelFileDescriptor descriptor = instrumentation
                .getUiAutomation().executeShellCommand(command)) {
            if (descriptor == null) return null;
            StringBuilder raw = new StringBuilder();
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(new FileInputStream(
                            descriptor.getFileDescriptor())))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    if (raw.length() + line.length() + 1 > MAX_RECEIPT)
                        return null;
                    raw.append(line).append('\n');
                }
            }
            return new JSONObject(raw.toString().trim());
        } catch (Exception ignored) {
            return null;
        }
    }

    private static boolean same(JSONObject left, JSONObject right,
                                String key) {
        return left != null && right != null
                && left.has(key) && right.has(key)
                && left.opt(key) != null
                && left.opt(key).equals(right.opt(key));
    }

    /**
     * Checks durable lower and upper boundaries plus current native facts.
     * The method itself is observation only. Caller MUST independently
     * enforce the exact single input, positive button, and postcondition.
     */
    public static Verdict inspectBeforeSingleClick(
            Instrumentation instrumentation, UiDevice device,
            String exactClaimId,
            Rect buttonBounds) {
        if (!NATIVE_PUBLISH_ACCEPTED)
            return deny("CAPABILITY_NATIVE_PUBLISH_GATE_CLOSED");
        if (exactClaimId == null
                || !exactClaimId.startsWith("ui-claim-")
                || instrumentation == null || device == null
                || buttonBounds == null || buttonBounds.isEmpty())
            return deny("CAPABILITY_PUBLISH_CLAIM_OR_TARGET_INVALID");
        JSONObject claim = Rev37NativeResourceOwner.readFixedClaim(
                instrumentation);
        if (claim == null || !exactClaimId.equals(
                claim.optString("claim_id", ""))
                || !"CAPABILITY".equals(
                        claim.optString("owner_kind", "")))
            return deny("CAPABILITY_PUBLISH_CLAIM_DRIFT");
        String job = claim.optString("capability_job_id", "");
        String backend = claim.optString("backend_job_id", "");
        if (!CAP.matcher(job).matches()
                || !BACKEND.matcher(backend).matches()
                || !backend.equals(job + "--publisher-01"))
            return deny("CAPABILITY_PUBLISH_BACKEND_ID_INVALID");
        if (!SHA.matcher(claim.optString(
                "request_sha256", "")).matches())
            return deny("CAPABILITY_PUBLISH_REQUEST_ID_INVALID");
        JSONObject effect = readRestrictedJson(
                instrumentation, JOB_ROOT + job + "/effect-boundary.json");
        JSONObject binding = readRestrictedJson(
                instrumentation, JOB_ROOT + job + "/backend.json");
        JSONObject approval = readRestrictedJson(
                instrumentation, JOB_ROOT + job + "/approval.json");
        JSONObject publisher = readRestrictedJson(
                instrumentation, PUBLISH_STATE);
        JSONObject request = readRestrictedJson(
                instrumentation, JOB_ROOT + job + "/request.json");
        if (effect == null || binding == null || approval == null
                || publisher == null || request == null)
            return deny("CAPABILITY_PUBLISH_DURABLE_PROOF_UNAVAILABLE");
        if (!"EFFECT_BOUNDARY_CROSSED".equals(
                effect.optString("phase", ""))
                || effect.optInt("effect_boundary_version", -1) != 1
                || !"tiktok.publish".equals(
                        effect.optString("capability", ""))
                || !"PUBLIC".equals(effect.optString("visibility", ""))
                || !job.equals(effect.optString("capability_job_id", ""))
                || !backend.equals(effect.optString("backend_job_id", ""))
                || !"publisher".equals(
                        binding.optString("backend_type", ""))
                || !backend.equals(binding.optString("backend_job_id", ""))
                || !"COMMITTING".equals(
                        publisher.optString("status", ""))
                || !"CAPABILITY".equals(
                        publisher.optString("publisher_mode", ""))
                || !job.equals(
                        publisher.optString("capability_job_id", "")))
            return deny("CAPABILITY_PUBLISH_ORDERING_NOT_PROVEN");
        JSONObject payload = request.optJSONObject("payload");
        String publisherId = payload == null ? ""
                : payload.optString("existing_publisher_job_id", "");
        if (payload == null
                || !PUBLISHER_ID.matcher(publisherId).matches()
                || !publisherId.equals(publisher.optString("job_id", ""))
                || !"COMMIT".equals(payload.optString("publish_mode", ""))
                || !"PUBLIC".equals(payload.optString("visibility", ""))
                || !same(payload, effect, "content_sha256")
                || !same(payload, approval, "caption_sha256"))
            return deny("CAPABILITY_PUBLISH_REQUEST_CONTENT_DRIFT");
        if (!same(effect, claim, "request_sha256")
                || !same(binding, claim, "request_sha256")
                || !same(effect, approval, "approval_id")
                || !same(effect, approval, "approval_nonce")
                || !same(effect, approval, "content_sha256"))
            return deny("CAPABILITY_PUBLISH_APPROVAL_OR_CONTENT_DRIFT");

        // The semantic POST_CONFIG contract must be independently visible
        // RIGHT NOW. The caller-selected target bounds cannot substitute
        // for a unique native Publish button and PUBLIC summary.
        try {
            List<UiObject2> publishButtons = device.findObjects(
                    By.clazz("android.widget.Button").text("发布"));
            List<UiObject2> publicSummary = device.findObjects(
                    By.desc("所有人可见"));
            if (publishButtons == null || publishButtons.size() != 1
                    || publicSummary == null || publicSummary.size() != 1
                    || !publishButtons.get(0).isEnabled()
                    || !publishButtons.get(0).isClickable()
                    || !publishButtons.get(0).getVisibleBounds()
                            .equals(buttonBounds))
                return deny("CAPABILITY_PUBLISH_SEMANTIC_TARGET_UNVERIFIED");
        } catch (Exception ignored) {
            return deny("CAPABILITY_PUBLISH_SEMANTIC_STATE_UNAVAILABLE");
        }
        Rev37NativeStateObserver.Observation now =
                Rev37NativeStateObserver.observe(
                        instrumentation, device, PACKAGE,
                        buttonBounds, ROUTE);
        if (!now.available())
            return deny(now.reason);
        JSONObject current = now.current;
        if (!same(effect, current, "state_epoch")
                || !same(effect, current, "revision")
                || !current.optString("boot_id", "").equals(
                        effect.optString("observed_boot_id", "")))
            return deny("CAPABILITY_PUBLISH_JIT_STATE_DRIFT");
        long observed = current.optLong("observed_boottime_ms", -1);
        long boundaryAt = effect.optLong(
                "crossed_boottime_ms", -1);
        if (ACCEPTED_BOUNDARY_AGE_MS <= 0
                || observed < 0 || boundaryAt < 0
                || observed < boundaryAt
                || observed - boundaryAt > ACCEPTED_BOUNDARY_AGE_MS)
            return deny("CAPABILITY_PUBLISH_BOUNDARY_STALE");

        JSONObject after = Rev37NativeResourceOwner.readFixedClaim(
                instrumentation);
        if (after == null || !same(claim, after, "claim_id")
                || !same(claim, after, "owner_id")
                || !same(claim, after, "claim_generation")
                || !same(claim, after, "backend_job_id"))
            return deny("CAPABILITY_PUBLISH_RESOURCE_DRIFT");
        // Still requires a separately accepted semantic button contract and
        // completion positive verifier; neither is inferred from text alone.
        return new Verdict(
                "NATIVE_CAPABILITY_PUBLISH_BOUNDARY_VERIFIED");
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
