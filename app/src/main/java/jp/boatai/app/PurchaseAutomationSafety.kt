package jp.boatai.app

import java.time.Duration
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

/** Guardrails for an opt-in Android purchase assistant. No wager is submitted here. */
internal data class PurchaseAutomationLimits(
    val maxSessionStake: Int = 5_000,
    val maxTicketsPerRace: Int = 6,
    val minSecondsToDeadline: Long = 120
)

internal data class PurchaseAutomationCheck(
    val allowed: Boolean,
    val reason: String,
    val sessionStake: Int = 0,
    val selectedTickets: Int = 0
)

internal object PurchaseAutomationSafety {
    private val combinationFormat = Regex("^[1-6]-[1-6]-[1-6]$")
    private val timeFormat = Regex("(\\d{1,2}):(\\d{2})")

    fun validate(
        session: PendingPurchaseSession,
        liveRaces: List<RaceData>,
        now: LocalDateTime = LocalDateTime.now(ZoneId.of("Asia/Tokyo")),
        limits: PurchaseAutomationLimits = PurchaseAutomationLimits()
    ): PurchaseAutomationCheck {
        val selected = session.selectedRaces
        if (selected.isEmpty()) return blocked("買い目が選択されていません")
        if (selected.size > 12 || selected.map { it.raceId }.distinct().size != selected.size) {
            return blocked("重複または過大なレース指定です")
        }
        val racesById = liveRaces.associateBy { it.id }
        var total = 0L
        var count = 0
        for (race in selected) {
            val current = racesById[race.raceId] ?: return blocked("${race.venueName} ${race.raceNumber}Rの最新開催情報がありません")
            if (current.date != now.toLocalDate().toString() || !current.isPurchasable(now)) {
                return blocked("${race.venueName} ${race.raceNumber}Rは発売中と確認できません")
            }
            val match = timeFormat.findAll(current.closedAt).lastOrNull() ?: return blocked("締切時刻を確認できません")
            val closing = runCatching { LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt()) }
                .getOrNull() ?: return blocked("締切時刻の形式が不正です")
            if (Duration.between(now.toLocalTime(), closing).seconds < limits.minSecondsToDeadline) {
                return blocked("${race.venueName} ${race.raceNumber}Rは締切が近すぎます")
            }
            if (race.tickets.isEmpty() || race.tickets.size > limits.maxTicketsPerRace) {
                return blocked("1レースの買い目が上限を超えています")
            }
            val seen = mutableSetOf<String>()
            for (ticket in race.tickets) {
                val nums = ticket.combination.split('-')
                if (!combinationFormat.matches(ticket.combination) || nums.distinct().size != 3 ||
                    !seen.add(ticket.combination)) return blocked("舟券の組番に不正または重複があります")
                if (ticket.amount < 100 || ticket.amount % 100 != 0) return blocked("金額は100円単位が必要です")
                total += ticket.amount
                count++
            }
        }
        if (total > limits.maxSessionStake) return blocked("合計金額が自動操作の上限${limits.maxSessionStake}円を超えています")
        return PurchaseAutomationCheck(true, "内容・締切・金額の事前検査を通過", total.toInt(), count)
    }

    private fun blocked(reason: String) = PurchaseAutomationCheck(false, reason)
}

/** Semantic selector. Ambiguous buttons or hidden/password inputs are never actionable. */
internal data class PurchaseUiElement(
    val text: String?,
    val description: String?,
    val resourceId: String?,
    val clickable: Boolean,
    val editable: Boolean,
    val visible: Boolean,
    val password: Boolean
)

internal data class PurchaseUiSelector(val label: String? = null, val resourceId: String? = null)

internal object PurchaseUiMatching {
    fun uniqueVisibleMatch(
        elements: List<PurchaseUiElement>,
        selector: PurchaseUiSelector,
        forInput: Boolean = false
    ): Int? {
        if (selector.label.isNullOrBlank() && selector.resourceId.isNullOrBlank()) return null
        val matches = elements.indices.filter { index ->
            val item = elements[index]
            item.visible && !item.password &&
                (if (forInput) item.editable else item.clickable) &&
                (selector.resourceId == null || item.resourceId == selector.resourceId) &&
                (selector.label == null || item.text == selector.label || item.description == selector.label)
        }
        return matches.singleOrNull()
    }
}
