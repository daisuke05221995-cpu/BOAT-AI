package jp.boatai.app

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Locally stored official evidence, separate from BOAT AI's predicted/virtual bets. */
internal object OfficialPurchaseReceiptCodec {
    fun encode(receipt: OfficialPurchaseReceipt): String = JSONObject().apply {
        put("sessionId", receipt.sessionId)
        put("contractNumber", receipt.officialContractNumber)
        put("observedAtMs", receipt.observedAtMs)
        put("totalYen", receipt.totalYen)
        put("tickets", JSONArray().apply {
            receipt.lines.forEach { line ->
                put(JSONObject().apply {
                    put("venue", line.stadiumNumber)
                    put("race", line.raceNumber)
                    put("combination", line.combination)
                    put("amount", line.amount)
                })
            }
        })
    }.toString()

    fun decode(raw: String): OfficialPurchaseReceipt? = runCatching {
        require(raw.length <= 16_000)
        val json = JSONObject(raw)
        val tickets = json.getJSONArray("tickets")
        require(tickets.length() in 1..72)
        val lines = (0 until tickets.length()).map { index ->
            val ticket = tickets.getJSONObject(index)
            val venue = ticket.getInt("venue").also { require(it in 1..24) }
            val race = ticket.getInt("race").also { require(it in 1..12) }
            val combination = ticket.getString("combination").also {
                require(it.matches(Regex("[1-6]-[1-6]-[1-6]")) && it.split('-').distinct().size == 3)
            }
            val amount = ticket.getInt("amount").also { require(it in 100..100_000 && it % 100 == 0) }
            OfficialPurchaseLine(venue, race, combination, amount)
        }
        val total = json.getInt("totalYen")
        require(total == lines.sumOf { it.amount })
        OfficialPurchaseReceipt(
            json.getString("sessionId").also { require(it.length in 1..128) },
            json.getString("contractNumber").also { require(it.matches(Regex("[0-9A-Za-z-]{3,40}"))) },
            json.getLong("observedAtMs").also { require(it > 0) },
            lines,
            total
        )
    }.getOrNull()
}

internal class OfficialPurchaseReceiptStore(context: Context) {
    private val preferences = context.getSharedPreferences("official_purchase_receipts", Context.MODE_PRIVATE)

    @Synchronized
    fun save(receipt: OfficialPurchaseReceipt): Boolean {
        val serialized = OfficialPurchaseReceiptCodec.encode(receipt)
        if (OfficialPurchaseReceiptCodec.decode(serialized) != receipt) return false
        val key = "receipt_${receipt.sessionId}"
        if (preferences.contains(key)) return false
        return preferences.edit().putString(key, serialized).commit()
    }

    fun forSession(sessionId: String): OfficialPurchaseReceipt? =
        preferences.getString("receipt_$sessionId", null)?.let(OfficialPurchaseReceiptCodec::decode)
}
