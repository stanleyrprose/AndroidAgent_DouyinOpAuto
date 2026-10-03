# Sprint 0 Baseline

Date: 2026-10-03
Device: Lenovo TB323FU
Android: 16 / API 36
Root: KernelSU, SELinux Enforcing

## Legacy UI observation

Current path:

Debian -> root-exec filesystem job -> /system/bin/uiautomator dump -> XML

10 consecutive observations:

- PASS: 10/10
- P50: 2429.1 ms
- P95: 2556.2 ms
- min: 2301.0 ms
- max: 2556.2 ms

This establishes the latency baseline AndroidX UI Automator must beat.

## Existing filesystem job permissions

Observed legacy jobs currently inherit modes including:

- job directory: 0777
- request/result/state: 0666

Rev2 explicitly forbids carrying this pattern into the new UI automation job plane.

The new UI driver will not require direct access to the root-owned durable job
directory. The host executor owns the durable job and passes workflow payloads
to instrumentation through am instrument -e. Instrumentation returns
structured output to the host, which performs atomic durable writes.

## Build plane

Mac:
- JDK 17 available at Homebrew prefix
- Android SDK Platform 36 installed
- Android Build Tools 36.0.0 installed
- ADB available

Y700:
- no Android build toolchain required
- /system/bin/uiautomator, /system/bin/app_process, /system/bin/am exist

