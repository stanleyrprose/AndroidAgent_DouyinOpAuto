#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "$ROOT/scripts/env.sh"
"$ROOT/scripts/fetch-ocr-models.sh"
cd "$ROOT"
./gradlew :app:assembleDebug :app:assembleDebugAndroidTest
printf 'APP=%s\n' "$ROOT/app/build/outputs/apk/debug/app-debug.apk"
printf 'TEST=%s\n' "$ROOT/app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk"
