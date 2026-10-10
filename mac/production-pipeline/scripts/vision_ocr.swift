// Local Apple Vision batch OCR. Input: JSON manifest of {path, ts, width, height}.
// Output: {"frames":[{"ts":..., "observations":[...]}]}.
// Vision uses bottom-left normalized coordinates; convert to top-left here.
import AppKit
import Foundation
import ImageIO
import Vision

struct Frame: Decodable {
    let path: String
    let ts: Double
    let width: Int
    let height: Int
}

func recognize(_ frame: Frame) throws -> [String: Any] {
    guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: frame.path) as CFURL, nil),
          let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
        throw NSError(domain: "VisionOCR", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "cannot open frame"])
    }
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = false
    request.recognitionLanguages = ["zh-Hans", "zh-Hant", "en-US"]
    try VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
    var results = [[String: Any]]()
    for candidate in request.results ?? [] {
        guard let top = candidate.topCandidates(1).first else { continue }
        let box = candidate.boundingBox
        let x0 = max(0.0, min(1.0, Double(box.minX)))
        let x1 = max(0.0, min(1.0, Double(box.maxX)))
        let y0 = max(0.0, min(1.0, 1.0 - Double(box.maxY)))
        let y1 = max(0.0, min(1.0, 1.0 - Double(box.minY)))
        results.append([
            "text_zh_raw": top.string,
            "ocr_confidence": Double(top.confidence),
            "bbox_norm": [x0, y0, x1, y1],
        ])
    }
    return ["ts": frame.ts, "observations": results]
}

guard CommandLine.arguments.count == 2 else {
    fputs("usage: vision_ocr <frame-manifest.json>\n", stderr)
    exit(2)
}
do {
    let manifest = try Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1]))
    let frames = try JSONDecoder().decode([Frame].self, from: manifest)
    let output = try frames.map { try recognize($0) }
    let payload = try JSONSerialization.data(withJSONObject: ["frames": output], options: [.sortedKeys])
    guard let line = String(data: payload, encoding: .utf8) else {
        throw NSError(domain: "VisionOCR", code: 3)
    }
    print(line)
} catch {
    fputs("vision OCR failed: \(error.localizedDescription)\n", stderr)
    exit(1)
}
