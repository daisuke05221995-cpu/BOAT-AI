package jp.boatai.app

import org.json.JSONArray
import org.json.JSONObject
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

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

    fun isPurchasable(now: LocalDateTime = LocalDateTime.now(ZoneId.of("Asia/Tokyo"))): Boolean {
        val raceDate = runCatching { LocalDate.parse(date.take(10)) }.getOrNull() ?: return false
        if (raceDate != now.toLocalDate() || hasResult || racers.size < 3) return false
        val time = Regex("""(\d{1,2}):(\d{2})""").findAll(closedAt).lastOrNull()?.let {
            runCatching { LocalTime.of(it.groupValues[1].toInt(), it.groupValues[2].toInt()) }.getOrNull()
        } ?: return false
        return now.toLocalTime().isBefore(time)
    }

    val isDataComplete: Boolean
        get() = racers.size == 6 && racers.all { it.name.isNotBlank() }
}

data class PredictionPick(
    val combination: String,
    val score: Double,
    val odds: Double? = null,
    val recommendedStake: Int = 0,
    val tier: BetTier = BetTier.MAIN,
    val reason: String = ""
)

enum class BetTier(val label: String) {
    MAIN("本線"),
    MID("中穴"),
    LONG("超穴")
}

enum class RaceRecommendation(val label: String) {
    BUY("購入推奨"),
    SKIP("見送り")
}

data class RecommendationDecision(
    val recommendation: RaceRecommendation,
    val reason: String
) {
    val recommended: Boolean get() = recommendation == RaceRecommendation.BUY
}

enum class DiagnosticStatus { OK, WARNING, ERROR, WAITING }

data class DataSourceDiagnostic(
    val source: String,
    val status: DiagnosticStatus,
    val detail: String,
    val checkedAt: Long = System.currentTimeMillis()
)

data class DateLoadResult(
    val races: List<RaceData>,
    val diagnostics: List<DataSourceDiagnostic>
)

data class OddsFetchResult(
    val odds: Map<String, Double>,
    val source: String,
    val diagnostics: List<DataSourceDiagnostic>,
    val fetchedAt: Long = System.currentTimeMillis()
)

data class PredictionRecord(
    val id: String,
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val combinations: List<String>,
    val stakePerPick: Int,
    val resultCombination: String?,
    val trifectaPayout: Int,
    val settled: Boolean,
    val createdAt: Long,
    val confidence: Int = 0,
    val rank: String = "D",
    val firstLane: Int? = null,
    val evaluationEligible: Boolean = false,
    val autoSkipped: Boolean = false,
    val autoSkipReason: String? = null,
    val recommended: Boolean = false,
    val recommendationReason: String? = null,
    val stakes: List<Int> = emptyList()
) {
    val venueName: String get() = Venues.name(stadiumNumber)
    val recommendation: RaceRecommendation get() = if (recommended) RaceRecommendation.BUY else RaceRecommendation.SKIP
    val simulatedStake: Int get() = if (stakes.size == combinations.size) stakes.sum() else stakePerPick * combinations.size
    val hit: Boolean get() = settled && !resultCombination.isNullOrBlank() && resultCombination in combinations
    val simulatedPayout: Int
        get() {
            if (!hit) return 0
            val index = combinations.indexOf(resultCombination)
            val stake = if (stakes.size == combinations.size) stakes[index] else stakePerPick
            return if (stake >= 100) trifectaPayout * (stake / 100) else 0
        }
    val simulatedProfit: Int get() = simulatedPayout - simulatedStake

    fun toJson(): JSONObject = JSONObject().apply {
        put("id", id)
        put("date", date)
        put("stadiumNumber", stadiumNumber)
        put("raceNumber", raceNumber)
        put("combinations", JSONArray().apply { combinations.forEach { put(it) } })
        put("stakePerPick", stakePerPick)
        if (stakes.isNotEmpty()) put("stakes", JSONArray().apply { stakes.forEach { put(it) } })
        put("resultCombination", resultCombination)
        put("trifectaPayout", trifectaPayout)
        put("settled", settled)
        put("createdAt", createdAt)
        put("confidence", confidence)
        put("rank", rank)
        if (firstLane != null) put("firstLane", firstLane)
        put("evaluationEligible", evaluationEligible)
        put("autoSkipped", autoSkipped)
        put("autoSkipReason", autoSkipReason)
        put("recommended", recommended)
        put("recommendationReason", recommendationReason)
    }

    companion object {
        fun fromJson(obj: JSONObject): PredictionRecord {
            val combinations = buildList {
                val array = obj.optJSONArray("combinations")
                if (array != null) {
                    for (i in 0 until array.length()) {
                        array.optString(i).takeIf { it.isNotBlank() }?.let { add(it) }
                    }
                }
            }
            val confidence = obj.optInt("confidence", 0)
            val autoSkipped = obj.optBoolean("autoSkipped", false)
            val stakes = obj.optJSONArray("stakes")?.let { array ->
                List(array.length()) { index -> array.optInt(index) }
                    .takeIf { it.size == combinations.size && it.all { stake -> stake >= 100 && stake % 100 == 0 } }
            }.orEmpty()
            return PredictionRecord(
                id = obj.optString("id"),
                date = obj.optString("date"),
                stadiumNumber = obj.optInt("stadiumNumber"),
                raceNumber = obj.optInt("raceNumber"),
                combinations = combinations,
                stakePerPick = obj.optInt("stakePerPick", 300),
                resultCombination = obj.optString("resultCombination").takeIf { it.isNotBlank() },
                trifectaPayout = obj.optInt("trifectaPayout"),
                settled = obj.optBoolean("settled"),
                createdAt = obj.optLong("createdAt"),
                confidence = confidence,
                rank = obj.optString("rank", "D").ifBlank { "D" },
                firstLane = if (obj.has("firstLane") && !obj.isNull("firstLane")) obj.optInt("firstLane") else null,
                evaluationEligible = obj.optBoolean("evaluationEligible", false),
                autoSkipped = autoSkipped,
                autoSkipReason = obj.optString("autoSkipReason").takeIf { it.isNotBlank() },
                recommended = if (obj.has("recommended")) obj.optBoolean("recommended") else !autoSkipped && confidence >= 70,
                recommendationReason = obj.optString("recommendationReason").takeIf { it.isNotBlank() },
                stakes = stakes
            )
        }
    }
}

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
