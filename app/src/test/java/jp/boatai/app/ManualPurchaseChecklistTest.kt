package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ManualPurchaseChecklistTest {
    private val now = 1_800_000_000_000L

    private fun race(
        id: String = "race-1",
        tickets: List<PendingPurchaseTicket> = listOf(
            PendingPurchaseTicket("1-2-3", 500),
            PendingPurchaseTicket("1-3-5", 300)
        )
    ) = PendingPurchaseRace(
        raceId = id,
        date = "2026-11-09",
        stadiumNumber = 2,
        raceNumber = 7,
        venueName = "戸田",
        recommended = true,
        tickets = tickets
    )

    private fun handoff(
        races: List<PendingPurchaseRace> = listOf(race()),
        selectedIds: Set<String> = races.mapTo(linkedSetOf()) { it.raceId },
        expiry: Long = now + 120_000L
    ) = CollectorPurchaseHandoff(
        handoffId = "f0000000-0000-4000-8000-000000000001",
        expiresAt = expiry,
        session = PendingPurchaseSession("test-session", now, races, selectedIds)
    )

    @Test fun validTicketsProduceLocalReadOnlyChecklist() {
        val result = ManualPurchaseChecklist.prepare(handoff(), now)
        assertTrue(result.valid)
        val text = result.clipboardText!!
        assertTrue(text.contains("受信済み／未購入"))
        assertTrue(text.contains("戸田 7R"))
        assertTrue(text.contains("1-2-3    500円"))
        assertTrue(text.contains("1-3-5    300円"))
        assertTrue(text.contains("合計 2点  800円"))
        assertFalse(text.contains("購入完了"))
        assertFalse(text.contains("投票成立"))
    }

    @Test fun unselectedRaceIsExcludedFromReviewAndTotal() {
        val selected = race()
        val excluded = race("race-2", listOf(PendingPurchaseTicket("2-1-3", 1000)))
        val result = ManualPurchaseChecklist.prepare(handoff(listOf(selected, excluded), setOf("race-1")), now)
        assertTrue(result.valid)
        assertFalse(result.clipboardText!!.contains("2-1-3"))
        assertTrue(result.clipboardText!!.contains("合計 2点  800円"))
    }

    @Test fun expiredTransferCannotBeCopiedAsCurrentPurchasePlan() {
        val result = ManualPurchaseChecklist.prepare(handoff(expiry = now), now)
        assertFalse(result.valid)
        assertEquals(null, result.clipboardText)
    }

    @Test fun repeatedCombinationFailsClosed() {
        val bad = race(tickets = listOf(
            PendingPurchaseTicket("1-2-3", 500),
            PendingPurchaseTicket("1-2-3", 500)
        ))
        assertFalse(ManualPurchaseChecklist.prepare(handoff(listOf(bad)), now).valid)
    }

    @Test fun sameLaneTwiceFailsClosed() {
        val bad = race(tickets = listOf(PendingPurchaseTicket("1-1-3", 500)))
        assertFalse(ManualPurchaseChecklist.prepare(handoff(listOf(bad)), now).valid)
    }

    @Test fun invalidStakeFailsClosed() {
        for (stake in listOf(0, 50, 125, -100)) {
            val bad = race(tickets = listOf(PendingPurchaseTicket("1-2-3", stake)))
            assertFalse(ManualPurchaseChecklist.prepare(handoff(listOf(bad)), now).valid)
        }
    }

    @Test fun emptySelectionDoesNotMakeChecklist() {
        val result = ManualPurchaseChecklist.prepare(handoff(selectedIds = emptySet()), now)
        assertFalse(result.valid)
        assertEquals(null, result.clipboardText)
    }

    @Test fun duplicateRaceIdsCannotBeReviewed() {
        val result = ManualPurchaseChecklist.prepare(handoff(races = listOf(race(), race())), now)
        assertFalse(result.valid)
    }

    @Test fun subtotalAndTotalAreFormattedInYen() {
        val result = ManualPurchaseChecklist.prepare(
            handoff(races = listOf(race(tickets = listOf(PendingPurchaseTicket("6-5-4", 2500)))), now
        )
        assertTrue(result.valid)
        assertTrue(result.clipboardText!!.contains("2,500円"))
        assertTrue(result.clipboardText!!.contains("このレースの小計"))
    }
}
