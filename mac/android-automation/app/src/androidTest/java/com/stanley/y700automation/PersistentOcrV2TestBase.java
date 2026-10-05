package com.stanley.y700automation;

import android.content.Context;
import android.util.Log;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONObject;
import org.junit.AssumptionViolatedException;
import org.junit.Rule;
import org.junit.rules.TestWatcher;
import org.junit.runner.Description;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Method-level persistent evidence for Sprint V2 instrumentation tests.
 *
 * Lenovo/ZUI's am wrapper does not propagate AndroidJUnitRunner result text in
 * this execution environment, so acceptance reads these artifacts directly
 * from the test package private files directory.
 */
public abstract class PersistentOcrV2TestBase {
    private long testStartedAtMs;

    @Rule
    public final TestWatcher persistentOcrV2Evidence = new TestWatcher() {
        @Override
        protected void starting(Description description) {
            testStartedAtMs = System.currentTimeMillis();
        }

        @Override
        protected void succeeded(Description description) {
            writeMethodEvidence(description, "PASS", null);
        }

        @Override
        protected void failed(Throwable error, Description description) {
            writeMethodEvidence(description, "FAIL", error);
        }

        @Override
        protected void skipped(AssumptionViolatedException error, Description description) {
            writeMethodEvidence(description, "SKIP", error);
        }
    };

    protected static void writePersistentArtifact(String fileName, JSONObject payload) {
        try {
            Context context = InstrumentationRegistry.getInstrumentation().getContext();
            File dir = new File(context.getFilesDir(), "ocr-v2-evidence");
            if (!dir.mkdirs() && !dir.isDirectory()) {
                throw new IllegalStateException("cannot create evidence dir: " + dir);
            }
            String safeName = sanitize(fileName);
            File target = new File(dir, safeName);
            File temp = new File(dir, safeName + ".tmp");
            byte[] data = (payload.toString(2) + "\n").getBytes(StandardCharsets.UTF_8);
            try (FileOutputStream out = new FileOutputStream(temp)) {
                out.write(data);
                out.getFD().sync();
            }
            if (!temp.renameTo(target)) {
                throw new IllegalStateException("cannot publish evidence: " + target);
            }
        } catch (Exception e) {
            throw new RuntimeException("persistent OCR V2 evidence failed", e);
        }
    }

    private void writeMethodEvidence(
            Description description,
            String status,
            Throwable error) {
        long finishedAtMs = System.currentTimeMillis();
        try {
            JSONObject payload = new JSONObject()
                    .put("schema_version", 1)
                    .put("class_name",
                            description == null ? JSONObject.NULL : description.getClassName())
                    .put("method_name",
                            description == null ? JSONObject.NULL : description.getMethodName())
                    .put("status", status)
                    .put("started_at_ms", testStartedAtMs)
                    .put("finished_at_ms", finishedAtMs)
                    .put("duration_ms", Math.max(0L, finishedAtMs - testStartedAtMs))
                    .put("error_class",
                            error == null ? JSONObject.NULL : error.getClass().getName())
                    .put("error_message",
                            error == null || error.getMessage() == null
                                    ? JSONObject.NULL
                                    : error.getMessage())
                    .put("error_trace",
                            error == null ? JSONObject.NULL : Log.getStackTraceString(error));
            String className = description == null ? "unknown" : description.getClassName();
            String methodName = description == null ? "unknown" : description.getMethodName();
            writePersistentArtifact(
                    "test-" + simpleName(className) + "-" + methodName + ".json",
                    payload);
        } catch (Exception e) {
            throw new RuntimeException("method evidence failed", e);
        }
    }

    private static String simpleName(String name) {
        if (name == null || name.isEmpty()) return "unknown";
        int index = name.lastIndexOf('.');
        return index < 0 ? name : name.substring(index + 1);
    }

    private static String sanitize(String raw) {
        String name = raw == null ? "" : raw.trim();
        if (name.isEmpty()) name = "artifact.json";
        name = name.replaceAll("[^A-Za-z0-9._-]", "_");
        if (!name.endsWith(".json")) name += ".json";
        if (name.length() > 120) name = name.substring(0, 115) + ".json";
        return name;
    }
}
