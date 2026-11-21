// GOOD MIXX - the Mac app window.
// Starts the GOOD MIXX helper (Resources/start-server.sh) and shows its screen in GOOD MIXX's own window,
// with normal Mac menus, copy/paste, file pickers and pop-up questions. Quitting the app stops the helper.
// Built by GitHub (macOS runner) with: swiftc -parse-as-library -O GoodMixxApp.swift
import AppKit
import WebKit

let port = ProcessInfo.processInfo.environment["GOODMIXX_PORT"] ?? "8770"
let home = URL(string: "http://localhost:\(port)/mixes")!

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, WKUIDelegate, WKNavigationDelegate, WKScriptMessageHandler {
    var window: NSWindow!
    var web: WKWebView!
    var retries = 0
    var quitting = false

    func applicationDidFinishLaunching(_ note: Notification) {
        buildMenu()
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        config.userContentController.add(self, name: "gm")
        config.preferences.setValue(true, forKey: "developerExtrasEnabled")
        web = WKWebView(frame: NSRect(x: 0, y: 0, width: 1366, height: 880), configuration: config)
        web.uiDelegate = self
        web.navigationDelegate = self
        web.setValue(false, forKey: "drawsBackground")
        if #available(macOS 12.0, *) { web.underPageBackgroundColor = NSColor(red: 0.063, green: 0.071, blue: 0.09, alpha: 1) }

        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1366, height: 880),
                          styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.title = "GOOD MIXX"
        window.minSize = NSSize(width: 900, height: 600)
        window.backgroundColor = NSColor(red: 0.063, green: 0.071, blue: 0.09, alpha: 1)
        window.contentView = web
        window.isReleasedWhenClosed = false
        if !window.setFrameUsingName("GOODMIXXMain") { window.center() }
        window.setFrameAutosaveName("GOODMIXXMain")
        web.loadHTMLString(Self.starting, baseURL: nil)
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        startHelper()
    }

    // Runs the same start-up script the app always used, minus opening a browser.
    func startHelper() {
        guard let script = Bundle.main.path(forResource: "start-server", ofType: "sh") else {
            fail("GOOD MIXX is missing a file (start-server.sh). Download it again.")
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/bash")
        p.arguments = [script]
        var env = ProcessInfo.processInfo.environment
        env["GM_NO_WINDOW"] = "1"
        p.environment = env
        p.terminationHandler = { proc in
            let ok = proc.terminationStatus == 0
            DispatchQueue.main.async {
                if ok { self.web.load(URLRequest(url: home)) } else { NSApp.terminate(nil) }  // the script already said why
            }
        }
        do { try p.run() } catch { fail("GOOD MIXX couldn't start its helper: \(error.localizedDescription)") }
    }

    func fail(_ msg: String) {
        let a = NSAlert()
        a.messageText = "GOOD MIXX"
        a.informativeText = msg
        a.runModal()
        NSApp.terminate(nil)
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ app: NSApplication) -> Bool { true }

    func applicationWillTerminate(_ note: Notification) { stopHelper() }

    // Stops the helper (the iPad screen stops too) - same as the QUIT button.
    func stopHelper() {
        guard !quitting, let url = URL(string: "http://localhost:\(port)/api/quit") else { return }
        quitting = true
        var req = URLRequest(url: url, timeoutInterval: 1.5)
        req.httpMethod = "POST"
        let done = DispatchSemaphore(value: 0)
        URLSession.shared.dataTask(with: req) { _, _, _ in done.signal() }.resume()
        _ = done.wait(timeout: .now() + 1.6)
    }

    // The page's QUIT button
    func userContentController(_ c: WKUserContentController, didReceive message: WKScriptMessage) {
        if (message.body as? String) == "quit" { quitting = true; NSApp.terminate(nil) }
    }

    // Links to other websites open in your browser; GOOD MIXX's own pages stay here.
    func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let url = action.request.url, let host = url.host, !["localhost", "127.0.0.1"].contains(host) {
            NSWorkspace.shared.open(url)
            decisionHandler(.cancel)
            return
        }
        decisionHandler(.allow)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation nav: WKNavigation!, withError error: Error) {
        guard retries < 20 else { return }
        retries += 1
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.web.load(URLRequest(url: home)) }
    }

    func webView(_ webView: WKWebView, didFinish nav: WKNavigation!) { retries = 0 }

    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for action: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = action.request.url { NSWorkspace.shared.open(url) }
        return nil
    }

    // alert() / confirm() / prompt() from the page
    func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.beginSheetModal(for: window) { _ in completionHandler() }
    }

    func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let a = NSAlert()
        a.messageText = message
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn) }
    }

    func webView(_ webView: WKWebView, runJavaScriptTextInputPanelWithPrompt prompt: String, defaultText: String?,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (String?) -> Void) {
        let a = NSAlert()
        a.messageText = prompt
        let field = NSTextField(frame: NSRect(x: 0, y: 0, width: 300, height: 24))
        field.stringValue = defaultText ?? ""
        a.accessoryView = field
        a.addButton(withTitle: "OK")
        a.addButton(withTitle: "Cancel")
        a.beginSheetModal(for: window) { r in completionHandler(r == .alertFirstButtonReturn ? field.stringValue : nil) }
    }

    // <input type=file> (REVIEW A SET > OPEN FILE)
    func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                 initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
        let panel = NSOpenPanel()
        panel.allowsMultipleSelection = parameters.allowsMultipleSelection
        panel.canChooseDirectories = false
        panel.beginSheetModal(for: window) { r in completionHandler(r == .OK ? panel.urls : nil) }
    }

    @objc func reload(_ sender: Any?) { web.load(URLRequest(url: home)) }
    @objc func zoomIn(_ sender: Any?) { web.pageZoom = min(2.0, web.pageZoom + 0.1) }
    @objc func zoomOut(_ sender: Any?) { web.pageZoom = max(0.5, web.pageZoom - 0.1) }
    @objc func zoomReset(_ sender: Any?) { web.pageZoom = 1.0 }

    // Help menu: opens the GitHub forms in your browser, filled in by the helper. Nothing is sent until you submit.
    @objc func reportProblem(_ sender: Any?) {
        NSWorkspace.shared.open(URL(string: "http://localhost:\(port)/api/report-problem")!)
    }
    @objc func suggestIdea(_ sender: Any?) {
        NSWorkspace.shared.open(URL(string: "https://github.com/XTRAGOODLABS/good-mixx/issues/new?template=idea.yml")!)
    }
    @objc func showErrorLog(_ sender: Any?) {
        let log = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/GOOD MIXX errors.log")
        if !FileManager.default.fileExists(atPath: log.path) {
            FileManager.default.createFile(atPath: log.path, contents: nil)
        }
        NSWorkspace.shared.activateFileViewerSelecting([log])
    }

    func buildMenu() {
        let main = NSMenu()
        func item(_ title: String, _ action: Selector?, _ key: String, _ mods: NSEvent.ModifierFlags = .command,
                  target: AnyObject? = nil) -> NSMenuItem {
            let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
            i.keyEquivalentModifierMask = mods
            if let t = target { i.target = t }
            return i
        }
        func top(_ title: String, _ items: [NSMenuItem]) -> NSMenu {
            let m = NSMenu(title: title)
            items.forEach { m.addItem($0) }
            let holder = NSMenuItem()
            holder.submenu = m
            main.addItem(holder)
            return m
        }
        _ = top("GOOD MIXX", [
            item("About GOOD MIXX", #selector(NSApplication.orderFrontStandardAboutPanel(_:)), ""),
            .separator(),
            item("Hide GOOD MIXX", #selector(NSApplication.hide(_:)), "h"),
            item("Hide Others", #selector(NSApplication.hideOtherApplications(_:)), "h", [.command, .option]),
            item("Show All", #selector(NSApplication.unhideAllApplications(_:)), ""),
            .separator(),
            item("Quit GOOD MIXX", #selector(NSApplication.terminate(_:)), "q"),
        ])
        _ = top("Edit", [
            item("Undo", Selector(("undo:")), "z"),
            item("Redo", Selector(("redo:")), "z", [.command, .shift]),
            .separator(),
            item("Cut", #selector(NSText.cut(_:)), "x"),
            item("Copy", #selector(NSText.copy(_:)), "c"),
            item("Paste", #selector(NSText.paste(_:)), "v"),
            item("Select All", #selector(NSText.selectAll(_:)), "a"),
        ])
        _ = top("View", [
            item("Reload", #selector(reload(_:)), "r", target: self),
            .separator(),
            item("Actual Size", #selector(zoomReset(_:)), "0", target: self),
            item("Zoom In", #selector(zoomIn(_:)), "+", target: self),
            item("Zoom Out", #selector(zoomOut(_:)), "-", target: self),
            .separator(),
            item("Enter Full Screen", #selector(NSWindow.toggleFullScreen(_:)), "f", [.command, .control]),
        ])
        let win = top("Window", [
            item("Minimize", #selector(NSWindow.performMiniaturize(_:)), "m"),
            item("Zoom", #selector(NSWindow.performZoom(_:)), ""),
        ])
        let help = top("Help", [
            item("Report a Problem…", #selector(reportProblem(_:)), "", target: self),
            item("Suggest an Idea…", #selector(suggestIdea(_:)), "", target: self),
            .separator(),
            item("Show Error Log", #selector(showErrorLog(_:)), "", target: self),
        ])
        NSApp.mainMenu = main
        NSApp.windowsMenu = win
        NSApp.helpMenu = help
    }

    static let starting = """
    <html><body style="margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#000;
    color:#8a8f9c;font:500 13px Menlo,monospace;letter-spacing:.12em">STARTING GOOD MIXX…</body></html>
    """
}

@main
struct GoodMixxMain {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()      // app.run() never returns, so this stays alive
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        app.run()
    }
}
