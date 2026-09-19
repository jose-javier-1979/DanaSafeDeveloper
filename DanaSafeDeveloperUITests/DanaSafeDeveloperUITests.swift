import XCTest

final class DanaSafeDeveloperUITests: XCTestCase {
    override func setUpWithError() throws { continueAfterFailure = false }

    @MainActor
    func testPrimaryNavigationAndNowcastHelp() throws {
        let app = XCUIApplication()
        app.launch()
        let tabBar = app.tabBars.firstMatch
        XCTAssertTrue(tabBar.buttons["Radar"].waitForExistence(timeout: 10))
        XCTAssertTrue(tabBar.buttons["Ahora"].exists)
        XCTAssertTrue(tabBar.buttons["Systems"].exists)
        XCTAssertTrue(tabBar.buttons["Hydrology"].exists)
        XCTAssertTrue(tabBar.buttons["Tools"].exists)
        tabBar.buttons["Ahora"].tap()
        XCTAssertTrue(app.buttons["nowcast.evaluateLocation"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["nowcast.refresh"].exists)
        XCTAssertTrue(app.buttons["nowcast.notifications"].exists)
        XCTAssertTrue(app.buttons["nowcast.help"].exists)
        app.buttons["nowcast.help"].tap()
        XCTAssertTrue(app.buttons["OK"].waitForExistence(timeout: 5))
        app.buttons["OK"].tap()
        tabBar.buttons["Tools"].tap()
        XCTAssertTrue(app.buttons["tools.healthCheck"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["tools.refresh"].exists)
    }

    @MainActor
    func testLaunchPerformance() throws {
        measure(metrics: [XCTApplicationLaunchMetric()]) { XCUIApplication().launch() }
    }
}
