package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.LocalDateTime

class PurchaseAutomationSafetyTest {
    private val now = LocalDateTime.of(2026, 11, 8, 12, 0)

    private fun race(close: String = "12:10") = RaceData(
        date = "2026-11-08", stadiumNumber = 1, raceNumber = 1, closedAt = close,
        gradeNumber = null, title = "", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane -> Racer(
            lane = lane, name = "R$lane", registrationNumber = null, rank = "B1",
            branch = null, age = null, weight = null, averageStart = null,
            nationalWinRate = null, nationalTop2 = null, nationalTop3 = null,
            localWinRate = null, localTop2 = null, localTop3 = null,
            motorNumber = null, motorTop2 = null, motorTop3 = null,
            boatNumber = null, boatTop2 = null, boatTop3 = null, preview = null
        ) }, preview = null, result = null
    )

    private fun session(vararg tickets: PendingPurchaseTicket): PendingPurchaseSession {
        val selected = race()
        return PendingPurchaseSession(
            id = "session-1", createdAt = 0L,
            races = listOf(PendingPurchaseRace(
                raceId = selected.id, date = selected.date, stadiumNumber = 1,
                raceNumber = 1, venueName = "桐生", recommended = true,
                tickets = tickets.toList()
            )), selectedRaceIds = setOf(selected.id)
        )
    }

    @Test fun acceptsFreshBoundedSixPickPlan() {
        val tickets = listOf("1-3-5", "1-2-4", "2-1-3", "3-1-2", "4-1-3", "5-1-3")
            .map { PendingPurchaseTicket(it, 500) }.toTypedArray()
        val result = PurchaseAutomationSafety.validate(session(*tickets), listOf(race()), now)
        assertTrue(result.reason, result.allowed)
        assertEquals(3000, result.sessionStake)
        assertEquals(6, result.selectedTickets)
    }

    @Test fun refusesClosingRaceAndOverBudget() {
        val selected = session(PendingPurchaseTicket("1-3-5", 500))
        assertFalse(PurchaseAutomationSafety.validate(selected, listOf(race("12:01")), now).allowed)
        assertFalse(PurchaseAutomationSafety.validate(
            session(PendingPurchaseTicket("1-3-5", 6000)), listOf(race()), now).allowed)
    }

    @Test fun refusesMalformedAndDuplicateCombinations() {
        val bad = session(PendingPurchaseTicket("1-1-3", 500))
        assertFalse(PurchaseAutomationSafety.validate(bad, listOf(race()), now).allowed)
        val duplicate = session(PendingPurchaseTicket("1-3-5", 500), PendingPurchaseTicket("1-3-5", 500))
        assertFalse(PurchaseAutomationSafety.validate(duplicate, listOf(race()), now).allowed)
    }

    @Test fun selectorRefusesAmbiguityOrPasswordField() {
        val button = PurchaseUiElement("投票確認", null, "button-confirm", true, false, true, false)
        val password = PurchaseUiElement("投票確認", null, "password", true, true, true, true)
        assertEquals(0, PurchaseUiMatching.uniqueVisibleMatch(
            listOf(button, password), PurchaseUiSelector(label = "投票確認")))
        assertNull(PurchaseUiMatching.uniqueVisibleMatch(
            listOf(button, button), PurchaseUiSelector(label = "投票確認")))
        assertNull(PurchaseUiMatching.uniqueVisibleMatch(
            listOf(password), PurchaseUiSelector(resourceId = "password"), forInput = true))
    }
}
