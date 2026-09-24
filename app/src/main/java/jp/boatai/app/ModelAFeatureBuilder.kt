package jp.boatai.app

import java.time.LocalDate
import kotlin.math.max

/**
 * Converts live RaceData into the frozen v0.16 Model A pre-race feature contract.
 *
 * This builder mirrors v016_r2_features.extract() + v016_r4_player_history.enrich()
 * for inference only. It never reads odds or results and never mutates history.
 * Result updates remain day-batched through ModelAPlayerHistory.commitDay().
 */
internal class ModelAFeatureBuilder(
    private val history: ModelAPlayerHistory
) {
    data class LaneHistoryContext(
        val player: Int,
        val course: Int,
        val racerClass: Int,
        val exhibitionTime: Double,
        val previewStartTiming: Double,
        val flags: ModelAPlayerHistory.Flags
    )

    data class BuildResult(
        val input: ModelAConditionalPredictor.Input?,
        val laneHistory: List<LaneHistoryContext>,
        val usable: Boolean,
        val reason: String?,
        val predictionDayOrdinal: Int?,
        val historyThroughDayOrdinal: Int,
        val historyFreshForDay: Boolean
    )

    fun build(race: RaceData): BuildResult {
        val day = runCatching { LocalDate.parse(race.date.take(10)) }.getOrNull()
            ?: return unavailable("Invalid race date", null)
        val dayOrdinal = pythonOrdinal(day)
        if (dayOrdinal <= history.lastDay) {
            return unavailable("History is not strictly earlier than prediction day", dayOrdinal)
        }

        if (race.stadiumNumber !in 1..24 || race.raceNumber <= 0) {
            return unavailable("Invalid venue/race number", dayOrdinal)
        }
        if (race.racers.size != 6 || race.racers.map { it.lane }.toSet() != (1..6).toSet()) {
            return unavailable("Model A requires exactly lanes 1..6", dayOrdinal)
        }
        val racers = race.racers.sortedBy { it.lane }
        val ids = racers.map { it.registrationNumber ?: 0 }
        if (ids.any { it <= 0 } || ids.toSet().size != 6) {
            return unavailable("Missing or duplicate racer registration number", dayOrdinal)
        }

        val current25 = Array(6) { DoubleArray(BASE_CURRENT_FEATURES) { Double.NaN } }
        val classes = IntArray(6)
        for ((index, racer) in racers.withIndex()) {
            val preview = racer.preview
            val cls = racer.classNumber ?: classNumberFromText(racer.rank) ?: 0
            classes[index] = cls
            val row = current25[index]
            row[0] = f32(racer.nationalWinRate)
            row[1] = f32(racer.localWinRate)
            row[2] = f32(racer.nationalTop2)
            row[3] = f32(racer.localTop2)
            row[4] = f32(racer.nationalTop3)
            row[5] = f32(racer.localTop3)
            row[6] = f32(racer.motorTop2)
            row[7] = f32(racer.motorTop3)
            row[8] = f32(racer.boatTop2)
            row[9] = f32(racer.boatTop3)
            row[10] = f32(racer.averageStart)
            row[11] = f32(racer.flyingCount?.toDouble())
            row[12] = f32(racer.lateCount?.toDouble())
            row[13] = f32(racer.age?.toDouble())
            row[14] = f32(racer.weight)
            row[15] = f32(preview?.exhibitionTime)
            row[16] = f32(preview?.startTiming)
            row[17] = f32(preview?.course?.toDouble())
            row[18] = f32(preview?.tilt)
            row[19] = f32(preview?.weightAdjustment)
            for (classNumber in 1..4) {
                row[19 + classNumber] = if (cls == 0) Double.NaN else f32(if (cls == classNumber) 1.0 else 0.0)
            }
            row[24] = preview?.course?.let { f32(if (it != racer.lane) 1.0 else 0.0) } ?: Double.NaN
        }

        val previewCourses = current25.map { it[17] }
        val requiredUsable = current25.all { row ->
            row[15].isFinite() && row[16].isFinite() && row[17].isFinite() && row[0].isFinite()
        }
        val courseSetUsable = previewCourses.all { it.isFinite() } &&
            previewCourses.map { it.toInt() }.toSet() == (1..6).toSet()
        if (!requiredUsable || !courseSetUsable) {
            return unavailable("Missing required Model A pre-race input", dayOrdinal)
        }

        val relative = relativeFeatures(current25)
        val current30 = Array(6) { lane ->
            DoubleArray(CURRENT_FEATURES) { feature ->
                if (feature < BASE_CURRENT_FEATURES) current25[lane][feature]
                else relative[lane][feature - BASE_CURRENT_FEATURES]
            }
        }

        val historyRows = Array(6) { DoubleArray(ModelAPlayerHistory.HISTORY_FEATURES) }
        val reactionRows = Array(6) { DoubleArray(ModelAPlayerHistory.REACTION_FEATURES) }
        val laneHistory = ArrayList<LaneHistoryContext>(6)
        for (lane in 0..5) {
            val row = current25[lane]
            val snapshot = history.snapshot(
                player = ids[lane],
                course = row[17].toInt(),
                racerClass = classes[lane],
                exhibitionTime = row[15],
                previewStartTiming = row[16],
                courseChanged = row[24] == 1.0,
                day = dayOrdinal
            )
            historyRows[lane] = snapshot.history
            reactionRows[lane] = snapshot.reaction
            laneHistory += LaneHistoryContext(
                player = ids[lane],
                course = row[17].toInt(),
                racerClass = classes[lane],
                exhibitionTime = row[15],
                previewStartTiming = row[16],
                flags = snapshot.flags
            )
        }

        val boat = Array(6) { lane ->
            DoubleArray(BOAT_FEATURES).also { out ->
                var offset = 0
                current30[lane].forEach { out[offset++] = f32(it) }
                historyRows[lane].forEach { out[offset++] = f32(it) }
                reactionRows[lane].forEach { out[offset++] = f32(it) }
                require(offset == BOAT_FEATURES)
            }
        }

        val baseGlobal = baseGlobal(race)
        val weak = max(reactionRows[0][1], 0.0) + max(reactionRows[0][3], 0.0)
        var strong = 0
        for (lane in 1..5) {
            if (reactionRows[lane][1] <= -0.5 || reactionRows[lane][3] <= -0.5) strong += 1
        }
        val reactionGlobal = DoubleArray(REACTION_GLOBAL_FEATURES)
        for (index in 0 until 20) reactionGlobal[index] = f32(baseGlobal[index])
        reactionGlobal[20] = f32(weak)
        reactionGlobal[21] = f32(strong.toDouble())
        reactionGlobal[22] = f32(race.stadiumNumber.toDouble())
        reactionGlobal[23] = f32(race.raceNumber.toDouble())

        return BuildResult(
            input = ModelAConditionalPredictor.Input(
                boat = boat,
                global = reactionGlobal,
                venue = race.stadiumNumber,
                raceNumber = race.raceNumber
            ),
            laneHistory = laneHistory,
            usable = true,
            reason = null,
            predictionDayOrdinal = dayOrdinal,
            historyThroughDayOrdinal = history.lastDay,
            historyFreshForDay = history.lastDay == dayOrdinal - 1
        )
    }

    private fun unavailable(reason: String, dayOrdinal: Int?): BuildResult = BuildResult(
        input = null,
        laneHistory = emptyList(),
        usable = false,
        reason = reason,
        predictionDayOrdinal = dayOrdinal,
        historyThroughDayOrdinal = history.lastDay,
        historyFreshForDay = dayOrdinal != null && history.lastDay == dayOrdinal - 1
    )

    private fun relativeFeatures(current: Array<DoubleArray>): Array<DoubleArray> {
        val exhibitions = DoubleArray(6) { lane -> current[lane][15] }
        val starts = DoubleArray(6) { lane -> current[lane][16] }
        val exMin = exhibitions.minOrNull()!!
        val exMax = exhibitions.maxOrNull()!!
        return Array(6) { lane ->
            doubleArrayOf(
                f32(1.0 + exhibitions.count { exhibitions[lane] > it }),
                f32(1.0 + starts.count { starts[lane] > it }),
                f32(exhibitions[lane] - exMin),
                f32(exhibitions[lane] - exMax),
                f32(exhibitions[lane] - exhibitions[0])
            )
        }
    }

    private fun baseGlobal(race: RaceData): DoubleArray {
        val preview = race.preview
        val out = DoubleArray(BASE_GLOBAL_FEATURES) { Double.NaN }
        out[0] = f32(preview?.windSpeed?.toDouble())
        out[1] = f32(preview?.waveHeight?.toDouble())
        out[2] = f32(preview?.airTemperature)
        out[3] = f32(preview?.waterTemperature)
        val direction = preview?.windDirectionNumber?.takeIf { it in 1..16 } ?: parseNumber(preview?.windDirection)
        for (i in 1..16) {
            out[3 + i] = if (direction == null) Double.NaN else f32(if (direction == i) 1.0 else 0.0)
        }
        out[20] = f32(race.stadiumNumber.toDouble())
        out[21] = f32(race.raceNumber.toDouble())
        return out
    }

    private fun parseNumber(value: String?): Int? = value
        ?.let { Regex("""\d+""").find(it)?.value?.toIntOrNull() }
        ?.takeIf { it in 1..16 }

    private fun classNumberFromText(value: String): Int? = when (value.trim().uppercase()) {
        "A1" -> 1
        "A2" -> 2
        "B1" -> 3
        "B2" -> 4
        else -> value.toIntOrNull()?.takeIf { it in 1..4 }
    }

    private fun f32(value: Double?): Double = value?.takeIf { it.isFinite() }?.toFloat()?.toDouble() ?: Double.NaN

    companion object {
        private const val BASE_CURRENT_FEATURES = 25
        private const val CURRENT_FEATURES = 30
        private const val BOAT_FEATURES = 82
        private const val BASE_GLOBAL_FEATURES = 22
        private const val REACTION_GLOBAL_FEATURES = 24
        private const val PYTHON_ORDINAL_AT_UNIX_EPOCH = 719_163L

        fun pythonOrdinal(date: LocalDate): Int = Math.toIntExact(date.toEpochDay() + PYTHON_ORDINAL_AT_UNIX_EPOCH)
    }
}
