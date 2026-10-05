# PaddleOCR Android SDK source provenance

Vendored for Sprint V2 OCR benchmarking/integration from:

- project: PaddlePaddle/PaddleOCR
- upstream commit: `dab3fe35379033fdcb2d0e9572fac0b36c9a9ebf`
- source subtree: `deploy/ppocr-android/ppocr-sdk/src/main/java/com/paddle/ocr`
- upstream license: Apache License 2.0

The original per-file Apache-2.0 copyright/license headers are preserved.

Y700 integration patches are intentionally outside the vendored algorithm core:

- OpenCV dependency is supplied by this app as official `org.opencv:opencv:4.12.0`
  because the upstream demo's QuickBird OpenCV 4.5.3 native package fails on the
  Y700 Android 16 linker.
- ONNX Runtime is `com.microsoft.onnxruntime:onnxruntime-android:1.21.1`.
- PP-OCRv6 tiny model binaries are downloaded on the Mac build plane from the
  upstream-documented Paddle model URLs and accepted only when pinned SHA-256
  values match. Model binaries are not committed to Git.
