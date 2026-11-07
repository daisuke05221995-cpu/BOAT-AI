package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

class OfficialPurchaseReviewParserTest {
    private val packageName = BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE
    private val profile = OfficialPurchaseReviewProfile(
        nextToConfirmation = PurchaseUiSelector(resourceId = "official:next"),
        confirmationTotalInput = PurchaseUiSelector(resourceId = "official:confirm_amount"),
        rowResourceId = "official:ticket_row",
        totalResourceId = "official:total",
        ticketRowPattern = Regex("(.+?)\\s+(\\d{1,2})R\\s+([1-6]-[1-6]-[1-6])\\s+([0-9,]+)円"),
        totalPattern = Regex("合計\\s*([0-9,]+)円"),
        submitButton = PurchaseUiSelector(resourceId = "official:submit"),
        reviewTitle = PurchaseUiSelector(resourceId = "official:review_title")
    )

    private fun element(id: String, text: String, clickable: Boolean = false) = PurchaseUiElement(
        text = text, description = null, resourceId = id,
        clickable = clickable, editable = false, visible = true, password = false
    )

    private val rows = listOf(
        element("official:review_title", "投票確認"),
        element("official:ticket_row", "桐生 1R 1-3-5 500円"),
        element("official:ticket_row", "桐生 1R 2-1-4 300円"),
        element("official:total", "合計 800円"),
        element("official:submit", "投票", clickable = true)
    )

    @Test fun parsesOnlyStrictlyIdentifiedOfficialRowsAndTotal() {
        val review = OfficialPurchaseReviewParser.parse(packageName, rows, profile, 1_000)
        assertNotNull(review)
        assertEquals(800, review!!.displayedTotal)
        assertEquals(listOf("1-3-5", "2-1-4"), review.lines.map { it.combination })
    }

    @Test fun rejectsExtraMalformedRowTotalMismatchAndWrongApp() {
        assertNull(OfficialPurchaseReviewParser.parse("other.app", rows, profile, 1_000))
        assertNull(OfficialPurchaseReviewParser.parse(packageName,
            rows + element("official:ticket_row", "表示が読めない買い目"), profile, 1_000))
        assertNull(OfficialPurchaseReviewParser.parse(packageName,
            rows.map { if (it.resourceId == "official:total") it.copy(text = "合計 900円") else it }, profile, 1_000))
        assertNull(OfficialPurchaseReviewParser.parse(packageName,
            rows.filterNot { it.resourceId == "official:review_title" }, profile, 1_000))
    }

    @Test fun independentConfirmationInputReadbackMustMatchTotal() {
        assertTrue(OfficialConfirmationAmount.matches("2,000円", 2_000))
        assertFalse(OfficialConfirmationAmount.matches("200", 2_000))
        assertFalse(OfficialConfirmationAmount.matches(null, 2_000))
        assertFalse(OfficialConfirmationAmount.matches("暗証番号", 2_000))
    }
}
