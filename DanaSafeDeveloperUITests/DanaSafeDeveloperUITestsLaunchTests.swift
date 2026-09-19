import XCTest

final class DanaSafeDeveloperUITestsLaunchTests: XCTestCase {
    override class var runsForEachTargetApplicationUIConfiguration: Bool { false }

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    @MainActor
    func testLaunch() throws {
        let app = XCUIApplication()
        app.launchArguments.append("--ui-testing")
        app.launch()
        XCTAssertTrue(app.tabBars.buttons["Radar"].waitForExistence(timeout: 15))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "DanaSafe 8.2 Launch"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
