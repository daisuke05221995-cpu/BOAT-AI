package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class PurchaseAssistCoordinatorTest {
    private fun race(id: String, raceNumber: Int) = PendingPurchaseRace(
        raceId = id,
        date = "2026-10-10",
        stadiumNumber = 1,
        raceNumber = raceNumber,
        venueName = "桐生",
        recommended = true,
        tickets = listOf(PendingPurchaseTicket("1-2-3", 500)),
        strategyId = "value-v1"
    )

    private fun session(id: String, vararg races: PendingPurchaseRace) = PendingPurchaseSession(
        id = id,
        createdAt = 1L,
        races = races.toList(),
        selectedRaceIds = races.mapTo(linkedSetOf()) { it.raceId }
    )

    @Test
    fun missingExistingUsesIncomingSession() {
        val incoming = session("incoming", race("r1", 1))
        assertSame(incoming, mergePendingSessions(null, incoming))
    }

    @Test
    fun duplicateRaceDoesNotOverwriteUnresolvedSession() {
        val existing = session("existing", race("r1", 1))
        val incoming = session("incoming", race("r1", 1))

        val merged = mergePendingSessions(existing, incoming)

        assertSame(existing, merged)
        assertEquals(listOf("r1"), merged.races.map { it.raceId })
    }

    @Test
    fun newRaceIsAppendedAndSelected() {
        val existing = session("existing", race("r1", 1))
        val incoming = session("incoming", race("r2", 2))

        val merged = mergePendingSessions(existing, incoming)

        assertEquals("existing", merged.id)
        assertEquals(listOf("r1", "r2"), merged.races.map { it.raceId })
        assertEquals(setOf("r1", "r2"), merged.selectedRaceIds)
    }
}
