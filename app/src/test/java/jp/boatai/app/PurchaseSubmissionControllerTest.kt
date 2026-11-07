package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PurchaseSubmissionControllerTest {
    private val now = 1_800_000_000_000L
    private fun session(id: String = "one") = PendingPurchaseSession(
        id, now - 25_000, listOf(PendingPurchaseRace(
            "race1", "2026-11-08", 1, 1, "桐生", true,
            listOf(PendingPurchaseTicket("1-3-5", 500), PendingPurchaseTicket("2-1-4", 300))
        )), setOf("race1")
    )
    private val review = OfficialPurchaseReview(
        BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE, now - 2_000,
        listOf(OfficialPurchaseLine(1, 1, "1-3-5", 500), OfficialPurchaseLine(1, 1, "2-1-4", 300)), 800
    )
    private val allowed = PurchaseAutomationCheck(true, "OK", 800, 2)

    @Test fun persistsReservationBeforeOneTapAndRejectsDuplicateHandoff() {
        val store = object : PurchaseAttemptReservation {
            private val keys = mutableSetOf<String>()
            override fun reserve(deduplicationKey: String, attemptedAtMs: Long) = keys.add(deduplicationKey)
        }
        val controller = PurchaseSubmissionController(store)
        var taps = 0
        assertEquals(PurchaseSubmissionResult.TapAttemptedReceiptPending,
            controller.submitOnce(session(), review, allowed, now, now - 5_000) { taps++; true })
        assertTrue(controller.submitOnce(session("second-handoff"), review, allowed, now, now - 5_000) is
            PurchaseSubmissionResult.Rejected)
        assertEquals(1, taps)
    }

    @Test fun refusesStaleDataMismatchedOfficialScreenAndFailedPersistence() {
        val store = object : PurchaseAttemptReservation {
            override fun reserve(deduplicationKey: String, attemptedAtMs: Long) = false
        }
        val controller = PurchaseSubmissionController(store)
        var clicked = false
        assertTrue(controller.submitOnce(session(), review, allowed, now, now - 100_000) { clicked = true; true } is
            PurchaseSubmissionResult.Rejected)
        assertTrue(controller.submitOnce(session(), review.copy(displayedTotal = 900), allowed, now, now - 5_000) {
            clicked = true; true
        } is PurchaseSubmissionResult.Rejected)
        assertTrue(controller.submitOnce(session(), review, allowed, now, now - 5_000) { clicked = true; true } is
            PurchaseSubmissionResult.Rejected)
        assertFalse(clicked)
    }

    @Test fun failedTapDoesNotGrantAnAutomaticRetry() {
        val store = object : PurchaseAttemptReservation {
            val keys = mutableSetOf<String>()
            override fun reserve(deduplicationKey: String, attemptedAtMs: Long) = keys.add(deduplicationKey)
        }
        val controller = PurchaseSubmissionController(store)
        assertEquals(PurchaseSubmissionResult.TapFailedDoNotRetry,
            controller.submitOnce(session(), review, allowed, now, now - 5_000) { false })
        assertTrue(controller.submitOnce(session(), review, allowed, now, now - 5_000) { true } is
            PurchaseSubmissionResult.Rejected)
    }
}
