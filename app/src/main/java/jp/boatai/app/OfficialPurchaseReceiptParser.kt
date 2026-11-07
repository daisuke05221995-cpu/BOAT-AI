package jp.boatai.app

/** An accepted screen must prove every ticket, its stake, and an official contract number. */
internal data class OfficialPurchaseReceiptProfile(
    val resultTitle: PurchaseUiSelector,
    val contractNumberResourceId: String,
    val contractNumberPattern: Regex,
    val ticketResultResourceId: String,
    /** Venue, race number, combination, stake, and result (five capture groups). */
    val ticketResultPattern: Regex,
    val totalResourceId: String,
    val totalPattern: Regex
)

internal data class OfficialPurchaseReceipt(
    val sessionId: String,
    val officialContractNumber: String,
    val observedAtMs: Long,
    val lines: List<OfficialPurchaseLine>,
    val totalYen: Int
)

internal object OfficialPurchaseReceiptParser {
    private const val MAX_RECEIPT_WAIT_MS = 30_000L

    fun parse(
        sourcePackage: String,
        elements: List<PurchaseUiElement>,
        session: PendingPurchaseSession,
        profile: OfficialPurchaseReceiptProfile,
        attemptedAtMs: Long,
        observedAtMs: Long
    ): OfficialPurchaseReceipt? {
        if (sourcePackage != BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE ||
            attemptedAtMs <= 0 || observedAtMs <= attemptedAtMs ||
            observedAtMs - attemptedAtMs > MAX_RECEIPT_WAIT_MS ||
            session.selectedRaces.isEmpty()) return null
        if (!uniqueMarker(elements, profile.resultTitle)) return null
        if (profile.contractNumberResourceId.isBlank() || profile.ticketResultResourceId.isBlank() ||
            profile.totalResourceId.isBlank() ||
            setOf(profile.contractNumberResourceId, profile.ticketResultResourceId, profile.totalResourceId).size != 3) return null

        val contractText = singleText(elements, profile.contractNumberResourceId) ?: return null
        val contractMatch = profile.contractNumberPattern.matchEntire(contractText) ?: return null
        if (contractMatch.groupValues.size != 2) return null
        val contractNumber = contractMatch.groupValues[1].trim()
        if (!contractNumber.matches(Regex("[0-9A-Za-z-]{3,40}"))) return null

        val resultRows = elements.filter {
            it.visible && !it.password && it.resourceId == profile.ticketResultResourceId
        }
        if (resultRows.isEmpty() || resultRows.size > 72) return null
        val receivedLines = resultRows.map { element ->
            val row = (element.text ?: element.description)?.trim() ?: return null
            val match = profile.ticketResultPattern.matchEntire(row) ?: return null
            if (match.groupValues.size != 6 || match.groupValues[5] != "成立") return null
            val venue = readVenue(match.groupValues[1]) ?: return null
            val race = match.groupValues[2].toIntOrNull()?.takeIf { it in 1..12 } ?: return null
            val combination = match.groupValues[3].replace('－', '-').trim()
            if (!Regex("^[1-6]-[1-6]-[1-6]$").matches(combination) ||
                combination.split('-').distinct().size != 3) return null
            val amount = readYen(match.groupValues[4]) ?: return null
            OfficialPurchaseLine(venue, race, combination, amount)
        }
        val totalText = singleText(elements, profile.totalResourceId) ?: return null
        val totalMatch = profile.totalPattern.matchEntire(totalText) ?: return null
        if (totalMatch.groupValues.size != 2) return null
        val total = readYen(totalMatch.groupValues[1]) ?: return null
        val expected = session.selectedRaces.flatMap { race ->
            race.tickets.map { ticket ->
                OfficialPurchaseLine(race.stadiumNumber, race.raceNumber, ticket.combination, ticket.amount)
            }
        }
        if (expected.size != receivedLines.size ||
            expected.groupingBy { it }.eachCount() != receivedLines.groupingBy { it }.eachCount() ||
            session.selectedStake != total || receivedLines.sumOf { it.amount } != total) return null
        return OfficialPurchaseReceipt(session.id, contractNumber, observedAtMs, receivedLines, total)
    }

    private fun singleText(elements: List<PurchaseUiElement>, id: String): String? = elements
        .filter { it.visible && !it.password && it.resourceId == id }
        .singleOrNull()?.let { it.text ?: it.description }?.trim()

    private fun uniqueMarker(elements: List<PurchaseUiElement>, selector: PurchaseUiSelector): Boolean {
        if (selector.resourceId.isNullOrBlank() && selector.label.isNullOrBlank()) return false
        return elements.count { element -> element.visible && !element.password &&
            (selector.resourceId == null || selector.resourceId == element.resourceId) &&
            (selector.label == null || selector.label == element.text || selector.label == element.description)
        } == 1
    }

    private fun readVenue(raw: String): Int? = raw.trim().toIntOrNull()?.takeIf { it in 1..24 }
        ?: (1..24).firstOrNull { Venues.name(it) == raw.trim() }

    private fun readYen(raw: String): Int? = raw.replace(",", "").replace("円", "").trim()
        .toIntOrNull()?.takeIf { it in 100..100_000 && it % 100 == 0 }
}
