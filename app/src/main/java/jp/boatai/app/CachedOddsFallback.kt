package jp.boatai.app

import java.time.Duration
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.OffsetDateTime
import java.time.ZoneId
import kotlin.math.round

internal data class CachedOddsSnapshot(
    val observedOdds: Map<String, Double>,
    val estimatedOdds: Map<String, Double>,
    val fetchedAt: Long,
    val minutesBeforeClose: Double
)

internal object StartOddsEstimator {
    private val TOKYO: ZoneId = ZoneId.of("Asia/Tokyo")

    internal fun baseFactor(popularityRank: Int): Double = when {
        popularityRank <= 1 -> 0.92
        popularityRank <= 3 -> 0.86
        popularityRank <= 6 -> 0.87
        popularityRank <= 12 -> 0.88
        else -> 0.96
    }

    fun estimate(
        observedOdds: Map<String, Double>,
        minutesBeforeClose: Double
    ): Map<String, Double> {
        if (observedOdds.isEmpty()) return emptyMap()
        val ordered = observedOdds.entries
            .filter { it.value.isFinite() && it.value > 0.0 }
            .sortedWith(compareBy<Map.Entry<String, Double>> { it.value }.thenBy { it.key })
        val ranks = ordered.mapIndexed { index, entry -> entry.key to (index + 1) }.toMap()
        val timeWeight = (minutesBeforeClose / 8.0).coerceIn(0.0, 1.0)
        return observedOdds.mapValues { (combo, odds) ->
            val rank = ranks[combo] ?: 120
            val base = baseFactor(rank)
            val effectiveFactor = 1.0 + (base - 1.0) * timeWeight
            round((odds * effectiveFactor).coerceAtLeast(1.0) * 10.0) / 10.0
        }
    }

    fun minutesBeforeClose(race: RaceData, fetchedAt: Long): Double? {
        val date = runCatching { LocalDate.parse(race.date.take(10)) }.getOrNull() ?: return null
        val match = Regex("""(\d{1,2}):(\d{2})""").findAll(race.closedAt).lastOrNull() ?: return null
        val time = runCatching {
            LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt())
        }.getOrNull() ?: return null
        val close = LocalDateTime.of(date, time).atZone(TOKYO).toInstant()
        val fetched = java.time.Instant.ofEpochMilli(fetchedAt)
        return Duration.between(fetched, close).toMillis() / 60_000.0
    }
}

internal object BoatraceCsvOddsFallback {
    private const val BASE =
        "https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/main/data/previews/od3"

    fun urlFor(race: RaceData): String {
        val date = LocalDate.parse(race.date.take(10))
        return "$BASE/${date.year}/${"%02d".format(date.monthValue)}/${"%02d".format(date.dayOfMonth)}.csv"
    }

    fun parseRaceSnapshot(
        csv: String,
        race: RaceData
    ): CachedOddsSnapshot? {
        val lines = csv.lineSequence().filter { it.isNotBlank() }.toList()
        if (lines.size < 2) return null
        val headers = lines.first().split(',')
        val code = race.date.replace("-", "").take(8) +
            "%02d".format(race.stadiumNumber) +
            "%02d".format(race.raceNumber)

        val row = lines.drop(1).firstOrNull { line ->
            line.substringBefore(',').trim() == code
        } ?: return null
        val values = row.split(',')
        if (values.size < headers.size) return null

        val byHeader = headers.indices.associate { index ->
            headers[index] to values.getOrElse(index) { "" }
        }
        val fetchedAt = byHeader["取得日時"]
            ?.takeIf { it.isNotBlank() }
            ?.let { raw -> runCatching { OffsetDateTime.parse(raw).toInstant().toEpochMilli() }.getOrNull() }
            ?: return null

        val observed = buildMap {
            headers.forEachIndexed { index, header ->
                if (!header.startsWith("3連単_")) return@forEachIndexed
                val odds = values.getOrNull(index)?.toDoubleOrNull()?.takeIf { it.isFinite() && it > 0.0 }
                    ?: return@forEachIndexed
                put(header.removePrefix("3連単_"), odds)
            }
        }
        if (observed.size < 120) return null

        val minutes = StartOddsEstimator.minutesBeforeClose(race, fetchedAt) ?: return null
        if (minutes < -2.0 || minutes > 15.0) return null
        val estimated = StartOddsEstimator.estimate(observed, minutes.coerceAtLeast(0.0))
        return CachedOddsSnapshot(
            observedOdds = observed,
            estimatedOdds = estimated,
            fetchedAt = fetchedAt,
            minutesBeforeClose = minutes
        )
    }
}
