package com.stanley.y700automation;

import android.content.Context;
import android.os.Bundle;

import androidx.test.platform.app.InstrumentationRegistry;

import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.runner.Description;
import org.junit.runner.Result;
import org.junit.runner.notification.Failure;
import org.junit.runner.notification.RunListener;

import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;

/**
 * Persistent JUnit evidence for Y700 where the vendor am wrapper does not
 * propagate AndroidJUnitRunner stdout or JUnit status codes.
 *
 * Invocation:
 *   -e listener com.stanley.y700automation.PersistentResultRunListener
 *   -e result_file <safe-name>.json
 */
public final class PersistentResultRunListener extends RunListener {
    private long startedAtMs;
    private int testsStarted;
    private int testsFinished;
    private int testsIgnored;
    private final JSONArray failures = new JSONArray();

    @Override
    public void testRunStarted(Description description) {
        startedAtMs = System.currentTimeMillis();
    }

    @Override
    public void testStarted(Description description) {
        testsStarted++;
    }

    @Override
    public void testFinished(Description description) {
        testsFinished++;
    }

    @Override
    public void testIgnored(Description description) {
        testsIgnored++;
    }

    @Override
    public void testFailure(Failure failure) {
        try {
            failures.put(new JSONObject()
                    .put("description",
                            failure.getDescription() == null
                                    ? JSONObject.NULL
                                    : failure.getDescription().toString())
                    .put("message",
                            failure.getMessage() == null
                                    ? JSONObject.NULL
                                    : failure.getMessage())
                    .put("trace",
                            failure.getTrace() == null
                                    ? JSONObject.NULL
                                    : failure.getTrace()));
        } catch (Exception ignored) {
            // Evidence writing at run end still records failure_count from Result.
        }
    }

    @Override
    public void testRunFinished(Result result) throws Exception {
        long finishedAtMs = System.currentTimeMillis();
        Bundle args = InstrumentationRegistry.getArguments();
        String requested = args == null ? "" : args.getString("class", "");
        String rawName = args == null ? "" : args.getString("result_file", "");
        String fileName = sanitizeFileName(rawName);

        JSONObject payload = new JSONObject()
                .put("schema_version", 1)
                .put("requested_class", requested)
                .put("started_at_ms", startedAtMs)
                .put("finished_at_ms", finishedAtMs)
                .put("duration_ms", Math.max(0L, finishedAtMs - startedAtMs))
                .put("tests_started", testsStarted)
                .put("tests_finished", testsFinished)
                .put("tests_ignored", testsIgnored)
                .put("run_count", result == null ? 0 : result.getRunCount())
                .put("failure_count", result == null ? failures.length() : result.getFailureCount())
                .put("ignore_count", result == null ? testsIgnored : result.getIgnoreCount())
                .put("successful", result != null && result.wasSuccessful())
                .put("failures", failures);

        Context context = InstrumentationRegistry.getInstrumentation().getContext();
        File dir = new File(context.getFilesDir(), "ocr-v2-instrument");
        if (!dir.mkdirs() && !dir.isDirectory()) {
            throw new IllegalStateException("cannot create result dir: " + dir);
        }
        File target = new File(dir, fileName);
        File temp = new File(dir, fileName + ".tmp");
        byte[] bytes = (payload.toString(2) + "\n").getBytes(StandardCharsets.UTF_8);
        try (FileOutputStream out = new FileOutputStream(temp)) {
            out.write(bytes);
            out.getFD().sync();
        }
        if (!temp.renameTo(target)) {
            throw new IllegalStateException("cannot publish result: " + target);
        }
    }

    private static String sanitizeFileName(String raw) {
        String name = raw == null ? "" : raw.trim();
        if (name.isEmpty()) {
            name = "result.json";
        }
        name = name.replaceAll("[^A-Za-z0-9._-]", "_");
        if (!name.endsWith(".json")) {
            name += ".json";
        }
        if (name.length() > 96) {
            name = name.substring(0, 91) + ".json";
        }
        return name;
    }
}
