// One-shot batched AppKit/CoreText shaping, no resident daemon.
// Usage: render_text_batch <subtitle_timeline.json> <output-directory>
// Output JSON: {"assets":[{"event_id":...,"asset_path":...}]}.
import AppKit
import Foundation

guard CommandLine.arguments.count == 3 else {
    fputs("usage: render_text_batch <timeline.json> <output_dir>\n", stderr)
    exit(2)
}
let timelineURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
let size = NSSize(width: 900, height: 260)
do {
    try FileManager.default.createDirectory(at: outputURL, withIntermediateDirectories: true)
    let raw = try Data(contentsOf: timelineURL)
    guard let root = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
          let events = root["events"] as? [[String: Any]] else {
        throw NSError(domain: "BurmeseBatch", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "timeline events missing"])
    }
    guard NSFont(name: "Noto Sans Myanmar", size: 42) != nil else {
        throw NSError(domain: "BurmeseBatch", code: 3,
                      userInfo: [NSLocalizedDescriptionKey: "Noto Sans Myanmar font unavailable"])
    }
    var assets: [[String: String]] = []
    for event in events {
        guard let localization = event["localization"] as? [String: Any],
              let txt = localization["text_my"] as? String, !txt.isEmpty,
              let eventID = event["event_id"] as? String else { continue }
        guard eventID.range(of: #"^[a-zA-Z0-9_-]+$"#, options: .regularExpression) != nil else {
            throw NSError(domain: "BurmeseBatch", code: 4,
                          userInfo: [NSLocalizedDescriptionKey: "unsafe event ID"])
        }
        guard let bitmap = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(size.width), pixelsHigh: Int(size.height),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true,
            isPlanar: false, colorSpaceName: .deviceRGB,
            bytesPerRow: 0, bitsPerPixel: 0
        ) else { throw NSError(domain: "BurmeseBatch", code: 5) }
        NSGraphicsContext.saveGraphicsState()
        let context = NSGraphicsContext(bitmapImageRep: bitmap)
        NSGraphicsContext.current = context
        NSColor.clear.setFill()
        NSRect(origin: .zero, size: size).fill()
        let role = event["role"] as? String ?? "primary_subtitle"
        let fontSize: CGFloat = role == "callout" ? 38 : 42
        NSColor(calibratedWhite: 0.04, alpha: 0.76).setFill()
        NSBezierPath(roundedRect: NSRect(x: 8, y: 8, width: 884, height: 244),
                     xRadius: 20, yRadius: 20).fill()
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        paragraph.lineBreakMode = .byWordWrapping
        paragraph.lineSpacing = 6
        let font = NSFont(name: "Noto Sans Myanmar", size: fontSize)!
        let attributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white,
            .paragraphStyle: paragraph,
        ]
        let text = NSAttributedString(string: txt, attributes: attributes)
        let bounds = NSRect(x: 32, y: 36, width: 836, height: 192)
        let needed = text.boundingRect(with: bounds.size,
                                       options: [.usesLineFragmentOrigin, .usesFontLeading])
        if needed.height > bounds.height || needed.width > bounds.width {
            NSGraphicsContext.restoreGraphicsState()
            throw NSError(domain: "BurmeseBatch", code: 6,
                          userInfo: [NSLocalizedDescriptionKey: "Myanmar caption exceeds box: \(eventID)"])
        }
        text.draw(in: bounds)
        context?.flushGraphics()
        NSGraphicsContext.restoreGraphicsState()
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            throw NSError(domain: "BurmeseBatch", code: 7)
        }
        let output = outputURL.appendingPathComponent(eventID + ".png")
        try png.write(to: output, options: .atomic)
        assets.append(["event_id": eventID, "asset_path": output.path])
    }
    let response = try JSONSerialization.data(withJSONObject: ["assets": assets], options: [.sortedKeys])
    if let json = String(data: response, encoding: .utf8) {
        print(json)
    }
} catch {
    fputs("Burmese batch render failed: \(error.localizedDescription)\n", stderr)
    exit(1)
}
