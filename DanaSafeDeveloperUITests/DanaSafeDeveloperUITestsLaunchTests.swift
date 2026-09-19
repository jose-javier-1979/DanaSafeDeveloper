import XCTest

final class DanaSafeDeveloperUITestsLaunchTests: XCTestCase {
    override class var runsForEachTargetApplicationUIConfiguration: Bool { true }
    override func setUpWithError() throws { continueAfterFailure = false }

    @MainActor
    func testLaunch() throws {
        let app = XCUIApplication()
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Radar"].waitForExistence(timeout: 10))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "DanaSafe 8.1 Launch"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
