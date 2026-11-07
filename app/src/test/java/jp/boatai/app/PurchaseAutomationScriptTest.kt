package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PurchaseAutomationScriptTest {
    private fun profile() = OfficialPurchaseScreenProfile(
        venueSelectors = mapOf(1 to PurchaseUiSelector(resourceId = "venue-1")),
        raceSelectors = mapOf(1 to PurchaseUiSelector(resourceId = "race-1")),
        trifectaSelector = PurchaseUiSelector(resourceId = "trifecta"),
        laneSelectors = (1..3).associateWith { position ->
            (1..6).associateWith { boat -> PurchaseUiSelector(resourceId = "pos$position-boat$boat") }
        },
        amountInput = PurchaseUiSelector(resourceId = "amount"),
        addTicket = PurchaseUiSelector(resourceId = "add"),
        reviewList = PurchaseUiSelector(resourceId = "review")
    )

    private fun session() = PendingPurchaseSession(
        id = "test", createdAt = 0,
        races = listOf(PendingPurchaseRace(
            raceId = "2026-11-08-01-1", date = "2026-11-08", stadiumNumber = 1,
            raceNumber = 1, venueName = "桐生", recommended = true,
            tickets = listOf(PendingPurchaseTicket("1-3-5", 500), PendingPurchaseTicket("2-1-4", 300))
        )), selectedRaceIds = setOf("2026-11-08-01-1")
    )

    @Test fun compilesUniqueBoatSelectionsAndStakeInputWithoutSubmission() {
        val plan = PurchaseAutomationScriptCompiler.compile(
            session(), profile(), PurchaseAutomationCheck(true, "OK", 800, 2))!!
        assertEquals(14, plan.steps.size) // venue + race + 3連単 + (3 boats + amount + add)*2 + review
        assertEquals(800, plan.expectedTotal)
        assertEquals("1:1:1-3-5:500", plan.expectedTicketText.first())
        assertTrue(plan.steps.any { it is PurchaseUiStep.EnterText && it.value == "500" })
        assertFalse(plan.steps.any { it is PurchaseUiStep.Click && it.selector.label == "投票確定" })
    }

    @Test fun incompleteProfileOrFailedGuardCannotBeCompiled() {
        assertNull(PurchaseAutomationScriptCompiler.compile(
            session(), profile().copy(laneSelectors = emptyMap()),
            PurchaseAutomationCheck(true, "OK", 800, 2)))
        assertNull(PurchaseAutomationScriptCompiler.compile(
            session(), profile(), PurchaseAutomationCheck(false, "締切間近")))
    }
}
