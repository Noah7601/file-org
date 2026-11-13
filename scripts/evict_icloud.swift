// Evict local copies of iCloud Drive files (cloud originals untouched). Usage: evict_icloud <path>...
import Foundation
let fm = FileManager.default
var ok = 0, fail = 0
for p in CommandLine.arguments.dropFirst() {
    do { try fm.evictUbiquitousItem(at: URL(fileURLWithPath: p)); ok += 1 }
    catch { fail += 1; FileHandle.standardError.write("FAIL \(p): \(error.localizedDescription)\n".data(using: .utf8)!) }
}
print("evicted \(ok) failed \(fail)")
