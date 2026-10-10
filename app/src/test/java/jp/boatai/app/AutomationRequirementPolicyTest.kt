package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutomationRequirementPolicyTest {
    @Test
    fun healthyAutomationStaysHidden() {
        assertFalse(
            AutomationRequirementPolicy.shouldShowExactAlarmIssue(
                exactAlarmReady = true,
                hasPurchasableRace = true
            )
        )
    }

    @Test
    fun missingPermissionWithoutActiveRacesStaysHidden() {
        assertFalse(
            AutomationRequirementPolicy.shouldShowExactAlarmIssue(
                exactAlarmReady = false,
                hasPurchasableRace = false
            )
        )
    }

    @Test
    fun missingPermissionWithActiveRaceBecomesActionable() {
        assertTrue(
            AutomationRequirementPolicy.shouldShowExactAlarmIssue(
                exactAlarmReady = false,
                hasPurchasableRace = true
            )
        )
    }
}
