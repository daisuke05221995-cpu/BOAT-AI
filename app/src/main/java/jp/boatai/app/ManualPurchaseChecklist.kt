package jp.boatai.app

import java.util.Locale

/**
 * Read-only Android presentation of the research manual-purchase handoff.
 * Receiving, copying, or viewing this checklist NEVER records a purchase.
 * Neither official-app accessibility clicks nor account data are involved.
 */
internal data class ManualPurchaseChecklistResult(
    val valid: Boolean,
    val message: String,
    val clipboardText: String? = null
)

internal object ManualPurchaseChecklist {
    private val trifecta = Regex("^[1-6]-[1-6]-[1-6]$")
    private val date = Regex("^\\d{4}-\\d{2}-\\d{2}$")

    fun prepare(
        handoff: CollectorPurchaseHandoff,
        nowMs: Long = System.currentTimeMillis()
    ): ManualPurchaseChecklistResult {
        fun invalid(message: String) = ManualPurchaseChecklistResult(false, message)
        if (handoff.expiresAt <= nowMs) return invalid("転送の有効期限が切れています。1台目で買い目を再確認してください。")

        val races = handoff.session.selectedRaces
        if (races.isEmpty() || races.size > 24 || races.map { it.raceId }.toSet().size != races.size) {
            return invalid("受信したレース情報が不正です")
        }

        val lines = mutableListOf(
            "【BOAT AI・受信済み／未購入】",
            "転送ID: ${handoff.handoffId}"
        )
        var total = 0L
        var count = 0
        for (race in races) {
            if (race.raceId.isBlank() || !date.matches(race.date) ||
                race.stadiumNumber !in 1..24 || race.raceNumber !in 1..12 ||
                race.venueName.isBlank() || race.tickets.isEmpty() || race.tickets.size > 120
            ) return invalid("受信したレース情報が不正です")

            val unique = HashSet<String>()
            var subtotal = 0L
            lines.add("")
            lines.add("${race.date}  ${race.venueName} ${race.raceNumber}R")
            for (ticket in race.tickets) {
                val combination = ticket.combination
                val lanes = combination.split("-")
                if (!trifecta.matches(combination) || lanes.distinct().size != 3 ||
                    !unique.add(combination) || ticket.amount < 100 || ticket.amount % 100 != 0
                ) return invalid("買い目・金額の重複または不正な形式があります")
                subtotal += ticket.amount.toLong()
                total += ticket.amount.toLong()
                count++
                if (total > Int.MAX_VALUE) return invalid("購入予定金額が不正です")
                lines.add("${combination}    ${yen(ticket.amount)}円")
            }
            lines.add("このレースの小計  ${yen(subtotal)}円")
        }

        if (total != handoff.session.selectedStake.toLong() ||
            count != handoff.session.selectedTicketCount
        ) return invalid("受信した合計金額と買い目が一致しません")

        lines.add("")
        lines.add("合計 ${count}点  ${yen(total)}円")
        lines.add("※受信・コピーだけでは購入していません。")
        lines.add("公式投票画面で本人が買い目・金額・合計を照合して手動購入し、公式の受付履歴を確認してください。")
        return ManualPurchaseChecklistResult(
            valid = true,
            message = "未購入の確認表をコピーしました。公式投票で本人が照合してください。",
            clipboardText = lines.joinToString("\n")
        )
    }

    private fun yen(amount: Number): String = String.format(Locale.JAPAN, "%,d", amount.toLong())
}
