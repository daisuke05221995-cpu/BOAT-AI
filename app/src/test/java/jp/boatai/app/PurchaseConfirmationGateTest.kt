package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PurchaseConfirmationGateTest {
    private val now = 1_790_000_000_000L
    private val session = PendingPurchaseSession(
        id = "test", createdAt = now,
        races = listOf(PendingPurchaseRace(
            raceId = "2026-11-08-01-1", date = "2026-11-08", stadiumNumber = 1,
            raceNumber = 1, venueName = "桐生", recommended = true,
            tickets = listOf(PendingPurchaseTicket("1-3-5", 500), PendingPurchaseTicket("2-1-4", 300))
        )), selectedRaceIds = setOf("2026-11-08-01-1")
    )
    private val correct = OfficialPurchaseReview(
        sourcePackage = BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE,
        observedAtMs = now - 100,
        lines = listOf(OfficialPurchaseLine(1, 1, "1-3-5", 500), OfficialPurchaseLine(1, 1, "2-1-4", 300)),
        displayedTotal = 800
    )

    @Test fun permitsOnlyExactFreshReviewOfOfficialScreen() {
        assertTrue(PurchaseConfirmationGate.checkReview(session, correct, now).allowed)
    }

    @Test fun blocksExtraTicketAndWrongAmountEvenWhenTotalsMatch() {
        val wrongLines = correct.copy(lines = listOf(
            OfficialPurchaseLine(1, 1, "1-3-5", 600), OfficialPurchaseLine(1, 1, "2-1-4", 200)))
        assertFalse(PurchaseConfirmationGate.checkReview(session, wrongLines, now).allowed)
        assertFalse(PurchaseConfirmationGate.checkReview(session, correct.copy(displayedTotal = 900), now).allowed)
        assertFalse(PurchaseConfirmationGate.checkReview(session, correct.copy(lines = correct.lines + correct.lines.first()), now).allowed)
    }

    @Test fun blocksWrongAppAndStaleObservation() {
        assertFalse(PurchaseConfirmationGate.checkReview(session, correct.copy(sourcePackage = "com.fake"), now).allowed)
        assertFalse(PurchaseConfirmationGate.checkReview(session, correct.copy(observedAtMs = now - 40_000), now).allowed)
    }
}
