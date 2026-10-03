package com.stanley.y700automation;

import android.app.Instrumentation;
import android.app.KeyguardManager;
import android.content.Context;
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
import androidx.test.uiautomator.Direction;
import androidx.test.uiautomator.StableResult;
import androidx.test.uiautomator.UiDevice;
import androidx.test.uiautomator.UiDeviceExt;
import androidx.test.uiautomator.UiObject2;

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
    private static final int MAX_TREE_NODES = 5000;

    private Instrumentation instrumentation;
    private UiDevice device;
    private Context context;
    private String jobId;
    private String sessionId;

    @Test
    public void runWorkflow() throws Exception {
        instrumentation = InstrumentationRegistry.getInstrumentation();
        context = instrumentation.getTargetContext();
        device = UiDevice.getInstance(instrumentation);

        final long workflowStart = SystemClock.elapsedRealtime();
        JSONObject result = new JSONObject();
        JSONArray actionResults = new JSONArray();

        try {
            JSONObject request = loadRequest();
            jobId = request.optString("job_id", "anonymous");
            sessionId = request.optString("session_id", UUID.randomUUID().toString());
            int protocol = request.optInt("protocol_version", -1);

            result.put("job_id", jobId);
            result.put("session_id", sessionId);
            result.put("driver_version", DRIVER_VERSION);
            result.put("protocol_version", PROTOCOL_VERSION);

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
            result.put("preflight", ensureUiPreflight(request));

            boolean failed = false;
            for (int i = 0; i < actions.length(); i++) {
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
        if (keyguardBlocking) {
            if (!request.optBoolean("dismiss_keyguard", true)) {
                throw new ActionFailure("KEYGUARD_BLOCKING",
                        "keyguard is blocking and dismiss_keyguard=false", false, "BLOCKED");
            }
            shell("wm dismiss-keyguard");
            dismissAttempted = true;
            SystemClock.sleep(350L);
            keyguardBlocking = km != null && km.isKeyguardLocked();
        }

        if (keyguardBlocking) {
            throw new ActionFailure("KEYGUARD_BLOCKING",
                    "keyguard remained blocking after dismiss attempt", false, "BLOCKED");
        }

        return new JSONObject()
                .put("screen_initially_on", screenInitiallyOn)
                .put("wake_attempted", wakeAttempted)
                .put("screen_on", true)
                .put("keyguard_initially_blocking", keyguardInitiallyBlocking)
                .put("dismiss_keyguard_attempted", dismissAttempted)
                .put("keyguard_blocking", false);
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
        JSONObject last = null;
        for (int attempt = 0; attempt <= maxRetry; attempt++) {
            last = executeAction(action, index);
            last.put("attempts", attempt + 1);
            if ("PASS".equals(last.optString("status"))) {
                last.put("retry_delays_ms", delays);
                return last;
            }

            JSONObject err = last.optJSONObject("error");
            boolean retryable = err != null && err.optBoolean("retryable", false);
            if (!retryable || attempt >= maxRetry) {
                last.put("retry_delays_ms", delays);
                return last;
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
            out.put("status", t.status);
            out.put("error", error(t.code, t.getMessage(), t.retryable));
        } catch (Throwable t) {
            out.put("status", "FAILED");
            out.put("error", error(classify(t), t.getClass().getSimpleName() + ": " +
                    String.valueOf(t.getMessage()), true));
        }
        out.put("latency_ms", SystemClock.elapsedRealtime() - started);
        return out;
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


    private BySelector buildSelector(JSONObject spec) throws Exception {
        if (spec == null || spec.length() == 0) {
            throw new ActionFailure("JOB_PAYLOAD_INVALID", "selector is required", false);
        }

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
        UiObject2 target = findUnique(action.optJSONObject("selector"));
        JSONObject resolved = elementJson(target);
        target.click();
        verifyExpectation(action.optJSONObject("expect"), action.optLong("timeout_ms", 10000L));
        JSONObject out = new JSONObject();
        out.put("resolved_element", resolved);
        return out;
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
            heartbeat.put("elapsed_ms", SystemClock.elapsedRealtime());
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
