package jp.boatai.app

/**
 * Review-page calibration must come from a real official Android app screen.
 * Every item matching [rowResourceId] is treated as a ticket: one malformed/extra row fails closed.
 */
internal data class OfficialPurchaseReviewProfile(
    val rowResourceId: String,
    val totalResourceId: String,
    /** Four capture groups, in this order: venue, race number, combination, stake. */
    val ticketRowPattern: Regex,
    /** One capture group: total stake. */
    val totalPattern: Regex,
    val submitButton: PurchaseUiSelector,
    val reviewTitle: PurchaseUiSelector
)

internal object OfficialPurchaseReviewParser {
    fun parse(
        sourcePackage: String,
        elements: List<PurchaseUiElement>,
        profile: OfficialPurchaseReviewProfile,
        observedAtMs: Long
    ): OfficialPurchaseReview? {
        if (sourcePackage != BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE) return null
        if (profile.rowResourceId.isBlank() || profile.totalResourceId.isBlank() ||
            profile.rowResourceId == profile.totalResourceId ||
            !uniqueTitleMarker(elements, profile.reviewTitle) ||
            PurchaseUiMatching.uniqueVisibleMatch(elements, profile.submitButton) == null) return null

        val rowElements = elements.filter {
            it.visible && !it.password && it.resourceId == profile.rowResourceId
        }
        if (rowElements.isEmpty() || rowElements.size > 72) return null
        val lines = rowElements.map { element ->
            val text = element.text?.trim() ?: element.description?.trim() ?: return null
            val match = profile.ticketRowPattern.matchEntire(text) ?: return null
            if (match.groupValues.size != 5) return null
            val venue = readVenue(match.groupValues[1]) ?: return null
            val race = match.groupValues[2].toIntOrNull()?.takeIf { it in 1..12 } ?: return null
            val combo = match.groupValues[3].replace('－', '-').trim()
            if (!Regex("^[1-6]-[1-6]-[1-6]$").matches(combo) ||
                combo.split('-').distinct().size != 3) return null
            val amount = readYen(match.groupValues[4]) ?: return null
            OfficialPurchaseLine(venue, race, combo, amount)
        }
        val totals = elements.filter { it.visible && !it.password && it.resourceId == profile.totalResourceId }
        val totalText = totals.singleOrNull()?.let { it.text ?: it.description }?.trim() ?: return null
        val totalMatch = profile.totalPattern.matchEntire(totalText) ?: return null
        if (totalMatch.groupValues.size != 2) return null
        val total = readYen(totalMatch.groupValues[1]) ?: return null
        if (lines.sumOf { it.amount } != total) return null
        return OfficialPurchaseReview(sourcePackage, observedAtMs, lines, total)
    }

    private fun uniqueTitleMarker(elements: List<PurchaseUiElement>, selector: PurchaseUiSelector): Boolean {
        if (selector.label.isNullOrBlank() && selector.resourceId.isNullOrBlank()) return false
        return elements.count { element ->
            element.visible && !element.password &&
                (selector.resourceId == null || element.resourceId == selector.resourceId) &&
                (selector.label == null || element.text == selector.label || element.description == selector.label)
        } == 1
    }

    private fun readVenue(input: String): Int? = input.trim().toIntOrNull()?.takeIf { it in 1..24 }
        ?: (1..24).firstOrNull { Venues.name(it) == input.trim() }

    private fun readYen(input: String): Int? = input.replace(",", "").replace("円", "").trim()
        .toIntOrNull()?.takeIf { it in 100..100_000 && it % 100 == 0 }
}
