package jp.boatai.app

import android.content.Context
import org.json.JSONObject

/**
 * Locally imported, screen-calibrated selectors. They are data, not executable code.
 * Unknown or incomplete mappings do not trigger exploratory clicks.
 */
internal object OfficialPurchaseProfileCodec {
    fun decode(raw: String): OfficialPurchaseScreenProfile? = runCatching {
        require(raw.isNotBlank() && raw.length <= 24_000)
        val root = JSONObject(raw)
        fun selector(value: JSONObject): PurchaseUiSelector {
            val id = value.optString("id").trim().takeIf { it.isNotEmpty() }
            val label = value.optString("label").trim().takeIf { it.isNotEmpty() }
            require(id != null || label != null)
            require((id?.length ?: 0) <= 180 && (label?.length ?: 0) <= 80)
            return PurchaseUiSelector(label = label, resourceId = id)
        }
        fun selectorMap(value: JSONObject): Map<Int, PurchaseUiSelector> =
            value.keys().asSequence().associate { rawKey ->
                val index = rawKey.toInt()
                require(index in 1..24)
                index to selector(value.getJSONObject(rawKey))
            }

        val finalization = root.optJSONObject("finalization")?.let { config ->
            val rowId = config.getString("rowId").trim()
            val totalId = config.getString("totalId").trim()
            val rowPattern = config.getString("rowPattern")
            val totalPattern = config.getString("totalPattern")
            require(rowId.length in 5..180 && totalId.length in 5..180 &&
                rowPattern.length in 10..220 && totalPattern.length in 5..140)
            OfficialPurchaseReviewProfile(
                rowResourceId = rowId,
                totalResourceId = totalId,
                ticketRowPattern = Regex(rowPattern),
                totalPattern = Regex(totalPattern),
                submitButton = selector(config.getJSONObject("submit")),
                reviewTitle = selector(config.getJSONObject("title"))
            )
        }

        val laneRoot = root.getJSONObject("lanes")
        val laneMap = laneRoot.keys().asSequence().associate { rawKey ->
            val position = rawKey.toInt()
            require(position in 1..3)
            val boats = selectorMap(laneRoot.getJSONObject(rawKey))
            require(boats.keys.all { it in 1..6 })
            position to boats
        }
        OfficialPurchaseScreenProfile(
            venueSelectors = selectorMap(root.getJSONObject("venues")),
            raceSelectors = selectorMap(root.getJSONObject("races")),
            trifectaSelector = selector(root.getJSONObject("trifecta")),
            laneSelectors = laneMap,
            amountInput = selector(root.getJSONObject("amount")),
            addTicket = selector(root.getJSONObject("add")),
            reviewList = selector(root.getJSONObject("review")),
            finalization = finalization
        ).also { profile ->
            require(profile.venueSelectors.keys.all { it in 1..24 })
            require(profile.raceSelectors.keys.all { it in 1..12 })
            require((1..3).all { pos -> (1..6).all { boat -> profile.laneSelectors[pos]?.containsKey(boat) == true } })
        }
    }.getOrNull()
}

internal class OfficialPurchaseProfileStore(context: Context) {
    private val preferences = context.getSharedPreferences("official_purchase_ui_calibration", Context.MODE_PRIVATE)

    fun save(raw: String): Boolean {
        if (OfficialPurchaseProfileCodec.decode(raw) == null) return false
        return preferences.edit().putString("calibration_json", raw).commit()
    }

    fun load(): OfficialPurchaseScreenProfile? =
        preferences.getString("calibration_json", null)?.let(OfficialPurchaseProfileCodec::decode)

    fun hasValidProfile(): Boolean = load() != null

    fun clear() = preferences.edit().remove("calibration_json").apply()
}
