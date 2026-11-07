package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OfficialPurchaseReceiptParserTest {
    private val official = BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE
    private val session = PendingPurchaseSession(
        id = "receipt-session", createdAt = 1_000,
        races = listOf(PendingPurchaseRace("r1", "2026-11-08", 1, 1, "桐生", true,
            listOf(PendingPurchaseTicket("1-3-5", 500), PendingPurchaseTicket("2-1-4", 300)))),
        selectedRaceIds = setOf("r1")
    )
    private val profile = OfficialPurchaseReceiptProfile(
        resultTitle = PurchaseUiSelector(resourceId = "official:receipt_title"),
        contractNumberResourceId = "official:contract",
        contractNumberPattern = Regex("契約番号 ([0-9]+)"),
        ticketResultResourceId = "official:receipt_row",
        ticketResultPattern = Regex("(.+?) ([0-9]+)R ([1-6]-[1-6]-[1-6]) ([0-9,]+)円 (成立|不成立)"),
        totalResourceId = "official:receipt_total",
        totalPattern = Regex("合計 ([0-9,]+)円")
    )
    private fun element(id: String, value: String) = PurchaseUiElement(
        value, null, id, clickable = false, editable = false, visible = true, password = false
    )
    private val elements = listOf(
        element("official:receipt_title", "投票結果"),
        element("official:contract", "契約番号 0011"),
        element("official:receipt_row", "桐生 1R 1-3-5 500円 成立"),
        element("official:receipt_row", "桐生 1R 2-1-4 300円 成立"),
        element("official:receipt_total", "合計 800円")
    )

    @Test fun acceptsOnlyExactOfficialContractAndEverySuccessfulTicket() {
        val receipt = OfficialPurchaseReceiptParser.parse(official, elements, session, profile, 2_000, 3_000)
        assertNotNull(receipt)
        assertEquals("0011", receipt!!.officialContractNumber)
        assertEquals(800, receipt.totalYen)
        assertEquals(2, receipt.lines.size)
    }

    @Test fun rejectsUnsettledRowsStaleResultsAndExtraTickets() {
        val failedRow = elements.map { if (it.text?.contains("2-1-4") == true) it.copy(text =
            "桐生 1R 2-1-4 300円 不成立") else it }
        assertNull(OfficialPurchaseReceiptParser.parse(official, failedRow, session, profile, 2_000, 3_000))
        assertNull(OfficialPurchaseReceiptParser.parse(official, elements, session, profile, 2_000, 33_001))
        assertNull(OfficialPurchaseReceiptParser.parse("other.app", elements, session, profile, 2_000, 3_000))
        assertNull(OfficialPurchaseReceiptParser.parse(official,
            elements + element("official:receipt_row", "桐生 1R 1-2-3 100円 成立"),
            session, profile, 2_000, 3_000))
    }

    @Test fun recordsOnlyCompleteOfficialEvidence() {
        val receipt = OfficialPurchaseReceiptParser.parse(official, elements, session, profile, 2_000, 3_000)!!
        assertEquals(receipt, OfficialPurchaseReceiptCodec.decode(OfficialPurchaseReceiptCodec.encode(receipt)))
        val json = org.json.JSONObject(OfficialPurchaseReceiptCodec.encode(receipt))
        json.put("totalYen", 900)
        assertNull(OfficialPurchaseReceiptCodec.decode(json.toString()))
        assertTrue(receipt.lines.all { it.amount > 0 })
    }

    @Test fun refusesReceiptWithoutUniqueTitleContractOrExactTotal() {
        assertNull(OfficialPurchaseReceiptParser.parse(official, elements + elements.first(), session, profile, 2_000, 3_000))
        assertNull(OfficialPurchaseReceiptParser.parse(official,
            elements.map { if (it.resourceId == "official:contract") it.copy(text = "受付なし") else it },
            session, profile, 2_000, 3_000))
        assertNull(OfficialPurchaseReceiptParser.parse(official,
            elements.map { if (it.resourceId == "official:receipt_total") it.copy(text = "合計 700円") else it },
            session, profile, 2_000, 3_000))
    }
}
