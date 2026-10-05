#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ASSETS="$ROOT/app/src/debug/assets/models"
DET="$ASSETS/det/inference.onnx"
REC="$ASSETS/rec/inference.onnx"
REC_YML="$ASSETS/rec/inference.yml"

DET_SHA="193bab7a04fca699a6c82e6abb5b81bdb28177f0abd4062552b04908dafb19f8"
REC_SHA="9ef676d6ed3c88256a2d92c640c44f25b0c40947e111b14b8be8f594091563e6"
REC_YML_SHA="66170210bad538e83fff3c4a3867e547d6bf20b50d64b20347c4b913f3034ea1"

DET_URL="https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_tiny_det_onnx_infer.tar"
REC_URL="https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/PP-OCRv6_tiny_rec_onnx_infer.tar"

sha() {
  shasum -a 256 "$1" | awk '{print $1}'
}

valid() {
  [ -f "$DET" ] && [ "$(sha "$DET")" = "$DET_SHA" ] &&
  [ -f "$REC" ] && [ "$(sha "$REC")" = "$REC_SHA" ] &&
  [ -f "$REC_YML" ] && [ "$(sha "$REC_YML")" = "$REC_YML_SHA" ]
}

if valid; then
  echo "OCR_MODELS_READY det_sha=$DET_SHA rec_sha=$REC_SHA"
  exit 0
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/y700-ocr-models.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$ASSETS/det" "$ASSETS/rec"

curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 -o "$TMP/det.tar" "$DET_URL"
curl -fL --retry 4 --retry-delay 2 --connect-timeout 15 -o "$TMP/rec.tar" "$REC_URL"
tar -xf "$TMP/det.tar" -C "$TMP"
tar -xf "$TMP/rec.tar" -C "$TMP"

DET_SRC="$(find "$TMP" -path '*PP-OCRv6_tiny_det_onnx_infer/inference.onnx' -type f | head -n 1)"
REC_SRC="$(find "$TMP" -path '*PP-OCRv6_tiny_rec_onnx_infer/inference.onnx' -type f | head -n 1)"
YML_SRC="$(find "$TMP" -path '*PP-OCRv6_tiny_rec_onnx_infer/inference.yml' -type f | head -n 1)"
[ -n "$DET_SRC" ] && [ -n "$REC_SRC" ] && [ -n "$YML_SRC" ]

[ "$(sha "$DET_SRC")" = "$DET_SHA" ] || { echo "OCR model SHA mismatch: det" >&2; exit 65; }
[ "$(sha "$REC_SRC")" = "$REC_SHA" ] || { echo "OCR model SHA mismatch: rec" >&2; exit 65; }
[ "$(sha "$YML_SRC")" = "$REC_YML_SHA" ] || { echo "OCR model SHA mismatch: rec config" >&2; exit 65; }

cp "$DET_SRC" "$DET.tmp"
cp "$REC_SRC" "$REC.tmp"
cp "$YML_SRC" "$REC_YML.tmp"
mv "$DET.tmp" "$DET"
mv "$REC.tmp" "$REC"
mv "$REC_YML.tmp" "$REC_YML"

valid || { echo "OCR model verification failed after install" >&2; exit 65; }
echo "OCR_MODELS_READY det_sha=$DET_SHA rec_sha=$REC_SHA"
