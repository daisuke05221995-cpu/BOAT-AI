package jp.boatai.app

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Rule
import org.junit.Test

class MainActivitySmokeTest {
    @get:Rule
    val composeRule = createAndroidComposeRule<MainActivity>()

    @Test fun appLaunchesAndShowsMainNavigation() {
        composeRule.onNodeWithText("レース").assertIsDisplayed()
        composeRule.onNodeWithText("収支").assertIsDisplayed()
    }
}
