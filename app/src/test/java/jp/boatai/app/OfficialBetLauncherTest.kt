package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OfficialBetLauncherTest {
    @Test
    fun clipboardText_containsOnlySelectedRacesAndSelectedTotal() {
        val session = PendingPurchaseSession(
            id = "test-session",
            createdAt = 1L,
            races = listOf(
                PendingPurchaseRace(
                    raceId = "r1",
                    date = "2026-09-27",
                    stadiumNumber = 2,
                    raceNumber = 1,
                    venueName = "戸田",
                    recommended = true,
                    tickets = listOf(
                        PendingPurchaseTicket("1-2-3", 300),
                        PendingPurchaseTicket("1-3-2", 200)
                    )
                ),
                PendingPurchaseRace(
                    raceId = "r2",
                    date = "2026-09-27",
                    stadiumNumber = 4,
                    raceNumber = 2,
                    venueName = "平和島",
                    recommended = true,
                    tickets = listOf(PendingPurchaseTicket("2-1-3", 400))
                )
            ),
            selectedRaceIds = setOf("r1")
        )

        val text = OfficialBetLauncher.clipboardText(session)

        assertTrue(text.contains("戸田 1R"))
        assertTrue(text.contains("1-2-3 300円"))
        assertTrue(text.contains("1-3-2 200円"))
        assertTrue(text.contains("合計 500円"))
        assertFalse(text.contains("平和島 2R"))
        assertFalse(text.contains("2-1-3 400円"))
    }

    @Test
    fun clipboardText_emptySelectionDoesNotIncludeRaceTickets() {
        val session = PendingPurchaseSession(
            id = "empty-selection",
            createdAt = 1L,
            races = listOf(
                PendingPurchaseRace(
                    raceId = "r1",
                    date = "2026-09-27",
                    stadiumNumber = 2,
                    raceNumber = 1,
                    venueName = "戸田",
                    recommended = true,
                    tickets = listOf(PendingPurchaseTicket("1-2-3", 300))
                )
            ),
            selectedRaceIds = emptySet()
        )

        val text = OfficialBetLauncher.clipboardText(session)

        assertTrue(text.contains("合計 0円"))
        assertFalse(text.contains("戸田 1R"))
        assertFalse(text.contains("1-2-3 300円"))
    }
}
