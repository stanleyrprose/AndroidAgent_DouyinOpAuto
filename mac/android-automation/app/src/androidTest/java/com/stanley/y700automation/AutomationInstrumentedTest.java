package com.stanley.y700automation;

import android.app.Instrumentation;
import android.app.KeyguardManager;
import android.content.Context;
import android.content.Intent;
import android.content.res.Configuration;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.ParcelFileDescriptor;
import android.os.PowerManager;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;

import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import androidx.test.uiautomator.By;
import androidx.test.uiautomator.BySelector;
import androidx.test.uiautomator.Configurator;
import androidx.test.uiautomator.Direction;
import androidx.test.uiautomator.StableResult;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiDeviceExt;
import androidx.test.uiautomator.UiObject2;

import com.stanley.y700automation.vision.OcrTextLocator;
import com.stanley.y700automation.vision.VisionTemplateLocator;
import com.stanley.y700automation.vision.VisionV0Harness;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

@RunWith(AndroidJUnit4.class)
public class AutomationInstrumentedTest {
    private static final String DRIVER_VERSION = "0.5.0";
    private static final int PROTOCOL_VERSION = 1;
    private static final int MAX_ACTIONS = 50;
    private static final long MAX_DURATION_MS = 600_000L;
    private static final long WAIT_FOR_IDLE_TIMEOUT_MS = 500L;
    private static final long WAIT_FOR_SELECTOR_TIMEOUT_MS = 0L;
    private static final int MAX_TREE_NODES = 5000;
    private static final int MAX_FAILURE_EVIDENCE_NODES = 256;

    private Instrumentation instrumentation;
    private UiDevice device;
    private Context context;
    private String jobId;
    private String sessionId;
    private long workflowStartedElapsedMs;
    private boolean testMode;
    private int testObserveFailuresRemaining;
    private VisionTemplateLocator.Config visionConfig;
    private VisionTemplateLocator visionLocator;
    private OcrTextLocator ocrLocator;
    private JSONObject lastVisionContext;
    private boolean visionRequested;
    private long semanticToVisionFallbackCount;
    private long hybridTemplateToOcrFallbackCount;
    private long visionStaleReresolveCount;
    private long visionRecoveryCount;
    private JSONArray currentVisionRecoveryEvents;

    @Test
    public void runWorkflow() throws Exception {
        instrumentation = InstrumentationRegistry.getInstrumentation();
        context = instrumentation.getTargetContext();
        device = UiDevice.getInstance(instrumentation);

        // TikTok and other animated/video surfaces may never become globally
        // "idle". UiObject2 refreshes call UiDevice.waitForIdle() implicitly,
        // so the library default can dominate action latency independently of
        // the explicit action timeout. Keep the implicit wait short and make
        // all meaningful waiting explicit via waitFor/waitStable/postconditions.
        Configurator.getInstance()
                .setWaitForIdleTimeout(WAIT_FOR_IDLE_TIMEOUT_MS)
                .setWaitForSelectorTimeout(WAIT_FOR_SELECTOR_TIMEOUT_MS);

        final long workflowStart = SystemClock.elapsedRealtime();
        workflowStartedElapsedMs = workflowStart;
        JSONObject result = new JSONObject();
        JSONArray actionResults = new JSONArray();

        try {
            JSONObject request = loadRequest();
            jobId = request.optString("job_id", "anonymous");
            sessionId = request.optString("session_id", UUID.randomUUID().toString());
            testMode = request.optBoolean("test_mode", false);
            testObserveFailuresRemaining = testMode
                    ? Math.max(0, Math.min(5, request.optInt("test_observe_failures", 0)))
                    : 0;
            visionRequested = request.has("vision");
            visionConfig = new VisionTemplateLocator.Config(request.optJSONObject("vision"));
            visionLocator = null;
            ocrLocator = null;
            lastVisionContext = null;
            semanticToVisionFallbackCount = 0L;
            hybridTemplateToOcrFallbackCount = 0L;
            visionStaleReresolveCount = 0L;
            visionRecoveryCount = 0L;
            currentVisionRecoveryEvents = new JSONArray();
            int protocol = request.optInt("protocol_version", -1);

            result.put("job_id", jobId);
            result.put("session_id", sessionId);
            result.put("driver_version", DRIVER_VERSION);
            result.put("protocol_version", PROTOCOL_VERSION);
            if (visionRequested) result.put("vision_policy", visionConfig.json());

            if (protocol != PROTOCOL_VERSION) {
                result.put("status", "BLOCKED");
                result.put("error", error("PROTOCOL_MISMATCH",
                        "request protocol=" + protocol + ", driver protocol=" + PROTOCOL_VERSION,
                        false));
                result.put("actions", actionResults);
                emitResult(result);
                return;
            }

            JSONArray actions = request.optJSONArray("actions");
            if (actions == null || actions.length() == 0) {
                result.put("status", "FAILED");
                result.put("error", error("JOB_PAYLOAD_INVALID", "actions must be non-empty", false));
                result.put("actions", actionResults);
                emitResult(result);
                return;
            }
            if (actions.length() > MAX_ACTIONS) {
                result.put("status", "BLOCKED");
                result.put("error", error("WORKFLOW_LIMIT_EXCEEDED",
                        "actions=" + actions.length() + " max=" + MAX_ACTIONS, false));
                result.put("actions", actionResults);
                emitResult(result);
                return;
            }

            long requestedMax = request.optLong("max_duration_ms", MAX_DURATION_MS);
            long workflowDeadline = Math.min(MAX_DURATION_MS, Math.max(1000L, requestedMax));
            if (testMode && request.optBoolean("test_prepare_vision_benchmark", false)) {
                prepareVisionBenchmark(request);
            }
            result.put("preflight", ensureUiPreflight(request));

            boolean failed = false;
            for (int i = 0; i < actions.length(); i++) {
                if (isCancellationRequested()) {
                    JSONObject action = actions.getJSONObject(i);
                    emitHeartbeat(i, action.optString("action", "unknown"), "CANCELLED");
                    result.put("status", "CANCELLED");
                    result.put("error", error("WORKFLOW_CANCELLED",
                            "cancellation observed at action boundary index=" + i, false));
                    failed = true;
                    break;
                }
                if (SystemClock.elapsedRealtime() - workflowStart > workflowDeadline) {
                    result.put("status", "TIMEOUT");
                    result.put("error", error("WORKFLOW_TIMEOUT", "workflow deadline exceeded", false));
                    failed = true;
                    break;
                }

                JSONObject action = actions.getJSONObject(i);
                emitHeartbeat(i, action.optString("action", "unknown"), "STARTED");
                JSONObject one = executeWithRetry(action, i);
                actionResults.put(one);
                emitHeartbeat(i, action.optString("action", "unknown"), one.optString("status", "FAILED"));

                if (!"PASS".equals(one.optString("status"))) {
                    result.put("status", one.optString("status", "FAILED"));
                    if (one.has("error")) {
                        result.put("error", one.getJSONObject("error"));
                    }
                    failed = true;
                    break;
                }
            }

            if (!failed) {
                result.put("status", "PASS");
            }
            result.put("actions", actionResults);
            result.put("duration_ms", SystemClock.elapsedRealtime() - workflowStart);
            attachVisionMetrics(result);
            emitResult(result);
        } catch (ActionFailure t) {
            if (jobId == null) jobId = "unknown";
            if (sessionId == null) sessionId = UUID.randomUUID().toString();
            result = new JSONObject();
            result.put("status", t.status);
            result.put("job_id", jobId);
            result.put("session_id", sessionId);
            result.put("driver_version", DRIVER_VERSION);
            result.put("protocol_version", PROTOCOL_VERSION);
            result.put("actions", actionResults);
            result.put("error", error(t.code, t.getMessage(), t.retryable));
            result.put("duration_ms", SystemClock.elapsedRealtime() - workflowStart);
            attachVisionMetrics(result);
            emitResult(result);
        } catch (Throwable t) {
            if (jobId == null) jobId = "unknown";
            if (sessionId == null) sessionId = UUID.randomUUID().toString();
            result = new JSONObject();
            result.put("status", "FAILED");
            result.put("job_id", jobId);
            result.put("session_id", sessionId);
            result.put("driver_version", DRIVER_VERSION);
            result.put("protocol_version", PROTOCOL_VERSION);
            result.put("actions", actionResults);
            result.put("error", error("DRIVER_CRASHED",
                    t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()), false));
            result.put("duration_ms", SystemClock.elapsedRealtime() - workflowStart);
            attachVisionMetrics(result);
            emitResult(result);
        }
    }


    private JSONObject ensureUiPreflight(JSONObject request) throws Exception {
        PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        KeyguardManager km = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);

        boolean screenInitiallyOn = pm != null && pm.isInteractive();
        boolean keyguardInitiallyBlocking = km != null && km.isKeyguardLocked();
        boolean wakeAttempted = false;
        boolean dismissAttempted = false;

        if (!screenInitiallyOn) {
            if (!request.optBoolean("auto_wake", true)) {
                throw new ActionFailure("SCREEN_OFF", "screen is off and auto_wake=false", true, "BLOCKED");
            }
            device.wakeUp();
            wakeAttempted = true;
            SystemClock.sleep(350L);
        }

        boolean screenOn = pm != null && pm.isInteractive();
        if (!screenOn) {
            throw new ActionFailure("SCREEN_OFF", "screen remained off after wake attempt", true, "BLOCKED");
        }

        boolean keyguardBlocking = km != null && km.isKeyguardLocked();
        boolean benchmarkKeyguardBypass =
                keyguardBlocking &&
                testMode &&
                request.optBoolean("test_allow_keyguard_benchmark", false) &&
                isVisionBenchmarkActivityTop();
        if (keyguardBlocking && !benchmarkKeyguardBypass) {
            if (!request.optBoolean("dismiss_keyguard", true)) {
                throw new ActionFailure("KEYGUARD_BLOCKING",
                        "keyguard is blocking and dismiss_keyguard=false", false, "BLOCKED");
            }
            shell("wm dismiss-keyguard");
            dismissAttempted = true;
            SystemClock.sleep(350L);
            keyguardBlocking = km != null && km.isKeyguardLocked();
        }

        if (keyguardBlocking && !benchmarkKeyguardBypass) {
            throw new ActionFailure("KEYGUARD_BLOCKING",
                    "keyguard remained blocking after dismiss attempt", false, "BLOCKED");
        }

        return new JSONObject()
                .put("screen_initially_on", screenInitiallyOn)
                .put("wake_attempted", wakeAttempted)
                .put("screen_on", true)
                .put("keyguard_initially_blocking", keyguardInitiallyBlocking)
                .put("dismiss_keyguard_attempted", dismissAttempted)
                .put("test_benchmark_keyguard_bypass", benchmarkKeyguardBypass)
                .put("keyguard_blocking", keyguardBlocking);
    }

    private void prepareVisionBenchmark(JSONObject request) throws Exception {
        boolean duplicate = request.optBoolean("test_benchmark_duplicate", false);
        boolean clicked = request.optBoolean("test_benchmark_clicked", false);
        String ocrText = request.optString("test_benchmark_ocr_text", "");
        boolean popup = request.optBoolean("test_benchmark_popup", false);
        boolean popupTemplate = request.optBoolean("test_benchmark_popup_template", false);
        boolean staleVariant = request.optBoolean("test_benchmark_stale_variant", false);
        boolean trackClickCount = request.optBoolean("test_benchmark_track_click_count", false);
        Intent intent = new Intent();
        intent.setClassName("com.stanley.y700automation",
                "com.stanley.y700automation.VisionBenchmarkActivity");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                Intent.FLAG_ACTIVITY_CLEAR_TOP |
                Intent.FLAG_ACTIVITY_SINGLE_TOP);
        intent.putExtra("duplicate", duplicate);
        intent.putExtra("clicked", clicked);
        if (!ocrText.isEmpty()) {
            intent.putExtra("ocr_text", ocrText);
        }
        intent.putExtra("popup", popup);
        intent.putExtra("popup_template", popupTemplate);
        intent.putExtra("stale_variant", staleVariant);
        intent.putExtra("track_click_count", trackClickCount);
        context.startActivity(intent);
        long deadline = SystemClock.elapsedRealtime() + 2500L;
        while (SystemClock.elapsedRealtime() < deadline) {
            if ("com.stanley.y700automation".equals(device.getCurrentPackageName()) ||
                    isVisionBenchmarkActivityTop()) {
                return;
            }
            SystemClock.sleep(100L);
        }
        throw new ActionFailure("TEST_BENCHMARK_UNAVAILABLE",
                "VisionBenchmarkActivity did not become foreground within 2500ms",
                false, "BLOCKED");
    }

    private void maybeMutateVisionBenchmarkBeforeAction(
            JSONObject action,
            int resolveAttempt) throws Exception {
        if (!testMode || resolveAttempt != 0 ||
                !action.optBoolean("test_mutate_vision_before_action", false) ||
                !isVisionBenchmarkActivityTop()) {
            return;
        }
        Intent intent = new Intent();
        intent.setClassName("com.stanley.y700automation",
                "com.stanley.y700automation.VisionBenchmarkActivity");
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK |
                Intent.FLAG_ACTIVITY_CLEAR_TOP |
                Intent.FLAG_ACTIVITY_SINGLE_TOP);
        String ocrText = action.optString("test_mutate_vision_ocr_text", "");
        if (!ocrText.isEmpty()) intent.putExtra("ocr_text", ocrText);
        intent.putExtra("clicked", false);
        intent.putExtra("popup", false);
        intent.putExtra("stale_variant", true);
        context.startActivity(intent);
        SystemClock.sleep(180L);
    }

    private boolean isVisionBenchmarkActivityTop() {
        try {
            String activities = shell("dumpsys activity activities");
            String component = "com.stanley.y700automation/.VisionBenchmarkActivity";
            for (String line : activities.split("\n")) {
                String trimmed = line.trim();
                if ((trimmed.startsWith("topResumedActivity=") ||
                        trimmed.startsWith("ResumedActivity:")) &&
                        trimmed.contains(component)) {
                    return true;
                }
            }
        } catch (Exception ignored) {
            // Test-only bypass must fail closed if activity state cannot be proven.
        }
        return false;
    }

    private JSONObject loadRequest() throws Exception {
        Bundle args = InstrumentationRegistry.getArguments();
        String encoded = args.getString("request_b64");
        if (encoded == null || encoded.isEmpty()) {
            JSONObject request = new JSONObject();
            request.put("protocol_version", PROTOCOL_VERSION);
            request.put("job_id", "health-" + System.currentTimeMillis());
            JSONArray actions = new JSONArray();
            actions.put(new JSONObject().put("action", "health"));
            request.put("actions", actions);
            return request;
        }
        byte[] raw = Base64.decode(encoded, Base64.DEFAULT);
        return new JSONObject(new String(raw, StandardCharsets.UTF_8));
    }


    private JSONObject executeWithRetry(JSONObject action, int index) throws Exception {
        int requestedRetry = Math.max(0, Math.min(5, action.optInt("retry", 0)));
        String sideEffect = action.optString("side_effect", defaultSideEffect(action.optString("action", "")));
        boolean retrySafe = "OBSERVE_ONLY".equals(sideEffect) || "IDEMPOTENT".equals(sideEffect)
                || action.optBoolean("retry_safe", false);
        int maxRetry = retrySafe ? requestedRetry : 0;

        JSONArray delays = new JSONArray();
        JSONArray recovery = new JSONArray();
        JSONObject last = null;
        for (int attempt = 0; attempt <= maxRetry; attempt++) {
            last = executeAction(action, index);
            last.put("attempts", attempt + 1);
            if ("PASS".equals(last.optString("status"))) {
                last.put("retry_delays_ms", delays);
                if (recovery.length() > 0) last.put("recovery", recovery);
                return last;
            }

            JSONObject err = last.optJSONObject("error");
            boolean retryable = err != null && err.optBoolean("retryable", false);
            String code = err == null ? "" : err.optString("code", "");
            boolean observationFailure = "observe".equals(action.optString("action")) &&
                    "UI_OBSERVATION_FAILED".equals(code);
            if (!retryable || attempt >= maxRetry) {
                if (observationFailure) {
                    recovery.put("LEVEL_7_BLOCKED_EVIDENCE");
                    last.put("status", "BLOCKED");
                    if (err != null) err.put("retryable", false);
                }
                last.put("retry_delays_ms", delays);
                if (recovery.length() > 0) last.put("recovery", recovery);
                return last;
            }

            if (observationFailure) {
                if (attempt == 0) {
                    recovery.put("LEVEL_0_REOBSERVE");
                } else {
                    try {
                        waitStable(new JSONObject()
                                .put("timeout_ms", 2000L)
                                .put("stable_interval_ms", 300L)
                                .put("poll_interval_ms", 100L));
                        recovery.put("LEVEL_1_WAIT_STABLE");
                    } catch (Throwable ignored) {
                        recovery.put("LEVEL_1_WAIT_STABLE_UNAVAILABLE");
                    }
                }
            }

            long delay = retryBackoffMs(action, attempt);
            delays.put(delay);
            SystemClock.sleep(delay);
        }
        return last;
    }

    private String defaultSideEffect(String actionName) {
        switch (actionName) {
            case "health":
            case "observe":
            case "screenshot":
            case "find":
            case "findAll":
            case "waitFor":
            case "waitStable":
            case "assert":
                return "OBSERVE_ONLY";
            default:
                return "REVERSIBLE_LOCAL";
        }
    }

    private long retryBackoffMs(JSONObject action, int attempt) {
        JSONArray arr = action.optJSONArray("retry_backoff_ms");
        if (arr != null && arr.length() > 0) {
            int idx = Math.min(attempt, arr.length() - 1);
            return Math.max(0L, Math.min(10_000L, arr.optLong(idx, 0L)));
        }
        long value = 300L * (1L << Math.min(attempt, 5));
        return Math.min(5_000L, value);
    }

    private JSONObject executeAction(JSONObject action, int index) throws Exception {
        long started = SystemClock.elapsedRealtime();
        String name = action.optString("action", "");
        String actionId = action.optString("action_id", "action-" + index);
        JSONObject out = new JSONObject();
        out.put("action_id", actionId);
        out.put("action", name);
        lastVisionContext = null;

        try {
            JSONObject precondition = action.optJSONObject("precondition");
            if (precondition != null && !expectationSatisfied(precondition)) {
                throw new ActionFailure("PRECONDITION_FAILED", "precondition did not match current UI state", false);
            }
            switch (name) {
                case "health":
                    out.put("data", health());
                    break;
                case "observe":
                    out.put("data", observe());
                    break;
                case "screenshot":
                    out.put("data", screenshot(action.optString("filename", "screen-" + index + ".png")));
                    break;
                case "find":
                    out.put("data", find(action, true));
                    break;
                case "findAll":
                    out.put("data", find(action, false));
                    break;
                case "click":
                    out.put("data", click(action));
                    break;
                case "longClick":
                    out.put("data", longClick(action));
                    break;
                case "inputText":
                    out.put("data", inputText(action));
                    break;
                case "clearText":
                    out.put("data", clearText(action));
                    break;
                case "swipe":
                    out.put("data", swipe(action));
                    break;
                case "scroll":
                    out.put("data", scroll(action));
                    break;
                case "waitFor":
                    out.put("data", waitFor(action));
                    break;
                case "waitStable":
                    out.put("data", waitStable(action));
                    break;
                case "assert":
                    out.put("data", assertState(action));
                    break;
                case "pressBack":
                    device.pressBack();
                    out.put("data", new JSONObject().put("pressed", "BACK"));
                    verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
                    break;
                case "pressHome":
                    device.pressHome();
                    out.put("data", new JSONObject().put("pressed", "HOME"));
                    verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
                    break;
                default:
                    out.put("status", "FAILED");
                    out.put("error", error("JOB_PAYLOAD_INVALID", "unsupported action: " + name, false));
                    out.put("latency_ms", SystemClock.elapsedRealtime() - started);
                    return out;
            }
            out.put("status", "PASS");
        } catch (ActionFailure t) {
            JSONObject err = error(t.code, t.getMessage(), t.retryable);
            out.put("status", t.status);
            out.put("error", err);
            out.put("failure_evidence", captureFailureEvidence(action, index, err));
        } catch (Throwable t) {
            String code = "observe".equals(name) ? "UI_OBSERVATION_FAILED" : classify(t);
            JSONObject err = error(code, t.getClass().getSimpleName() + ": " +
                    String.valueOf(t.getMessage()), true);
            out.put("status", "FAILED");
            out.put("error", err);
            out.put("failure_evidence", captureFailureEvidence(action, index, err));
        }
        out.put("latency_ms", SystemClock.elapsedRealtime() - started);
        return out;
    }

    private JSONObject captureFailureEvidence(JSONObject action, int index, JSONObject err) {
        JSONObject evidence = new JSONObject();
        try {
            evidence.put("timestamp_ms", System.currentTimeMillis());
            evidence.put("action_index", index);
            evidence.put("action_id", action.optString("action_id", "action-" + index));
            evidence.put("action", action.optString("action", ""));
            evidence.put("selector", action.optJSONObject("selector"));
            evidence.put("precondition", action.optJSONObject("precondition"));
            evidence.put("postcondition", action.optJSONObject("expect"));
            evidence.put("error", err);
            if (lastVisionContext != null) {
                evidence.put("vision", lastVisionContext);
            }
            evidence.put("package", device == null ? JSONObject.NULL : nullableString(device.getCurrentPackageName()));

            try {
                String dump = shell("dumpsys activity activities");
                String activity = "";
                for (String line : dump.split("\\r?\\n")) {
                    String trimmed = line.trim();
                    if (trimmed.contains("mResumedActivity") || trimmed.contains("topResumedActivity")) {
                        activity = trimmed;
                        break;
                    }
                }
                evidence.put("activity", activity.isEmpty() ? JSONObject.NULL : activity);
            } catch (Throwable t) {
                evidence.put("activity_error", t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()));
            }

            try {
                JSONObject shot = screenshot("failure-action-" + index + ".png");
                evidence.put("screenshot", shot);
            } catch (Throwable t) {
                evidence.put("screenshot_error", t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()));
            }

            int savedFailures = testObserveFailuresRemaining;
            try {
                testObserveFailuresRemaining = 0;
                JSONObject observed = observe();
                JSONArray src = observed.optJSONArray("elements");
                JSONArray compact = new JSONArray();
                if (src != null) {
                    int n = Math.min(MAX_FAILURE_EVIDENCE_NODES, src.length());
                    for (int i = 0; i < n; i++) compact.put(src.get(i));
                }
                JSONObject tree = new JSONObject();
                tree.put("package", observed.opt("package"));
                tree.put("display_width", observed.opt("display_width"));
                tree.put("display_height", observed.opt("display_height"));
                tree.put("display_rotation", observed.opt("display_rotation"));
                tree.put("root_count", observed.opt("root_count"));
                tree.put("node_count", observed.opt("node_count"));
                tree.put("truncated", observed.optBoolean("truncated", false) ||
                        (src != null && src.length() > MAX_FAILURE_EVIDENCE_NODES));
                tree.put("tree_hash", observed.opt("tree_hash"));
                tree.put("elements", compact);
                evidence.put("compact_ui_tree", tree);
            } catch (Throwable t) {
                evidence.put("observation_error", t.getClass().getSimpleName() + ": " + String.valueOf(t.getMessage()));
            } finally {
                testObserveFailuresRemaining = savedFailures;
            }
        } catch (Throwable ignored) {
        }
        return evidence;
    }

    private JSONObject health() throws Exception {
        JSONObject out = new JSONObject();
        PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
        KeyguardManager km = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);

        out.put("driver_version", DRIVER_VERSION);
        out.put("protocol_version", PROTOCOL_VERSION);
        out.put("min_protocol_version", PROTOCOL_VERSION);
        out.put("max_protocol_version", PROTOCOL_VERSION);
        out.put("driver_ready", true);
        out.put("uiautomator_ready", device != null);
        out.put("screen_on", pm != null && pm.isInteractive());
        out.put("keyguard_blocking", km != null && km.isKeyguardLocked());
        out.put("current_package", device.getCurrentPackageName());
        out.put("display_width", device.getDisplayWidth());
        out.put("display_height", device.getDisplayHeight());
        out.put("display_rotation", device.getDisplayRotation());
        out.put("orientation", context.getResources().getConfiguration().orientation ==
                Configuration.ORIENTATION_LANDSCAPE ? "landscape" : "portrait");
        out.put("ime", Settings.Secure.getString(context.getContentResolver(), Settings.Secure.DEFAULT_INPUT_METHOD));
        JSONArray caps = new JSONArray();
        caps.put("health");
        caps.put("observe");
        caps.put("screenshot");
        caps.put("find");
        caps.put("findAll");
        caps.put("click");
        caps.put("longClick");
        caps.put("inputText");
        caps.put("clearText");
        caps.put("swipe");
        caps.put("scroll");
        caps.put("waitFor");
        caps.put("waitStable");
        caps.put("assert");
        caps.put("pressBack");
        caps.put("pressHome");
        out.put("capabilities", caps);
        return out;
    }

    private JSONObject observe() throws Exception {
        if (testMode && testObserveFailuresRemaining > 0) {
            testObserveFailuresRemaining--;
            throw new ActionFailure(
                    "UI_OBSERVATION_FAILED",
                    "injected observation failure for acceptance testing",
                    true);
        }
        long started = SystemClock.elapsedRealtime();
        int width = device.getDisplayWidth();
        int height = device.getDisplayHeight();
        JSONArray elements = new JSONArray();
        AtomicInteger seq = new AtomicInteger(0);
        List<AccessibilityNodeInfo> roots = device.getWindowRoots();

        for (AccessibilityNodeInfo root : roots) {
            walk(root, null, 0, width, height, seq, elements);
            if (seq.get() >= MAX_TREE_NODES) break;
        }

        String serialized = elements.toString();
        JSONObject out = new JSONObject();
        out.put("package", device.getCurrentPackageName());
        out.put("display_width", width);
        out.put("display_height", height);
        out.put("display_rotation", device.getDisplayRotation());
        out.put("root_count", roots.size());
        out.put("node_count", elements.length());
        out.put("truncated", seq.get() >= MAX_TREE_NODES);
        out.put("tree_hash", sha256(serialized));
        out.put("elements", elements);
        out.put("observe_ms", SystemClock.elapsedRealtime() - started);
        return out;
    }

    private void walk(AccessibilityNodeInfo node, String parentId, int depth,
                      int width, int height, AtomicInteger seq, JSONArray out) {
        if (node == null || seq.get() >= MAX_TREE_NODES) return;

        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        boolean validBounds = bounds.width() > 0 && bounds.height() > 0 &&
                bounds.right > 0 && bounds.bottom > 0 &&
                bounds.left < width && bounds.top < height;
        boolean include = node.isVisibleToUser() && validBounds;

        String nextParent = parentId;
        if (include) {
            String id = "n" + seq.incrementAndGet();
            nextParent = id;
            JSONObject item = new JSONObject();
            try {
                item.put("node_id", id);
                item.put("parent_id", parentId == null ? JSONObject.NULL : parentId);
                item.put("depth", depth);
                item.put("resource_id", stringOrNull(node.getViewIdResourceName()));
                item.put("text", stringOrNull(node.getText()));
                item.put("content_desc", stringOrNull(node.getContentDescription()));
                item.put("class", stringOrNull(node.getClassName()));
                item.put("package", stringOrNull(node.getPackageName()));
                item.put("clickable", node.isClickable());
                item.put("editable", node.isEditable());
                item.put("enabled", node.isEnabled());
                item.put("selected", node.isSelected());
                item.put("checkable", node.isCheckable());
                item.put("checked", node.isChecked());
                item.put("scrollable", node.isScrollable());
                JSONArray b = new JSONArray();
                b.put(bounds.left).put(bounds.top).put(bounds.right).put(bounds.bottom);
                item.put("bounds", b);
                out.put(item);
            } catch (JSONException ignored) {
            }
        }

        for (int i = 0; i < node.getChildCount(); i++) {
            AccessibilityNodeInfo child = node.getChild(i);
            if (child != null) {
                walk(child, nextParent, depth + 1, width, height, seq, out);
            }
            if (seq.get() >= MAX_TREE_NODES) break;
        }
    }


    private boolean hasSemanticCriteria(JSONObject spec) {
        if (spec == null) return false;
        String[] keys = new String[]{
                "resource_id", "text", "text_contains", "content_desc",
                "content_desc_contains", "class_name", "package", "clickable",
                "enabled", "selected", "checked", "checkable", "scrollable",
                "has_descendant", "has_child", "has_parent", "has_ancestor"
        };
        for (String key : keys) {
            if (spec.has(key)) return true;
        }
        return false;
    }

    private VisionTemplateLocator ensureVisionLocator() throws ActionFailure {
        if (visionConfig == null || !visionConfig.enabled) {
            throw new ActionFailure(
                    VisionTemplateLocator.ERR_POLICY_BLOCKED,
                    "vision_enabled=false",
                    false,
                    "BLOCKED");
        }
        if (visionLocator == null) {
            try {
                long seed = Integer.toUnsignedLong(
                        ((jobId == null ? "" : jobId) + "|" +
                                (sessionId == null ? "" : sessionId)).hashCode());
                visionLocator = new VisionTemplateLocator(
                        instrumentation, device, visionConfig, seed);
            } catch (VisionV0Harness.VisionFailure e) {
                throw visionActionFailure(e);
            }
        }
        return visionLocator;
    }

    private OcrTextLocator ensureOcrLocator() throws ActionFailure {
        if (visionConfig == null || !visionConfig.enabled) {
            throw new ActionFailure(
                    OcrTextLocator.ERR_POLICY_BLOCKED,
                    "vision_enabled=false",
                    false,
                    "BLOCKED");
        }
        if (!visionConfig.ocrEnabled) {
            throw new ActionFailure(
                    OcrTextLocator.ERR_POLICY_BLOCKED,
                    "ocr_enabled=false",
                    false,
                    "BLOCKED");
        }
        if (ocrLocator == null) {
            ocrLocator = new OcrTextLocator(instrumentation, device, visionConfig);
        }
        return ocrLocator;
    }

    private ActionFailure visionActionFailure(VisionV0Harness.VisionFailure e) {
        boolean retryable =
                VisionV0Harness.ERR_TEMPLATE_NOT_FOUND.equals(e.code) ||
                OcrTextLocator.ERR_NOT_FOUND.equals(e.code) ||
                OcrTextLocator.ERR_TIMEOUT.equals(e.code) ||
                VisionV0Harness.ERR_CAPTURE_FAILED.equals(e.code) ||
                VisionV0Harness.ERR_STALE_TARGET.equals(e.code) ||
                VisionV0Harness.ERR_ROTATION_MISMATCH.equals(e.code) ||
                VisionV0Harness.ERR_OOM_THROTTLED.equals(e.code);
        String status = VisionTemplateLocator.ERR_POLICY_BLOCKED.equals(e.code)
                ? "BLOCKED" : "FAILED";
        return new ActionFailure(e.code, e.getMessage(), retryable, status);
    }

    private void validateVisionSelectors(JSONObject spec) throws ActionFailure {
        if (spec == null) return;
        try {
            String directType = spec.optString("type");
            if ("vision_template".equals(directType)) {
                VisionTemplateLocator.validateTemplateSpec(spec);
                return;
            }
            if ("vision_text".equals(directType)) {
                OcrTextLocator.validateTextSpec(spec);
                return;
            }
            if (spec.has("type")) {
                throw new VisionV0Harness.VisionFailure(
                        VisionV0Harness.ERR_TEMPLATE_CONFIG,
                        "V2 supports only type=vision_template or type=vision_text");
            }
            JSONArray fallback = spec.optJSONArray("fallback");
            if (spec.has("fallback") && fallback == null) {
                throw new VisionV0Harness.VisionFailure(
                        VisionV0Harness.ERR_TEMPLATE_CONFIG,
                        "fallback must be an array");
            }
            if (fallback != null) {
                if (fallback.length() > 8) {
                    throw new VisionV0Harness.VisionFailure(
                            VisionV0Harness.ERR_TEMPLATE_CONFIG,
                            "fallback contains more than 8 vision candidates");
                }
                for (int i = 0; i < fallback.length(); i++) {
                    JSONObject item = fallback.optJSONObject(i);
                    if (item == null) {
                        throw new VisionV0Harness.VisionFailure(
                                VisionV0Harness.ERR_TEMPLATE_CONFIG,
                                "V3 fallback entries must be vision objects");
                    }
                    String type = item.optString("type");
                    if ("vision_template".equals(type)) {
                        VisionTemplateLocator.validateTemplateSpec(item);
                    } else if ("vision_text".equals(type)) {
                        OcrTextLocator.validateTextSpec(item);
                    } else {
                        throw new VisionV0Harness.VisionFailure(
                                VisionV0Harness.ERR_TEMPLATE_CONFIG,
                                "V3 fallback entries must be vision_template or vision_text");
                    }
                }
            }
        } catch (VisionV0Harness.VisionFailure e) {
            throw visionActionFailure(e);
        }
    }

    private List<JSONObject> orderedVisionCandidates(JSONObject selector) {
        List<JSONObject> templates = new ArrayList<>();
        List<JSONObject> ocr = new ArrayList<>();
        if (selector == null) return templates;

        String directType = selector.optString("type");
        if ("vision_template".equals(directType)) {
            templates.add(selector);
            return templates;
        }
        if ("vision_text".equals(directType)) {
            ocr.add(selector);
            return ocr;
        }

        JSONArray fallback = selector.optJSONArray("fallback");
        if (fallback == null) return templates;
        for (int i = 0; i < fallback.length(); i++) {
            JSONObject item = fallback.optJSONObject(i);
            if (item == null) continue;
            String type = item.optString("type");
            if ("vision_template".equals(type)) templates.add(item);
            else if ("vision_text".equals(type)) ocr.add(item);
        }
        templates.addAll(ocr);
        return templates;
    }

    private boolean isVisionCandidateEnabled(JSONObject spec) {
        if (spec == null || visionConfig == null || !visionConfig.enabled ||
                !"fallback".equals(visionConfig.mode)) return false;
        String type = spec.optString("type");
        if ("vision_template".equals(type)) return visionConfig.templateEnabled;
        if ("vision_text".equals(type)) return visionConfig.ocrEnabled;
        return false;
    }

    private boolean isSoftLocatorMiss(ActionFailure failure) {
        return VisionV0Harness.ERR_TEMPLATE_NOT_FOUND.equals(failure.code) ||
                OcrTextLocator.ERR_NOT_FOUND.equals(failure.code) ||
                OcrTextLocator.ERR_TIMEOUT.equals(failure.code);
    }

    private boolean isStaleVisionFailure(VisionV0Harness.VisionFailure failure) {
        return VisionV0Harness.ERR_STALE_TARGET.equals(failure.code) ||
                VisionV0Harness.ERR_ROTATION_MISMATCH.equals(failure.code);
    }

    private void attachVisionMetrics(JSONObject result) {
        try {
            if (visionRequested && visionConfig != null) {
                result.put("vision_policy", visionConfig.json());
            }
            JSONObject combined = visionLocator != null
                    ? visionLocator.metrics().json()
                    : new JSONObject();
            if (ocrLocator != null) {
                JSONObject ocr = ocrLocator.metrics().json();
                result.put("ocr_metrics", ocr);
                result.put("ocr_runtime", ocrLocator.runtimeStatus());
                Iterator<String> keys = ocr.keys();
                while (keys.hasNext()) {
                    String key = keys.next();
                    combined.put(key, ocr.get(key));
                }
            }
            combined.put("semantic_to_vision_fallback_count",
                    semanticToVisionFallbackCount);
            combined.put("hybrid_template_to_ocr_fallback_count",
                    hybridTemplateToOcrFallbackCount);
            combined.put("vision_stale_reresolve_count",
                    visionStaleReresolveCount);
            combined.put("vision_recovery_count", visionRecoveryCount);
            if (combined.length() > 0) {
                result.put("vision_metrics", combined);
            }
        } catch (Throwable ignored) {
        }
    }

    private void validateSelectorKeys(JSONObject spec) throws ActionFailure {
        if (spec == null || spec.length() == 0) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "selector is required", false);
        }
        validateVisionSelectors(spec);
        if ("vision_template".equals(spec.optString("type")) ||
                "vision_text".equals(spec.optString("type"))) {
            return;
        }

        Iterator<String> keys = spec.keys();
        while (keys.hasNext()) {
            String key = keys.next();
            switch (key) {
                case "resource_id":
                case "text":
                case "text_contains":
                case "content_desc":
                case "content_desc_contains":
                case "class_name":
                case "package":
                case "clickable":
                case "enabled":
                case "selected":
                case "checked":
                case "checkable":
                case "scrollable":
                case "has_descendant":
                case "has_child":
                case "has_parent":
                case "has_ancestor":
                case "fallback":
                    break;
                default:
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "unsupported selector key: " + key,
                            false);
            }
        }
    }

    private BySelector buildSelector(JSONObject spec) throws Exception {
        if (spec == null || spec.length() == 0) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "selector is required", false);
        }
        validateSelectorKeys(spec);

        BySelector selector;
        String seed;
        if (spec.has("resource_id")) {
            seed = "resource_id";
            selector = By.res(spec.getString(seed));
        } else if (spec.has("text")) {
            seed = "text";
            selector = By.text(spec.getString(seed));
        } else if (spec.has("text_contains")) {
            seed = "text_contains";
            selector = By.textContains(spec.getString(seed));
        } else if (spec.has("content_desc")) {
            seed = "content_desc";
            selector = By.desc(spec.getString(seed));
        } else if (spec.has("content_desc_contains")) {
            seed = "content_desc_contains";
            selector = By.descContains(spec.getString(seed));
        } else if (spec.has("class_name")) {
            seed = "class_name";
            selector = By.clazz(spec.getString(seed));
        } else if (spec.has("package")) {
            seed = "package";
            selector = By.pkg(spec.getString(seed));
        } else if (spec.has("clickable")) {
            seed = "clickable";
            selector = By.clickable(spec.getBoolean(seed));
        } else if (spec.has("enabled")) {
            seed = "enabled";
            selector = By.enabled(spec.getBoolean(seed));
        } else if (spec.has("selected")) {
            seed = "selected";
            selector = By.selected(spec.getBoolean(seed));
        } else if (spec.has("checked")) {
            seed = "checked";
            selector = By.checked(spec.getBoolean(seed));
        } else if (spec.has("checkable")) {
            seed = "checkable";
            selector = By.checkable(spec.getBoolean(seed));
        } else if (spec.has("scrollable")) {
            seed = "scrollable";
            selector = By.scrollable(spec.getBoolean(seed));
        } else {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "selector has no supported criteria", false);
        }

        if (spec.has("resource_id") && !"resource_id".equals(seed)) selector.res(spec.getString("resource_id"));
        if (spec.has("text") && !"text".equals(seed)) selector.text(spec.getString("text"));
        if (spec.has("text_contains") && !"text_contains".equals(seed)) selector.textContains(spec.getString("text_contains"));
        if (spec.has("content_desc") && !"content_desc".equals(seed)) selector.desc(spec.getString("content_desc"));
        if (spec.has("content_desc_contains") && !"content_desc_contains".equals(seed)) selector.descContains(spec.getString("content_desc_contains"));
        if (spec.has("class_name") && !"class_name".equals(seed)) selector.clazz(spec.getString("class_name"));
        if (spec.has("package") && !"package".equals(seed)) selector.pkg(spec.getString("package"));
        if (spec.has("clickable") && !"clickable".equals(seed)) selector.clickable(spec.getBoolean("clickable"));
        if (spec.has("enabled") && !"enabled".equals(seed)) selector.enabled(spec.getBoolean("enabled"));
        if (spec.has("selected") && !"selected".equals(seed)) selector.selected(spec.getBoolean("selected"));
        if (spec.has("checked") && !"checked".equals(seed)) selector.checked(spec.getBoolean("checked"));
        if (spec.has("checkable") && !"checkable".equals(seed)) selector.checkable(spec.getBoolean("checkable"));
        if (spec.has("scrollable") && !"scrollable".equals(seed)) selector.scrollable(spec.getBoolean("scrollable"));
        if (spec.has("has_descendant")) selector.hasDescendant(buildSelector(spec.getJSONObject("has_descendant")));
        if (spec.has("has_child")) selector.hasChild(buildSelector(spec.getJSONObject("has_child")));
        if (spec.has("has_parent")) selector.hasParent(buildSelector(spec.getJSONObject("has_parent")));
        if (spec.has("has_ancestor")) selector.hasAncestor(buildSelector(spec.getJSONObject("has_ancestor")));
        return selector;
    }

    private List<UiObject2> findObjects(JSONObject spec) throws Exception {
        return device.findObjects(buildSelector(spec));
    }

    private UiObject2 findUnique(JSONObject spec) throws Exception {
        List<UiObject2> matches = findObjects(spec);
        if (matches.isEmpty()) {
            throw new ActionFailure("ELEMENT_NOT_FOUND", "selector matched 0 elements", true);
        }
        if (matches.size() > 1) {
            throw new ActionFailure("SELECTOR_AMBIGUOUS",
                    "selector matched " + matches.size() + " elements", false);
        }
        return matches.get(0);
    }

    private JSONObject find(JSONObject action, boolean unique) throws Exception {
        JSONObject spec = action.optJSONObject("selector");
        List<UiObject2> matches = findObjects(spec);
        JSONObject out = new JSONObject();
        out.put("count", matches.size());
        if (unique) {
            if (matches.isEmpty()) {
                throw new ActionFailure("ELEMENT_NOT_FOUND", "selector matched 0 elements", true);
            }
            if (matches.size() > 1) {
                throw new ActionFailure("SELECTOR_AMBIGUOUS",
                        "selector matched " + matches.size() + " elements", false);
            }
            out.put("element", elementJson(matches.get(0)));
        } else {
            JSONArray rows = new JSONArray();
            int limit = Math.min(matches.size(), action.optInt("limit", 100));
            for (int i = 0; i < limit; i++) rows.put(elementJson(matches.get(i)));
            out.put("elements", rows);
            out.put("truncated", matches.size() > limit);
        }
        return out;
    }

    private JSONObject click(JSONObject action) throws Exception {
        JSONObject selector = action.optJSONObject("selector");
        if (selector == null || selector.length() == 0) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "click requires selector", false);
        }
        validateSelectorKeys(selector);
        validateVisionRecovery(action);
        currentVisionRecoveryEvents = new JSONArray();

        List<JSONObject> candidates = orderedVisionCandidates(selector);
        boolean semanticAvailable = hasSemanticCriteria(selector);
        if (semanticAvailable) {
            List<UiObject2> matches = findObjects(selector);
            if (matches.size() == 1) {
                UiObject2 target = matches.get(0);
                JSONObject resolved = elementJson(target);
                target.click();
                verifyExpectation(
                        action.optJSONObject("expect"),
                        action.optLong("timeout_ms", 10000L));
                return new JSONObject()
                        .put("locator_source", "semantic")
                        .put("resolved_element", resolved);
            }

            if (candidates.isEmpty() || visionConfig == null || !visionConfig.enabled) {
                if (matches.isEmpty()) {
                    throw new ActionFailure(
                            "ELEMENT_NOT_FOUND", "selector matched 0 elements", true);
                }
                throw new ActionFailure(
                        "SELECTOR_AMBIGUOUS",
                        "selector matched " + matches.size() + " elements",
                        false);
            }
            semanticToVisionFallbackCount++;
        } else if (candidates.isEmpty()) {
            throw new ActionFailure(
                    "JOB_PAYLOAD_INVALID",
                    "selector has neither semantic criteria nor an explicit Vision locator",
                    false);
        }

        String sideEffect = action.optString(
                "side_effect", defaultSideEffect(action.optString("action", "")));
        if ("EXTERNAL_IRREVERSIBLE".equals(sideEffect)) {
            throw new ActionFailure(
                    VisionTemplateLocator.ERR_POLICY_BLOCKED,
                    "Vision routing remains denied for EXTERNAL_IRREVERSIBLE actions",
                    false,
                    "BLOCKED");
        }

        return clickVisionCascade(action, selector, candidates, semanticAvailable);
    }

    private JSONObject clickVisionCascade(
            JSONObject action,
            JSONObject selector,
            List<JSONObject> candidates,
            boolean semanticAvailable) throws Exception {
        JSONArray trace = new JSONArray();
        ActionFailure lastMiss = null;
        boolean recoveryAttempted = false;
        long[] backoffMs = new long[]{100L, 200L, 400L};

        for (int round = 0; round <= backoffMs.length; round++) {
            boolean attempted = false;
            boolean templateMiss = false;
            for (int i = 0; i < candidates.size(); i++) {
                JSONObject spec = candidates.get(i);
                if (!isVisionCandidateEnabled(spec)) continue;
                attempted = true;
                String type = spec.optString("type");
                if ("vision_text".equals(type) && templateMiss) {
                    hybridTemplateToOcrFallbackCount++;
                }

                try {
                    JSONObject out;
                    if ("vision_template".equals(type)) {
                        out = clickTemplateCandidate(
                                action, selector, spec, semanticAvailable, round, i);
                    } else if ("vision_text".equals(type)) {
                        out = clickOcrCandidate(
                                action, selector, spec, semanticAvailable, round, i);
                    } else {
                        continue;
                    }
                    out.put("fallback_trace", trace);
                    if (currentVisionRecoveryEvents != null &&
                            currentVisionRecoveryEvents.length() > 0) {
                        out.put("vision_recovery", currentVisionRecoveryEvents);
                    }
                    return out;
                } catch (ActionFailure e) {
                    if (!isSoftLocatorMiss(e)) throw e;
                    lastMiss = e;
                    if ("vision_template".equals(type)) templateMiss = true;
                    trace.put(new JSONObject()
                            .put("round", round)
                            .put("candidate_index", i)
                            .put("locator_type", type)
                            .put("status", "MISS")
                            .put("error_code", e.code));
                }
            }

            if (!attempted) {
                throw new ActionFailure(
                        VisionTemplateLocator.ERR_POLICY_BLOCKED,
                        "no enabled Vision backend is eligible for selector",
                        false,
                        "BLOCKED");
            }

            if (!recoveryAttempted && attemptKnownPopupRecovery(action)) {
                recoveryAttempted = true;
                invalidateVisionObservationCaches();
                trace.put(new JSONObject()
                        .put("round", round)
                        .put("status", "RECOVERY_APPLIED")
                        .put("recovery", "KNOWN_POPUP"));
                // Recovery itself must not consume the final retry slot. Repeat
                // the same round once against the newly-observed screen.
                round = Math.max(-1, round - 1);
                continue;
            }

            if (round < backoffMs.length) {
                SystemClock.sleep(backoffMs[round]);
            }
        }

        String detail = lastMiss == null ? "no eligible visual target" :
                lastMiss.code + ": " + lastMiss.getMessage();
        throw new ActionFailure(
                "VISUAL_TIMEOUT",
                "semantic/template/OCR cascade exhausted after bounded backoff; last=" + detail,
                true);
    }

    private JSONObject clickTemplateCandidate(
            JSONObject action,
            JSONObject selector,
            JSONObject templateSpec,
            boolean semanticAvailable,
            int round,
            int candidateIndex) throws Exception {
        JSONObject effectiveVision = new JSONObject(templateSpec.toString());
        if (!effectiveVision.has("expected_package") && selector.has("package")) {
            effectiveVision.put("expected_package", selector.getString("package"));
        }
        VisionTemplateLocator locator = ensureVisionLocator();
        VisionTemplateLocator.Resolved resolved = null;
        for (int resolveAttempt = 0; resolveAttempt < 2; resolveAttempt++) {
            try {
                resolved = locator.resolve(effectiveVision);
                lastVisionContext = new JSONObject(resolved.metadata.toString())
                        .put("route", semanticAvailable
                                ? "SEMANTIC_TO_TEMPLATE"
                                : "VISION_TEMPLATE")
                        .put("hybrid_round", round)
                        .put("candidate_index", candidateIndex)
                        .put("resolve_attempt", resolveAttempt + 1);
                maybeMutateVisionBenchmarkBeforeAction(action, resolveAttempt);
                locator.validatePreAction(resolved);
                break;
            } catch (VisionV0Harness.VisionFailure e) {
                if (isStaleVisionFailure(e) && resolveAttempt == 0) {
                    visionStaleReresolveCount++;
                    continue;
                }
                lastVisionContext = visionFailureContext(
                        "vision_template", effectiveVision, e, round, candidateIndex);
                throw visionActionFailure(e);
            }
        }
        if (resolved == null) {
            throw new ActionFailure(
                    VisionV0Harness.ERR_STALE_TARGET,
                    "template target could not be re-resolved",
                    true);
        }

        int[] point = locator.clickPoint(resolved, false);
        lastVisionContext.put("click_policy", resolved.clickPolicy)
                .put("click_point", new JSONArray().put(point[0]).put(point[1]));
        boolean clicked = device.click(point[0], point[1]);
        if (!clicked) {
            throw new ActionFailure(
                    "ACTION_FAILED",
                    "UiDevice.click returned false for vision target",
                    true);
        }

        try {
            verifyExpectation(
                    action.optJSONObject("expect"),
                    action.optLong("timeout_ms", 10000L));
            lastVisionContext.put("postcondition_pass", true);
        } catch (ActionFailure e) {
            locator.notePostconditionFailure();
            lastVisionContext.put("postcondition_pass", false)
                    .put("postcondition_error", e.getMessage());
            throw new ActionFailure(
                    "VISION_POSTCONDITION_FAILED",
                    e.getMessage(),
                    e.retryable,
                    e.status);
        }

        return new JSONObject()
                .put("locator_source", "vision_template")
                .put("resolved_target", resolved.metadata)
                .put("click_point", new JSONArray().put(point[0]).put(point[1]))
                .put("postcondition_pass", true);
    }

    private JSONObject clickOcrCandidate(
            JSONObject action,
            JSONObject selector,
            JSONObject ocrSpec,
            boolean semanticAvailable,
            int round,
            int candidateIndex) throws Exception {
        JSONObject effectiveOcr = new JSONObject(ocrSpec.toString());
        if (!effectiveOcr.has("expected_package") && selector.has("package")) {
            effectiveOcr.put("expected_package", selector.getString("package"));
        }

        OcrTextLocator locator = ensureOcrLocator();
        OcrTextLocator.Resolved resolved = null;
        for (int resolveAttempt = 0; resolveAttempt < 2; resolveAttempt++) {
            try {
                resolved = locator.resolve(
                        effectiveOcr,
                        action.optLong("timeout_ms", 10000L));
                lastVisionContext = new JSONObject(resolved.metadata.toString())
                        .put("route", semanticAvailable
                                ? "SEMANTIC_TO_OCR"
                                : "VISION_TEXT")
                        .put("hybrid_round", round)
                        .put("candidate_index", candidateIndex)
                        .put("resolve_attempt", resolveAttempt + 1);
                maybeMutateVisionBenchmarkBeforeAction(action, resolveAttempt);
                locator.validatePreAction(resolved);
                break;
            } catch (VisionV0Harness.VisionFailure e) {
                if (isStaleVisionFailure(e) && resolveAttempt == 0) {
                    visionStaleReresolveCount++;
                    locator.invalidateObservationCache();
                    continue;
                }
                lastVisionContext = visionFailureContext(
                        "vision_text", effectiveOcr, e, round, candidateIndex);
                throw visionActionFailure(e);
            }
        }
        if (resolved == null) {
            throw new ActionFailure(
                    VisionV0Harness.ERR_STALE_TARGET,
                    "OCR target could not be re-resolved",
                    true);
        }

        int[] point = new int[]{resolved.centerX, resolved.centerY};
        lastVisionContext.put("click_point", new JSONArray().put(point[0]).put(point[1]));
        boolean clicked = device.click(point[0], point[1]);
        if (!clicked) {
            throw new ActionFailure(
                    "ACTION_FAILED",
                    "UiDevice.click returned false for OCR target",
                    true);
        }

        try {
            verifyExpectation(
                    action.optJSONObject("expect"),
                    action.optLong("timeout_ms", 10000L));
            lastVisionContext.put("postcondition_pass", true);
        } catch (ActionFailure e) {
            locator.notePostconditionFailure();
            lastVisionContext.put("postcondition_pass", false)
                    .put("postcondition_error", e.getMessage());
            throw new ActionFailure(
                    "VISION_POSTCONDITION_FAILED",
                    e.getMessage(),
                    e.retryable,
                    e.status);
        }

        return new JSONObject()
                .put("locator_source", "vision_text")
                .put("resolved_target", resolved.metadata)
                .put("click_point", new JSONArray().put(point[0]).put(point[1]))
                .put("postcondition_pass", true);
    }

    private JSONObject visionFailureContext(
            String type,
            JSONObject spec,
            VisionV0Harness.VisionFailure failure,
            int round,
            int candidateIndex) throws Exception {
        JSONObject out = new JSONObject()
                .put("locator_type", type)
                .put("error_code", failure.code)
                .put("error_message", failure.getMessage())
                .put("hybrid_round", round)
                .put("candidate_index", candidateIndex);
        if ("vision_template".equals(type)) {
            out.put("template", spec.optString("template", ""))
                    .put("template_sha256", spec.optString("template_sha256", ""));
        } else {
            out.put("pattern", spec.optString("pattern", ""))
                    .put("match", spec.optString("match", "substring"));
        }
        return out;
    }

    private void validateVisionRecovery(JSONObject action) throws Exception {
        if (!action.has("vision_recovery")) return;
        JSONObject recovery = action.optJSONObject("vision_recovery");
        if (recovery == null) {
            throw new ActionFailure(
                    "JOB_PAYLOAD_INVALID",
                    "vision_recovery must be an object",
                    false);
        }
        Iterator<String> recoveryKeys = recovery.keys();
        while (recoveryKeys.hasNext()) {
            String key = recoveryKeys.next();
            if (!"known_popups".equals(key)) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "unsupported vision_recovery key: " + key,
                        false);
            }
        }
        JSONArray popups = recovery.optJSONArray("known_popups");
        if (popups == null) {
            throw new ActionFailure(
                    "JOB_PAYLOAD_INVALID",
                    "vision_recovery.known_popups must be an array",
                    false);
        }
        if (popups.length() > 4) {
            throw new ActionFailure(
                    "JOB_PAYLOAD_INVALID",
                    "vision_recovery.known_popups supports at most 4 entries",
                    false);
        }
        for (int i = 0; i < popups.length(); i++) {
            JSONObject popup = popups.optJSONObject(i);
            if (popup == null) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "known popup recovery entry must be an object",
                        false);
            }
            Iterator<String> keys = popup.keys();
            while (keys.hasNext()) {
                String key = keys.next();
                if (!"expected_package".equals(key) &&
                        !"semantic".equals(key) &&
                        !"template".equals(key) &&
                        !"expect".equals(key) &&
                        !"timeout_ms".equals(key)) {
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "unsupported known popup key: " + key,
                            false);
                }
            }
            String expectedPackage = popup.optString("expected_package", "");
            if (expectedPackage.isEmpty()) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "known popup recovery requires expected_package",
                        false);
            }
            JSONObject semantic = popup.optJSONObject("semantic");
            JSONObject template = popup.optJSONObject("template");
            if (semantic == null && template == null) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "known popup recovery requires semantic or template dismiss",
                        false);
            }
            if (semantic != null) {
                if (semantic.has("fallback") || semantic.has("type") ||
                        !hasSemanticCriteria(semantic)) {
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "popup semantic dismiss must be semantic-only",
                            false);
                }
                validateSelectorKeys(semantic);
            }
            if (template != null) {
                try {
                    VisionTemplateLocator.validateTemplateSpec(template);
                } catch (VisionV0Harness.VisionFailure e) {
                    throw visionActionFailure(e);
                }
                if (!template.has("roi") && !template.has("roi_ratio")) {
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "popup template recovery requires bounded roi or roi_ratio",
                            false);
                }
            }
            long timeoutMs = popup.optLong("timeout_ms", 2000L);
            if (timeoutMs < 250L || timeoutMs > 10_000L) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "popup recovery timeout_ms must be 250..10000",
                        false);
            }
        }
    }

    private boolean attemptKnownPopupRecovery(JSONObject action) throws Exception {
        JSONObject recovery = action.optJSONObject("vision_recovery");
        if (recovery == null) return false;
        JSONArray popups = recovery.optJSONArray("known_popups");
        if (popups == null || popups.length() == 0) return false;
        if (popups.length() > 4) {
            throw new ActionFailure(
                    "JOB_PAYLOAD_INVALID",
                    "vision_recovery.known_popups supports at most 4 entries",
                    false);
        }

        String currentPackage = device.getCurrentPackageName();
        for (int i = 0; i < popups.length(); i++) {
            JSONObject popup = popups.optJSONObject(i);
            if (popup == null) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "known popup recovery entry must be an object",
                        false);
            }
            String expectedPackage = popup.optString("expected_package", "");
            if (expectedPackage.isEmpty()) {
                throw new ActionFailure(
                        "JOB_PAYLOAD_INVALID",
                        "known popup recovery requires expected_package",
                        false);
            }
            if (!expectedPackage.equals(currentPackage)) continue;

            JSONObject semantic = popup.optJSONObject("semantic");
            if (semantic != null) {
                if (semantic.has("fallback") || semantic.has("type") ||
                        !hasSemanticCriteria(semantic)) {
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "popup semantic dismiss must be semantic-only",
                            false);
                }
                validateSelectorKeys(semantic);
                List<UiObject2> matches = findObjects(semantic);
                if (matches.size() == 1) {
                    matches.get(0).click();
                    verifyPopupRecoveryExpectation(popup);
                    recordPopupRecovery(i, "semantic");
                    return true;
                }
            }

            JSONObject template = popup.optJSONObject("template");
            if (template != null) {
                VisionTemplateLocator.validateTemplateSpec(template);
                if (!template.has("roi") && !template.has("roi_ratio")) {
                    throw new ActionFailure(
                            "JOB_PAYLOAD_INVALID",
                            "popup template recovery requires bounded roi or roi_ratio",
                            false);
                }
                JSONObject effective = new JSONObject(template.toString())
                        .put("expected_package", expectedPackage);
                try {
                    VisionTemplateLocator locator = ensureVisionLocator();
                    VisionTemplateLocator.Resolved resolved = locator.resolve(effective);
                    locator.validatePreAction(resolved);
                    int[] point = locator.clickPoint(resolved, true);
                    if (!device.click(point[0], point[1])) {
                        throw new ActionFailure(
                                "ACTION_FAILED",
                                "UiDevice.click returned false for popup recovery",
                                true);
                    }
                    verifyPopupRecoveryExpectation(popup);
                    recordPopupRecovery(i, "vision_template");
                    return true;
                } catch (VisionV0Harness.VisionFailure e) {
                    if (VisionV0Harness.ERR_TEMPLATE_NOT_FOUND.equals(e.code)) continue;
                    throw visionActionFailure(e);
                }
            }
        }
        return false;
    }

    private void verifyPopupRecoveryExpectation(JSONObject popup) throws Exception {
        JSONObject expect = popup.optJSONObject("expect");
        if (expect != null) {
            verifyExpectation(expect, Math.max(250L, popup.optLong("timeout_ms", 2000L)));
        } else {
            SystemClock.sleep(100L);
        }
    }

    private void recordPopupRecovery(int index, String source) throws Exception {
        visionRecoveryCount++;
        if (currentVisionRecoveryEvents == null) currentVisionRecoveryEvents = new JSONArray();
        currentVisionRecoveryEvents.put(new JSONObject()
                .put("popup_index", index)
                .put("source", source)
                .put("status", "DISMISSED"));
    }

    private void invalidateVisionObservationCaches() {
        if (ocrLocator != null) ocrLocator.invalidateObservationCache();
    }

    private JSONObject longClick(JSONObject action) throws Exception {
        UiObject2 target = findUnique(action.optJSONObject("selector"));
        JSONObject resolved = elementJson(target);
        target.longClick();
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        return new JSONObject().put("resolved_element", resolved);
    }

    private JSONObject inputText(JSONObject action) throws Exception {
        if (!action.has("text")) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "inputText requires text", false);
        }
        String text = action.getString("text");
        JSONObject selector = action.optJSONObject("selector");
        UiObject2 target = findUnique(selector);
        target.click();
        if (action.optBoolean("clear_first", true)) target.clear();
        target.setText(text);

        UiObject2 refreshed = findUnique(selector);
        String actual = refreshed.getText();
        if (!text.equals(actual)) {
            throw new ActionFailure("TEXT_VALUE_MISMATCH",
                    "expected text length=" + text.length() + " actual=" + String.valueOf(actual), true);
        }

        if (action.optBoolean("dismiss_ime", true)) {
            device.pressBack();
            SystemClock.sleep(150L);
        }
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        JSONObject out = new JSONObject();
        out.put("text_length", text.length());
        out.put("actual_text", nullableString(actual));
        return out;
    }

    private JSONObject clearText(JSONObject action) throws Exception {
        JSONObject selector = action.optJSONObject("selector");
        UiObject2 target = findUnique(selector);
        target.clear();
        UiObject2 refreshed = findUnique(selector);
        String actual = refreshed.getText();
        if (actual != null && !actual.isEmpty()) {
            throw new ActionFailure("TEXT_VALUE_MISMATCH", "field is not empty after clearText", true);
        }
        if (action.optBoolean("dismiss_ime", true)) {
            device.pressBack();
            SystemClock.sleep(150L);
        }
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        return new JSONObject().put("cleared", true);
    }

    private JSONObject swipe(JSONObject action) throws Exception {
        int width = device.getDisplayWidth();
        int height = device.getDisplayHeight();
        int x1;
        int y1;
        int x2;
        int y2;

        if (action.has("x1") && action.has("y1") && action.has("x2") && action.has("y2")) {
            x1 = action.getInt("x1");
            y1 = action.getInt("y1");
            x2 = action.getInt("x2");
            y2 = action.getInt("y2");
        } else {
            double fx1 = action.optDouble("from_x", 0.5);
            double fy1 = action.optDouble("from_y", 0.8);
            double fx2 = action.optDouble("to_x", 0.5);
            double fy2 = action.optDouble("to_y", 0.2);
            if (fx1 < 0 || fx1 > 1 || fy1 < 0 || fy1 > 1 || fx2 < 0 || fx2 > 1 || fy2 < 0 || fy2 > 1) {
                throw new ActionFailure("JOB_PAYLOAD_INVALID", "normalized swipe coordinates must be 0..1", false);
            }
            x1 = (int) Math.round(width * fx1);
            y1 = (int) Math.round(height * fy1);
            x2 = (int) Math.round(width * fx2);
            y2 = (int) Math.round(height * fy2);
        }
        int steps = Math.max(5, Math.min(200, action.optInt("steps", 30)));
        boolean ok = device.swipe(x1, y1, x2, y2, steps);
        if (!ok) throw new ActionFailure("POSTCONDITION_FAILED", "UiDevice.swipe returned false", true);
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        return new JSONObject()
                .put("from", new JSONArray().put(x1).put(y1))
                .put("to", new JSONArray().put(x2).put(y2))
                .put("steps", steps);
    }

    private JSONObject scroll(JSONObject action) throws Exception {
        UiObject2 target = findUnique(action.optJSONObject("selector"));
        String raw = action.optString("direction", "DOWN").toUpperCase(Locale.ROOT);
        Direction direction;
        try {
            direction = Direction.valueOf(raw);
        } catch (IllegalArgumentException e) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "invalid direction: " + raw, false);
        }
        float percent = (float) action.optDouble("percent", 0.8);
        if (percent <= 0.0f || percent > 1.0f) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "scroll percent must be >0 and <=1", false);
        }
        boolean moved = target.scroll(direction, percent);
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        return new JSONObject().put("direction", raw).put("percent", percent).put("moved", moved);
    }


    private JSONObject waitStable(JSONObject action) throws Exception {
        long timeout = Math.max(500L, Math.min(60_000L, action.optLong("timeout_ms", 10_000L)));
        long stableInterval = Math.max(100L, Math.min(timeout, action.optLong("stable_interval_ms", 500L)));
        long pollInterval = Math.max(50L, Math.min(stableInterval, action.optLong("poll_interval_ms", 100L)));
        boolean requireScreenshot = action.optBoolean("require_stable_screenshot", false);

        StableResult result = UiDeviceExt.waitForStableInActiveWindow(
                device, timeout, stableInterval, pollInterval, requireScreenshot);
        if (result.isTimeout()) {
            throw new ActionFailure("ACTION_TIMEOUT", "UI did not become stable before timeout", true);
        }
        return new JSONObject()
                .put("stable", true)
                .put("stable_interval_ms", stableInterval)
                .put("require_stable_screenshot", requireScreenshot);
    }

    private JSONObject waitFor(JSONObject action) throws Exception {
        long timeout = Math.max(0L, Math.min(60000L, action.optLong("timeout_ms", 10000L)));
        long deadline = SystemClock.elapsedRealtime() + timeout;
        JSONObject expect = action.optJSONObject("expect");
        JSONObject selector = action.optJSONObject("selector");
        String pkg = action.optString("package", "");
        boolean requireUnique = action.optBoolean("unique", true);
        int lastCount = -1;

        do {
            if (selector != null) {
                List<UiObject2> matches = findObjects(selector);
                lastCount = matches.size();
                if ((!requireUnique && !matches.isEmpty()) || (requireUnique && matches.size() == 1)) {
                    return new JSONObject().put("matched", true).put("count", matches.size());
                }
                if (requireUnique && matches.size() > 1) {
                    throw new ActionFailure("SELECTOR_AMBIGUOUS",
                            "selector matched " + matches.size() + " elements while waiting", false);
                }
            } else if (!pkg.isEmpty()) {
                if (pkg.equals(device.getCurrentPackageName())) {
                    return new JSONObject().put("matched", true).put("package", pkg);
                }
            } else if (expect != null && expectationSatisfied(expect)) {
                return new JSONObject().put("matched", true);
            } else if (selector == null && pkg.isEmpty() && expect == null) {
                throw new ActionFailure("JOB_PAYLOAD_INVALID",
                        "waitFor requires selector, package, or expect", false);
            }
            if (SystemClock.elapsedRealtime() >= deadline) break;
            SystemClock.sleep(100L);
        } while (true);

        throw new ActionFailure("ACTION_TIMEOUT",
                "waitFor timed out" + (lastCount >= 0 ? " last_count=" + lastCount : ""), true);
    }

    private JSONObject assertState(JSONObject action) throws Exception {
        JSONObject expect = action.optJSONObject("expect");
        JSONObject selector = action.optJSONObject("selector");
        if (selector != null) {
            List<UiObject2> matches = findObjects(selector);
            boolean unique = action.optBoolean("unique", true);
            if (matches.isEmpty()) {
                throw new ActionFailure("ELEMENT_NOT_FOUND", "assert selector matched 0 elements", false);
            }
            if (unique && matches.size() > 1) {
                throw new ActionFailure("SELECTOR_AMBIGUOUS",
                        "assert selector matched " + matches.size() + " elements", false);
            }
            return new JSONObject().put("asserted", true).put("count", matches.size());
        }
        if (expect == null) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "assert requires selector or expect", false);
        }
        if (!expectationSatisfied(expect)) {
            throw new ActionFailure("POSTCONDITION_FAILED", "assertion did not match current UI state", false);
        }
        return new JSONObject().put("asserted", true);
    }

    private void verifyExpectation(JSONObject expect, long timeoutMs) throws Exception {
        if (expect == null || expect.length() == 0) return;
        long timeout = Math.max(0L, Math.min(60000L, timeoutMs));
        long deadline = SystemClock.elapsedRealtime() + timeout;
        do {
            if (expectationSatisfied(expect)) return;
            if (SystemClock.elapsedRealtime() >= deadline) break;
            SystemClock.sleep(100L);
        } while (true);
        throw new ActionFailure("POSTCONDITION_FAILED", "postcondition timed out", true);
    }

    private boolean expectationSatisfied(JSONObject expect) throws Exception {
        if (expect.has("package") &&
                !expect.getString("package").equals(device.getCurrentPackageName())) {
            return false;
        }
        if (expect.has("screen_on")) {
            PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
            boolean on = pm != null && pm.isInteractive();
            if (on != expect.getBoolean("screen_on")) return false;
        }
        if (expect.has("keyguard_blocking")) {
            KeyguardManager km = (KeyguardManager) context.getSystemService(Context.KEYGUARD_SERVICE);
            boolean blocked = km != null && km.isKeyguardLocked();
            if (blocked != expect.getBoolean("keyguard_blocking")) return false;
        }
        JSONObject selector = expect.optJSONObject("selector");
        if (selector != null) {
            int count = findObjects(selector).size();
            if (expect.optBoolean("unique", false)) {
                if (count != 1) return false;
            } else if (count < 1) {
                return false;
            }
        }
        JSONObject absent = expect.optJSONObject("absent_selector");
        if (absent != null && !findObjects(absent).isEmpty()) return false;
        return true;
    }

    private JSONObject elementJson(UiObject2 obj) throws Exception {
        JSONObject out = new JSONObject();
        out.put("resource_id", nullableString(obj.getResourceName()));
        out.put("text", nullableString(obj.getText()));
        out.put("content_desc", nullableString(obj.getContentDescription()));
        out.put("class", nullableString(obj.getClassName()));
        out.put("package", nullableString(obj.getApplicationPackage()));
        out.put("clickable", obj.isClickable());
        out.put("enabled", obj.isEnabled());
        out.put("selected", obj.isSelected());
        out.put("checkable", obj.isCheckable());
        out.put("checked", obj.isChecked());
        out.put("scrollable", obj.isScrollable());
        Rect bounds = obj.getVisibleBounds();
        JSONArray b = new JSONArray();
        b.put(bounds.left).put(bounds.top).put(bounds.right).put(bounds.bottom);
        out.put("bounds", b);
        return out;
    }

    private Object nullableString(String value) {
        return value == null || value.isEmpty() ? JSONObject.NULL : value;
    }

    private JSONObject screenshot(String filename) throws Exception {
        if (!filename.matches("[A-Za-z0-9._-]+")) {
            throw new IllegalArgumentException("invalid screenshot filename");
        }
        File base = new File(context.getFilesDir(), "y700-automation/" + sessionId);
        if (!base.exists() && !base.mkdirs()) {
            throw new IllegalStateException("cannot create screenshot directory");
        }
        File out = new File(base, filename);
        if (!device.takeScreenshot(out)) {
            throw new IllegalStateException("UiDevice.takeScreenshot returned false");
        }
        JSONObject data = new JSONObject();
        data.put("path", out.getAbsolutePath());
        data.put("size", out.length());
        return data;
    }

    private boolean isCancellationRequested() throws Exception {
        if (jobId == null || !jobId.matches("[A-Za-z0-9._-]{1,128}")) return false;
        String cancelPath = "/data/local/y700-agent/ui-cancel-signals/" + jobId;
        // UiAutomation.executeShellCommand() is not guaranteed to interpret
        // compound shell grammar consistently. Use one direct command against
        // a validated path and treat its stdout as the existence proof.
        String out = shell("ls " + cancelPath).trim();
        return cancelPath.equals(out);
    }

    private String shell(String command) throws Exception {
        ParcelFileDescriptor pfd = instrumentation.getUiAutomation().executeShellCommand(command);
        try (FileInputStream in = new FileInputStream(pfd.getFileDescriptor());
             ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] buf = new byte[4096];
            int n;
            while ((n = in.read(buf)) >= 0) {
                out.write(buf, 0, n);
            }
            return out.toString(StandardCharsets.UTF_8.name());
        } finally {
            pfd.close();
        }
    }

    private static class ActionFailure extends Exception {
        final String code;
        final boolean retryable;
        final String status;

        ActionFailure(String code, String message, boolean retryable) {
            this(code, message, retryable, "FAILED");
        }

        ActionFailure(String code, String message, boolean retryable, String status) {
            super(message);
            this.code = code;
            this.retryable = retryable;
            this.status = status;
        }
    }

    private JSONObject error(String code, String message, boolean retryable) throws JSONException {
        JSONObject e = new JSONObject();
        e.put("code", code);
        e.put("message", message == null ? "" : message);
        e.put("retryable", retryable);
        return e;
    }

    private String classify(Throwable t) {
        String name = t.getClass().getSimpleName().toLowerCase(Locale.ROOT);
        if (name.contains("security")) return "JOB_PERMISSION_DENIED";
        if (name.contains("timeout")) return "ACTION_TIMEOUT";
        return "UI_AUTOMATOR_DISCONNECTED";
    }

    private Object stringOrNull(CharSequence value) {
        if (value == null) return JSONObject.NULL;
        String s = value.toString();
        return s.isEmpty() ? JSONObject.NULL : s;
    }

    private String sha256(String value) throws Exception {
        byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder sb = new StringBuilder();
        for (byte b : digest) sb.append(String.format(Locale.US, "%02x", b));
        return sb.toString();
    }

    private void emitHeartbeat(int index, String action, String status) {
        try {
            JSONObject heartbeat = new JSONObject();
            heartbeat.put("job_id", jobId);
            heartbeat.put("session_id", sessionId);
            heartbeat.put("action_index", index);
            heartbeat.put("last_action", action);
            heartbeat.put("state", status);
            heartbeat.put("elapsed_ms",
                    Math.max(0L, SystemClock.elapsedRealtime() - workflowStartedElapsedMs));
            Bundle bundle = new Bundle();
            bundle.putString("y700_heartbeat_b64", encode(heartbeat.toString()));
            instrumentation.sendStatus(1, bundle);
        } catch (Throwable ignored) {
        }
    }

    private void emitResult(JSONObject result) {
        Bundle bundle = new Bundle();
        bundle.putString("y700_result_b64", encode(result.toString()));
        instrumentation.sendStatus(0, bundle);
    }

    private String encode(String value) {
        return Base64.encodeToString(value.getBytes(StandardCharsets.UTF_8), Base64.NO_WRAP);
    }
}
