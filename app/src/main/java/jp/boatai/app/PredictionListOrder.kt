package jp.boatai.app

import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

object PredictionListOrder {
    fun byDeadline(
        races: List<RaceData>,
        now: LocalDateTime = LocalDateTime.now(ZoneId.of("Asia/Tokyo"))
    ): List<RaceData> = races
        .asSequence()
        .filter { it.isPurchasable(now) }
        .sortedWith(
            compareBy<RaceData> { closeMinutes(it.closedAt) ?: Int.MAX_VALUE }
                .thenBy { it.stadiumNumber }
                .thenBy { it.raceNumber }
        )
        .toList()

    internal fun closeMinutes(raw: String): Int? {
        val match = Regex("""(\d{1,2}):(\d{2})""").findAll(raw).lastOrNull() ?: return null
        val time = runCatching {
            LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt())
        }.getOrNull() ?: return null
        return time.hour * 60 + time.minute
    }
}
