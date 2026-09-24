package jp.boatai.app

import kotlin.math.max
import kotlin.math.sqrt

/**
 * Leak-safe Android implementation of scripts/v016_r4_player_history.py.
 *
 * A prediction-day snapshot is read-only. Outcomes can only enter the state via
 * commitDay(), and commitDay() advances lastDay, making another snapshot for that
 * same day illegal. The integration layer must therefore snapshot every race for
 * a calendar day before committing any result from that day.
 */
internal class ModelAPlayerHistory(
    private val state: State = State()
) {
    data class State(
        val stats: MutableMap<String, DoubleArray> = mutableMapOf(),
        val recent: MutableMap<String, Recent> = mutableMapOf(),
        var lastDay: Int = 0,
        var updateRaces: Int = 0
    )

    data class Recent(
        val days: MutableList<Int> = mutableListOf(),
        val cumulative: MutableList<IntArray> = mutableListOf(intArrayOf(0, 0, 0))
    )

    data class Flags(
        val fastExhibition: Boolean,
        val goodPreviewStart: Boolean,
        val courseChanged: Boolean
    )

    data class Snapshot(
        val history: DoubleArray,
        val reaction: DoubleArray,
        val flags: Flags
    ) {
        init {
            require(history.size == HISTORY_FEATURES)
            require(reaction.size == REACTION_FEATURES)
        }
    }

    data class OutcomeUpdate(
        val player: Int,
        val course: Int,
        val racerClass: Int,
        val exhibitionTime: Double,
        val previewStartTiming: Double,
        val win: Boolean,
        val top2: Boolean,
        val top3: Boolean,
        val flags: Flags
    ) {
        init {
            require(player > 0)
            require(course in 1..6)
            require(exhibitionTime.isFinite())
            require(previewStartTiming.isFinite())
            require(!win || top2)
            require(!top2 || top3)
        }
    }

    val lastDay: Int get() = state.lastDay
    val updateRaces: Int get() = state.updateRaces
    val registeredPlayers: Int get() = state.recent.size

    fun snapshot(
        player: Int,
        course: Int,
        racerClass: Int,
        exhibitionTime: Double,
        previewStartTiming: Double,
        courseChanged: Boolean,
        day: Int
    ): Snapshot {
        require(player > 0)
        require(course in 1..6)
        require(day > state.lastDay) { "History is not strictly earlier than prediction day" }
        require(exhibitionTime.isFinite())
        require(previewStartTiming.isFinite())

        val p = player.toString()
        val c = course.toString()
        val globalRate = rates(get("global"), doubleArrayOf(1.0 / 6.0, 1.0 / 3.0, 1.0 / 2.0))
        val courseRate = rates(get("c:$c"), globalRate)
        val classRate = rates(get("class:$racerClass"), globalRate)
        val playerStats = get("p:$p")
        val playerCourseStats = get("pc:$p:$c")
        val playerRate = rates(playerStats, average(courseRate, classRate))
        val playerCourseRate = rates(playerCourseStats, average(playerRate, courseRate))

        val globalMoments = moments(get("global"), doubleArrayOf(6.8, 0.15, 0.17, 0.08))
        val courseMoments = moments(get("c:$c"), globalMoments)
        val playerMoments = moments(playerStats, globalMoments)
        val playerCourseMoments = moments(playerCourseStats, average(playerMoments, courseMoments))

        val historyValues = ArrayList<Double>(HISTORY_FEATURES)
        historyValues += playerStats[0]
        playerRate.forEach(historyValues::add)
        historyValues += playerCourseStats[0]
        playerCourseRate.forEach(historyValues::add)
        playerMoments.forEach(historyValues::add)
        playerCourseMoments.forEach(historyValues::add)

        val recent = state.recent[p] ?: Recent()
        for (window in WINDOWS) {
            val left = lowerBound(recent.days, day - window)
            val n = recent.days.size - left
            val total = recent.cumulative.last()
            val before = recent.cumulative[left]
            val wins = DoubleArray(3) { index -> (total[index] - before[index]).toDouble() }
            val windowRates = DoubleArray(3) { index ->
                (wins[index] + PRIOR_COUNT * playerRate[index]) / (n + PRIOR_COUNT)
            }
            historyValues += n.toDouble()
            windowRates.forEach(historyValues::add)
        }

        val fast = get("fast:$p:$c")
        val good = get("good:$p:$c")
        val changed = get("changed:$p")
        val reactionValues = ArrayList<Double>(REACTION_FEATURES)
        reactionValues += exhibitionTime - playerMoments[0]
        reactionValues += (exhibitionTime - playerMoments[0]) / playerMoments[1]
        reactionValues += previewStartTiming - playerMoments[2]
        reactionValues += (previewStartTiming - playerMoments[2]) / playerMoments[3]
        reactionValues += exhibitionTime - playerCourseMoments[0]
        reactionValues += (exhibitionTime - playerCourseMoments[0]) / playerCourseMoments[1]
        reactionValues += previewStartTiming - playerCourseMoments[2]
        reactionValues += (previewStartTiming - playerCourseMoments[2]) / playerCourseMoments[3]
        reactionValues += fast[0]
        rates(fast, playerCourseRate).forEach(reactionValues::add)
        reactionValues += good[0]
        rates(good, playerCourseRate).forEach(reactionValues::add)
        reactionValues += changed[0]
        rates(changed, playerRate).forEach(reactionValues::add)

        require(historyValues.size == HISTORY_FEATURES)
        require(reactionValues.size == REACTION_FEATURES)
        val flags = Flags(
            fastExhibition = exhibitionTime < playerMoments[0],
            goodPreviewStart = previewStartTiming < playerMoments[2],
            courseChanged = courseChanged
        )
        return Snapshot(
            history = float32(historyValues),
            reaction = float32(reactionValues),
            flags = flags
        )
    }

    /** Commit all usable six-lane race outcomes for one day in one operation. */
    fun commitDay(day: Int, updates: List<OutcomeUpdate>) {
        require(day > state.lastDay) { "Nonchronological/duplicate day update" }
        require(updates.size % 6 == 0) { "Daily history updates must contain complete six-lane races" }

        for (update in updates) {
            val p = update.player.toString()
            val c = update.course.toString()
            val keys = mutableListOf(
                "global",
                "c:$c",
                "class:${update.racerClass}",
                "p:$p",
                "pc:$p:$c"
            )
            if (update.flags.fastExhibition) keys += "fast:$p:$c"
            if (update.flags.goodPreviewStart) keys += "good:$p:$c"
            if (update.flags.courseChanged) keys += "changed:$p"

            val y = intArrayOf(
                if (update.win) 1 else 0,
                if (update.top2) 1 else 0,
                if (update.top3) 1 else 0
            )
            for (key in keys) {
                add(
                    state.stats.getOrPut(key, ::emptyStats),
                    y,
                    update.exhibitionTime,
                    update.previewStartTiming
                )
            }

            val recent = state.recent.getOrPut(p, ::Recent)
            recent.days += day
            val previous = recent.cumulative.last()
            recent.cumulative += IntArray(3) { index -> previous[index] + y[index] }
        }
        state.lastDay = day
        state.updateRaces += updates.size / 6
    }

    fun exportState(): State = state

    private fun get(key: String): DoubleArray = state.stats[key] ?: emptyStats()

    private fun rates(stats: DoubleArray, prior: DoubleArray): DoubleArray {
        require(prior.size == 3)
        return DoubleArray(3) { index ->
            (stats[index + 1] + PRIOR_COUNT * prior[index]) / (stats[0] + PRIOR_COUNT)
        }
    }

    private fun moments(stats: DoubleArray, prior: DoubleArray): DoubleArray {
        require(prior.size == 4)
        val n = stats[0]
        val out = DoubleArray(4)
        var target = 0
        for (offset in intArrayOf(4, 6)) {
            val priorMean = prior[target]
            val priorSd = prior[target + 1]
            val mean = (stats[offset] + PRIOR_COUNT * priorMean) / (n + PRIOR_COUNT)
            val variance =
                (stats[offset + 1] + PRIOR_COUNT * (priorSd * priorSd + priorMean * priorMean)) /
                    (n + PRIOR_COUNT) - mean * mean
            out[target] = mean
            out[target + 1] = max(sqrt(max(variance, 0.0)), MIN_SD)
            target += 2
        }
        return out
    }

    private fun add(stats: DoubleArray, y: IntArray, exhibitionTime: Double, previewStartTiming: Double) {
        stats[0] += 1.0
        for (index in 0..2) stats[index + 1] += y[index].toDouble()
        stats[4] += exhibitionTime
        stats[5] += exhibitionTime * exhibitionTime
        stats[6] += previewStartTiming
        stats[7] += previewStartTiming * previewStartTiming
    }

    private fun average(a: DoubleArray, b: DoubleArray): DoubleArray {
        require(a.size == b.size)
        return DoubleArray(a.size) { index -> (a[index] + b[index]) / 2.0 }
    }

    private fun lowerBound(values: List<Int>, target: Int): Int {
        var low = 0
        var high = values.size
        while (low < high) {
            val mid = (low + high) ushr 1
            if (values[mid] < target) low = mid + 1 else high = mid
        }
        return low
    }

    private fun float32(values: List<Double>): DoubleArray =
        DoubleArray(values.size) { index -> values[index].toFloat().toDouble() }

    companion object {
        const val HISTORY_FEATURES = 32
        const val REACTION_FEATURES = 20
        private const val PRIOR_COUNT = 20.0
        private const val MIN_SD = 0.02
        private val WINDOWS = intArrayOf(30, 60, 90, 180)

        private fun emptyStats(): DoubleArray = DoubleArray(8)
    }
}
