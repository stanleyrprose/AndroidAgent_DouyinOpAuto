package com.stanley.y700automation.vision;

import android.app.Instrumentation;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import android.content.pm.SigningInfo;
import android.os.Build;

import java.security.MessageDigest;
import java.util.Locale;

/**
 * Rev3.7 exact installed TikTok App UI Contract observer.
 *
 * The actual package signing certificate and longVersionCode are read from
 * Android PackageManager at native action-time; the request cannot supply
 * a matching certificate/version. Unknown/multiple signers, invisible app,
 * or version mismatch blocks all visual mutation. No bytes/keys are logged.
 *
 * A specific version/signature pair MUST be frozen from genuine Y700
 * evidence during final acceptance. Until then all paths fail closed.
 */
public final class Rev37NativeAppContract {
    private static final String PACKAGE = "com.zhiliaoapp.musically";
    private static final String CREATE_CONTRACT_ID = "tiktok.create.observe.v1";
    private static final String PUBLISH_CONTRACT_ID = "tiktok.publish-control.v1";
    private static final boolean CONTRACT_ACCEPTED = false;
    private static final long ACCEPTED_VERSION_CODE = -1L;
    private static final String ACCEPTED_CERT_SHA256 = "";

    private Rev37NativeAppContract() {}

    public static final class Result {
        public final String reason;
        private Result(String reason) { this.reason = reason; }
        public boolean matches() {
            return "NATIVE_APP_CONTRACT_MATCH_READ_ONLY".equals(reason);
        }
    }

    private static Result reject(String reason) {
        return new Result(reason);
    }

    private static String toHex(byte[] bytes) {
        StringBuilder chars = new StringBuilder();
        for (byte part : bytes) {
            chars.append(Character.forDigit((part >>> 4) & 0xF, 16));
            chars.append(Character.forDigit(part & 0xF, 16));
        }
        return chars.toString();
    }

    public static Result inspect(
            Instrumentation instrumentation, String requestedContract) {
        if (instrumentation == null
                || !(CREATE_CONTRACT_ID.equals(requestedContract)
                    || PUBLISH_CONTRACT_ID.equals(requestedContract)))
            return reject("APP_UI_CONTRACT_ID_MISMATCH");
        if (!CONTRACT_ACCEPTED
                || ACCEPTED_VERSION_CODE <= 0
                || !ACCEPTED_CERT_SHA256.matches("[0-9a-f]{64}"))
            return reject("APP_UI_CONTRACT_NOT_ACCEPTED");
        try {
            PackageManager pm = instrumentation.getTargetContext()
                    .getPackageManager();
            PackageInfo info;
            if (Build.VERSION.SDK_INT >= 33) {
                info = pm.getPackageInfo(PACKAGE,
                        PackageManager.PackageInfoFlags.of(
                                PackageManager.GET_SIGNING_CERTIFICATES));
            } else {
                info = pm.getPackageInfo(
                        PACKAGE, PackageManager.GET_SIGNING_CERTIFICATES);
            }
            if (info == null || info.signingInfo == null
                    || info.getLongVersionCode() != ACCEPTED_VERSION_CODE)
                return reject("APP_UI_VERSION_CHANGED");
            SigningInfo signing = info.signingInfo;
            if (signing.hasMultipleSigners())
                return reject("APP_UI_MULTIPLE_SIGNERS_NOT_ACCEPTED");
            Signature[] certificates = signing.getApkContentsSigners();
            if (certificates == null || certificates.length != 1)
                return reject("APP_UI_CERTIFICATE_UNAVAILABLE");
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            String observed = toHex(
                    digest.digest(certificates[0].toByteArray()));
            if (!ACCEPTED_CERT_SHA256.equals(observed))
                return reject("APP_UI_SIGNING_CERT_CHANGED");
            return new Result("NATIVE_APP_CONTRACT_MATCH_READ_ONLY");
        } catch (Exception ignored) {
            return reject("APP_UI_PACKAGE_OBSERVATION_UNAVAILABLE");
        }
    }

    /**
     * Independent device-fact capture for FUTURE signed-off app version
     * acceptance. No trusted version is inferred from the user payload.
     * Returning the installed cert HASH is diagnostic only; it does not
     * populate ACCEPTED_CERT_SHA256 or grant D-G3/Publish permission.
     */
    public static org.json.JSONObject observeInstalledReadOnly(
            Instrumentation instrumentation) throws Exception {
        org.json.JSONObject receipt = new org.json.JSONObject()
                .put("status", "BLOCKED")
                .put("source", "ANDROID_PACKAGE_MANAGER")
                .put("package", PACKAGE)
                .put("app_ui_contract_accepted", false)
                .put("production_dispatch_authorized", false)
                .put("ui_mutation_attempts", 0);
        if (instrumentation == null)
            return receipt.put("reason_code", "PACKAGE_MANAGER_UNAVAILABLE");
        try {
            PackageManager manager = instrumentation.getTargetContext()
                    .getPackageManager();
            PackageInfo info;
            if (Build.VERSION.SDK_INT >= 33) {
                info = manager.getPackageInfo(PACKAGE,
                        PackageManager.PackageInfoFlags.of(
                                PackageManager.GET_SIGNING_CERTIFICATES));
            } else {
                info = manager.getPackageInfo(
                        PACKAGE, PackageManager.GET_SIGNING_CERTIFICATES);
            }
            if (info == null || info.signingInfo == null
                    || info.signingInfo.hasMultipleSigners())
                return receipt.put("reason_code",
                        "APP_SIGNING_IDENTITY_UNAVAILABLE");
            Signature[] current =
                    info.signingInfo.getApkContentsSigners();
            if (current == null || current.length != 1)
                return receipt.put("reason_code",
                        "APP_SIGNER_AMBIGUOUS");
            String certHash = toHex(MessageDigest.getInstance("SHA-256")
                    .digest(current[0].toByteArray()));
            return receipt.put("status", "READ_ONLY_APP_IDENTITY_OBSERVED")
                    .put("reason_code", "NOT_YET_ACCEPTED")
                    .put("app_version_code", info.getLongVersionCode())
                    .put("app_signing_cert_sha256", certHash);
        } catch (Exception ignored) {
            return receipt.put("reason_code",
                    "APP_PACKAGE_OBSERVATION_UNAVAILABLE");
        }
    }

    public static boolean productionDispatchAuthorized() {
        return false;
    }
}
