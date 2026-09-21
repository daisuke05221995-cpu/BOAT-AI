package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class BoatRaceRepository {
    private val compact = DateTimeFormatter.ofPattern("yyyyMMdd")

    suspend fun loadDate(date: LocalDate): List<RaceData> = withContext(Dispatchers.IO) {
        val day = date.format(compact)
        val url = "https://boatraceopenapi.github.io/api/v1/${date.year}/$day.json"
        val json = httpGet(url)
        BoatRaceJsonParser.parse(json)
    }

    suspend fun loadOfficialTrifectaOdds(
        race: RaceData,
        combinations: List<String>
    ): Map<String, Double> = withContext(Dispatchers.IO) {
        if (combinations.isEmpty()) return@withContext emptyMap()
        val day = race.date.replace("-", "")
        val jcd = Venues.code(race.stadiumNumber)
        val url = "https://www.boatrace.jp/owpc/pc/race/odds3t?hd=$day&jcd=$jcd&rno=${race.raceNumber}"

        val doc = Jsoup.connect(url)
            .userAgent("Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36 BOAT-AI/0.2")
            .referrer("https://www.boatrace.jp/")
            .timeout(15_000)
            .get()

        val levelProbe = "//body/main/div/div/div/div[2]/div[3]/ul/li"
        val baseLevel = if (doc.selectXpath(levelProbe).isNotEmpty()) 1 else 0
        val divIndex = baseLevel + 7

        buildMap {
            for (combination in combinations.distinct()) {
                val parts = combination.split("-").mapNotNull { it.toIntOrNull() }
                if (parts.size != 3 || parts.distinct().size != 3 || parts.any { it !in 1..6 }) continue
                val (first, second, third) = parts
                val cell = TrifectaOddsLocator.locate(first, second, third) ?: continue
                val xpath = "//body/main/div/div/div/div[2]/div[$divIndex]/table/tbody/tr[${cell.row}]/td[${cell.column}]"
                val text = doc.selectXpath(xpath).firstOrNull()?.text()?.trim().orEmpty()
                val odds = text.replace(",", "").toDoubleOrNull()
                if (odds != null && odds > 0) put(combination, odds)
            }
        }
    }

    private fun httpGet(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 15_000
            connection.readTimeout = 20_000
            connection.setRequestProperty("User-Agent", "BOAT-AI/0.2 Android")
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Cache-Control", "no-cache")
            connection.connect()
            if (connection.responseCode !in 200..299) {
                throw IllegalStateException("データ取得失敗 HTTP ${connection.responseCode}")
            }
            connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }
}
