package jp.boatai.app

import org.json.JSONObject

object Venues {
    private val names = mapOf(
        1 to "桐生", 2 to "戸田", 3 to "江戸川", 4 to "平和島", 5 to "多摩川", 6 to "浜名湖",
        7 to "蒲郡", 8 to "常滑", 9 to "津", 10 to "三国", 11 to "びわこ", 12 to "住之江",
        13 to "尼崎", 14 to "鳴門", 15 to "丸亀", 16 to "児島", 17 to "宮島", 18 to "徳山",
        19 to "下関", 20 to "若松", 21 to "芦屋", 22 to "福岡", 23 to "唐津", 24 to "大村"
    )

    fun name(number: Int): String = names[number] ?: "場$number"
    fun code(number: Int): String = number.toString().padStart(2, '0')
}

data class PreviewRacer(
    val course: Int?,
    val startTiming: Double?,
    val weight: Double?,
    val weightAdjustment: Double?,
    val exhibitionTime: Double?,
    val tilt: Double?
)

data class Racer(
    val lane: Int,
    val name: String,
    val registrationNumber: Int?,
    val rank: String,
    val branch: String?,
    val age: Int?,
    val weight: Double?,
    val averageStart: Double?,
    val nationalWinRate: Double?,
    val nationalTop2: Double?,
    val nationalTop3: Double?,
    val localWinRate: Double?,
    val localTop2: Double?,
    val localTop3: Double?,
    val motorNumber: Int?,
    val motorTop2: Double?,
    val motorTop3: Double?,
    val boatNumber: Int?,
    val boatTop2: Double?,
    val boatTop3: Double?,
    val preview: PreviewRacer?
)

data class PreviewData(
    val windSpeed: Int?,
    val windDirection: String?,
    val waveHeight: Int?,
    val weather: String?,
    val airTemperature: Double?,
    val waterTemperature: Double?
)

data class RaceResultData(
    val trifectaCombination: String?,
    val trifectaPayout: Int?,
    val technique: String?
)

data class RaceData(
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val closedAt: String,
    val gradeNumber: Int?,
    val title: String,
    val subtitle: String,
    val distance: Int?,
    val dayNumber: Int?,
    val racers: List<Racer>,
    val preview: PreviewData?,
    val result: RaceResultData?
) {
    val id: String get() = "$date-${Venues.code(stadiumNumber)}-$raceNumber"
    val venueName: String get() = Venues.name(stadiumNumber)
    val hasResult: Boolean get() = !result?.trifectaCombination.isNullOrBlank()
}

data class PredictionPick(
    val combination: String,
    val score: Double,
    val odds: Double? = null
)

data class BetRecord(
    val id: String,
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val combination: String,
    val stake: Int,
    val payout: Int,
    val settled: Boolean,
    val createdAt: Long
) {
    val venueName: String get() = Venues.name(stadiumNumber)
    val profit: Int get() = payout - stake

    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("date", date)
        put("stadiumNumber", stadiumNumber)
        put("raceNumber", raceNumber)
        put("combination", combination)
        put("stake", stake)
        put("payout", payout)
        put("settled", settled)
        put("createdAt", createdAt)
    }

    companion object {
        fun fromJson(obj: JSONObject): BetRecord = BetRecord(
            id = obj.optString("id"),
            date = obj.optString("date"),
            stadiumNumber = obj.optInt("stadiumNumber"),
            raceNumber = obj.optInt("raceNumber"),
            combination = obj.optString("combination"),
            stake = obj.optInt("stake"),
            payout = obj.optInt("payout"),
            settled = obj.optBoolean("settled"),
            createdAt = obj.optLong("createdAt")
        )
    }
}

internal fun JSONObject.optIntOrNull(key: String): Int? =
    if (!has(key) || isNull(key)) null else optInt(key)

internal fun JSONObject.optDoubleOrNull(key: String): Double? =
    if (!has(key) || isNull(key)) null else optDouble(key).takeUnless { it.isNaN() }

internal fun JSONObject.optTextOrNull(key: String): String? =
    if (!has(key) || isNull(key)) null else optString(key).trim().takeIf { it.isNotBlank() }
