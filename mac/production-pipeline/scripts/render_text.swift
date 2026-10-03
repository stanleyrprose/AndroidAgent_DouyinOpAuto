import AppKit
import Foundation

guard CommandLine.arguments.count == 6 else {
    fputs("usage: render_text <text-file> <output-png> <width> <height> <font-size>\n", stderr)
    exit(2)
}

let textPath = CommandLine.arguments[1]
let outputPath = CommandLine.arguments[2]
let width = CGFloat(Double(CommandLine.arguments[3]) ?? 900)
let height = CGFloat(Double(CommandLine.arguments[4]) ?? 260)
let fontSize = CGFloat(Double(CommandLine.arguments[5]) ?? 42)
let text = try String(contentsOfFile: textPath, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines)

let image = NSImage(size: NSSize(width: width, height: height))
image.lockFocus()
NSColor(calibratedWhite: 0.05, alpha: 0.74).setFill()
NSBezierPath(
    roundedRect: NSRect(x: 0, y: 0, width: width, height: height),
    xRadius: 24, yRadius: 24
).fill()

let style = NSMutableParagraphStyle()
style.alignment = .center
style.lineSpacing = 4
let font = NSFont(name: "Noto Sans Myanmar", size: fontSize) ?? NSFont.systemFont(ofSize: fontSize)
let attrs: [NSAttributedString.Key: Any] = [
    .font: font,
    .foregroundColor: NSColor.white,
    .paragraphStyle: style,
]
(text as NSString).draw(
    in: NSRect(x: 34, y: 36, width: width - 68, height: height - 64),
    withAttributes: attrs
)
image.unlockFocus()

guard let tiff = image.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else {
    fatalError("PNG encoding failed")
}
try png.write(to: URL(fileURLWithPath: outputPath))
