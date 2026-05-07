import Cocoa
import FlutterMacOS

class MainFlutterWindow: NSWindow {
  override func awakeFromNib() {
    let flutterViewController = FlutterViewController()
    let targetSize = NSSize(width: 820, height: 720)
    self.contentViewController = flutterViewController
    self.setContentSize(targetSize)
    self.minSize = NSSize(width: 820, height: 720)

    RegisterGeneratedPlugins(registry: flutterViewController)

    super.awakeFromNib()
  }
}
