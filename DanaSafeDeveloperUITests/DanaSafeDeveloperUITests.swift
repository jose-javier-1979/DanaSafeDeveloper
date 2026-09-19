import XCTest

final class DanaSafeDeveloperUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    @MainActor
    func testPrimaryNavigationAndNowcastHelp() throws {
        let app = XCUIApplication()
        app.launchArguments.append("--ui-testing")
        app.launch()

        let tabBar = app.tabBars.firstMatch
        for tab in ["Radar", "Ahora", "Systems", "Hydrology", "Tools"] {
            XCTAssertTrue(tabBar.buttons[tab].waitForExistence(timeout: 15), "Missing tab: \(tab)")
        }

        tabBar.buttons["Ahora"].tap()
        for identifier in [
            "nowcast.evaluateLocation",
            "nowcast.refresh",
            "nowcast.notifications",
            "nowcast.help",
        ] {
            XCTAssertTrue(app.buttons[identifier].waitForExistence(timeout: 15), "Missing Nowcast control: \(identifier)")
        }

        app.buttons["nowcast.help"].tap()
        let dismiss = app.buttons["nowcast.help.dismiss"]
        XCTAssertTrue(dismiss.waitForExistence(timeout: 15), "Nowcast help sheet did not open")
        dismiss.tap()
        XCTAssertFalse(dismiss.waitForExistence(timeout: 5), "Nowcast help sheet did not dismiss")

        tabBar.buttons["Tools"].tap()
        XCTAssertTrue(app.buttons["tools.healthCheck"].waitForExistence(timeout: 15), "Tools health check is missing")
        XCTAssertTrue(app.buttons["tools.refresh"].waitForExistence(timeout: 15), "Tools refresh is missing")
    }

    @MainActor
    func testLaunchPerformance() throws {
        if ProcessInfo.processInfo.environment["CI"] == "true" {
            throw XCTSkip("Launch-performance sampling is intentionally manual; CI runs deterministic functional UI tests.")
        }
        measure(metrics: [XCTApplicationLaunchMetric()]) {
            let app = XCUIApplication()
            app.launchArguments.append("--ui-testing")
            app.launch()
        }
    }
}
