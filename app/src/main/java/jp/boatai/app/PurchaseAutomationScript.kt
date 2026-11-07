package jp.boatai.app

/**
 * Screen-specific selectors must be calibrated against the actual official app.
 * No guessed resource ID or arbitrary screen coordinate is allowed.
 */
internal data class OfficialPurchaseScreenProfile(
    val venueSelectors: Map<Int, PurchaseUiSelector>,
    val raceSelectors: Map<Int, PurchaseUiSelector>,
    val trifectaSelector: PurchaseUiSelector,
    val laneSelectors: Map<Int, Map<Int, PurchaseUiSelector>>,
    val amountInput: PurchaseUiSelector,
    val addTicket: PurchaseUiSelector,
    val reviewList: PurchaseUiSelector
) {
    fun isFullyMapped(races: List<PendingPurchaseRace>): Boolean =
        races.all { venueSelectors.containsKey(it.stadiumNumber) && raceSelectors.containsKey(it.raceNumber) } &&
            (1..3).all { position -> (1..6).all { boat -> laneSelectors[position]?.containsKey(boat) == true } }
}

internal data class PurchaseAutomationScript(
    val steps: List<PurchaseUiStep>,
    val expectedTicketText: List<String>,
    val expectedTotal: Int
)

/** Produces deterministic setup and entry steps; never includes a submit/commit action. */
internal object PurchaseAutomationScriptCompiler {
    fun compile(
        session: PendingPurchaseSession,
        profile: OfficialPurchaseScreenProfile,
        check: PurchaseAutomationCheck
    ): PurchaseAutomationScript? {
        if (!check.allowed || !profile.isFullyMapped(session.selectedRaces)) return null
        val steps = mutableListOf<PurchaseUiStep>()
        val expected = mutableListOf<String>()
        for (race in session.selectedRaces) {
            steps += PurchaseUiStep.Click(profile.venueSelectors.getValue(race.stadiumNumber))
            steps += PurchaseUiStep.Click(profile.raceSelectors.getValue(race.raceNumber))
            steps += PurchaseUiStep.Click(profile.trifectaSelector)
            for (ticket in race.tickets) {
                val boats = ticket.combination.split('-').map { it.toIntOrNull() ?: return null }
                if (boats.size != 3 || boats.distinct().size != 3) return null
                boats.forEachIndexed { index, boat ->
                    steps += PurchaseUiStep.Click(profile.laneSelectors[index + 1]?.get(boat) ?: return null)
                }
                steps += PurchaseUiStep.EnterText(profile.amountInput, ticket.amount.toString())
                steps += PurchaseUiStep.Click(profile.addTicket)
                expected += "${race.stadiumNumber}:${race.raceNumber}:${ticket.combination}:${ticket.amount}"
            }
        }
        steps += PurchaseUiStep.Click(profile.reviewList)
        return PurchaseAutomationScript(steps, expected, check.sessionStake)
    }
}
