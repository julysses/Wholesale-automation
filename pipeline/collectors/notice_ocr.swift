// Local OCR for saved public notice pages; text extraction never certifies eligibility.
// API reference: https://developer.apple.com/documentation/vision/recognizing-text-in-images
import Foundation
import Vision
import CryptoKit

let args = CommandLine.arguments
if args.count != 3 { fputs("Usage: notice-ocr image.jpg output.json\n", stderr); exit(2) }
do {
    let imageURL = URL(fileURLWithPath: args[1])
    let data = try Data(contentsOf: imageURL)
    let digest = SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.recognitionLanguages = ["en-US"]
    request.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(url: imageURL, options: [:])
    try handler.perform([request])
    let lines: [[String: Any]] = (request.results ?? []).compactMap { observation in
        guard let text = observation.topCandidates(1).first else { return nil }
        let rect = observation.boundingBox
        return ["text": text.string, "confidence": text.confidence,
                "bounds": ["x": rect.minX, "y": rect.minY, "width": rect.width, "height": rect.height]]
    }
    let result: [String: Any] = ["schema_version": "1.0", "engine": "apple-vision",
        "revision": request.revision, "image_sha256": digest,
        "extracted_at": ISO8601DateFormatter().string(from: Date()),
        "lines": lines, "trace_eligible": false, "verified": false]
    let output = URL(fileURLWithPath: args[2])
    try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]).write(to: output, options: .atomic)
    try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: output.path)
    print("Extracted \(lines.count) lines; verification required")
} catch { fputs("OCR failed: \(error.localizedDescription)\n", stderr); exit(1) }
