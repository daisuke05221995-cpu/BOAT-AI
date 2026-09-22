package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.format.DateTimeFormatter

class BoatRaceRepository : RaceDataProvider, OddsProvider {
    private val compact = DateTimeFormatter.ofPattern("yyyyMMdd")

    suspend fun loadDate(date: LocalDate): List<RaceData> = loadDateDetailed(date).races

    override suspend fun loadDateDetailed(date: LocalDate): DateLoadResult = withContext(Dispatchers.IO) {
        val day = date.format(compact)
        val url = "https://boatraceopenapi.github.io/api/v1/${date.year}/$day.json?ts=${System.currentTimeMillis()}"
        val startedAt = System.currentTimeMillis()
        val json = httpGet(url)
        val parsed = BoatRaceJsonParser.parse(json)
        val supplement = supplementMissingResults(parsed, date)
        val previewCount = supplement.races.count { it.preview != null }
        val diagnostics = buildList {
            add(
                DataSourceDiagnostic(
                    source = "開催・出走データ",
                    status = if (parsed.isNotEmpty()) DiagnosticStatus.OK else DiagnosticStatus.WARNING,
                    detail = "公開データ ${parsed.size}レース / ${System.currentTimeMillis() - startedAt}ms"
                )
            )
            add(
                DataSourceDiagnostic(
                    source = "展示・気象データ",
                    status = if (previewCount > 0 || date.isBefore(LocalDate.now())) DiagnosticStatus.OK else DiagnosticStatus.WAITING,
                    detail = "展示・気象あり $previewCount/${supplement.races.size}レース"
                )
            )
            add(
                DataSourceDiagnostic(
                    source = "公式結果補完",
                    status = if (supplement.failed == 0) DiagnosticStatus.OK else DiagnosticStatus.WARNING,
                    detail = "補完 ${supplement.completed}/${supplement.attempted}件" +
                        if (supplement.failed > 0) " / 失敗 ${supplement.failed}件" else ""
                )
            )
        }
        DateLoadResult(supplement.races, diagnostics)
    }

    private data class ResultSupplement(
        val races: List<RaceData>,
        val attempted: Int,
        val completed: Int,
        val failed: Int
    )

    private suspend fun supplementMissingResults(races: List<RaceData>, date: LocalDate): ResultSupplement {
        val now = java.time.LocalDateTime.now(java.time.ZoneId.of("Asia/Tokyo"))
        val candidates = races.filter { race ->
            !race.hasResult && race.isDataComplete && !race.isPurchasable(now) &&
                !date.isAfter(now.toLocalDate())
        }.take(24)
        if (candidates.isEmpty()) return ResultSupplement(races, 0, 0, 0)

        val supplements = coroutineScope {
            candidates.chunked(4).flatMap { group ->
                group.map { race -> async(Dispatchers.IO) { race.id to loadOfficialResult(race) } }.awaitAll()
            }
        }.mapNotNull { (id, result) -> result?.let { id to it } }.toMap()
        val merged = races.map { race -> supplements[race.id]?.let { race.copy(result = it) } ?: race }
        return ResultSupplement(
            races = merged,
            attempted = candidates.size,
            completed = supplements.size,
            failed = candidates.size - supplements.size
        )
    }

    private fun loadOfficialResult(race: RaceData): RaceResultData? {
        val day = race.date.replace("-", "").take(8)
        val url = "https://www.boatrace.jp/owpc/pc/race/raceresult?hd=$day&jcd=${Venues.code(race.stadiumNumber)}&rno=${race.raceNumber}&_=${System.currentTimeMillis()}"
        return runCatching {
            val doc = Jsoup.connect(url)
                .userAgent("Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36 BOAT-AI/0.6")
                .referrer("https://www.boatrace.jp/")
                .header("Cache-Control", "no-cache, no-store, max-age=0")
                .timeout(12_000)
                .get()
            val payoffRow = doc.select("table.table1 tbody tr").firstOrNull { row ->
                row.select("span.numberSet1_number").size == 3 && row.select("td").any { it.text().contains("¥") }
            } ?: return@runCatching null
            val combination = payoffRow.select("span.numberSet1_number")
                .map { it.text().trim() }.joinToString("-")
            val payout = payoffRow.select("td").firstOrNull { it.text().contains("¥") }
                ?.text()?.replace(",", "")?.let { Regex("""\d+""").find(it)?.value?.toIntOrNull() }
            if (combination.count { it == '-' } != 2 || payout == null) null
            else RaceResultData(combination, payout, null)
        }.getOrNull()
    }

    suspend fun loadOfficialTrifectaOdds(
        race: RaceData,
        combinations: List<String>
    ): Map<String, Double> = loadOfficialTrifectaOddsDetailed(race, combinations).odds

    override suspend fun loadOfficialTrifectaOddsDetailed(
        race: RaceData,
        combinations: List<String>
    ): OddsFetchResult = withContext(Dispatchers.IO) {
        if (combinations.isEmpty()) return@withContext OddsFetchResult(emptyMap(), "未取得", emptyList())
        val day = race.date.replace("-", "")
        val jcd = Venues.code(race.stadiumNumber)
        val suffix = "hd=$day&jcd=$jcd&rno=${race.raceNumber}&_=${System.currentTimeMillis()}"
        val sources = listOf(
            "公式PC版" to "https://www.boatrace.jp/owpc/pc/race/odds3t?$suffix",
            "公式スマホ版" to "https://www.boatrace.jp/owsp/sp/race/odds3t?$suffix"
        )
        var lastError: Throwable? = null
        val diagnostics = mutableListOf<DataSourceDiagnostic>()
        for ((source, url) in sources) {
            val startedAt = System.currentTimeMillis()
            runCatching {
                val doc = Jsoup.connect(url)
                    .userAgent("Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/140 Mobile Safari/537.36 BOAT-AI/0.7")
                    .referrer("https://www.boatrace.jp/")
                    .header("Cache-Control", "no-cache, no-store, max-age=0")
                    .header("Pragma", "no-cache")
                    .timeout(15_000)
                    .get()
                parseTrifectaOdds(doc, combinations).takeIf { it.isNotEmpty() }
                    ?: error("オッズ表の解析結果が空です")
            }.onSuccess { odds ->
                diagnostics += DataSourceDiagnostic(
                    source,
                    DiagnosticStatus.OK,
                    "${odds.size}/${combinations.size}点取得 / ${System.currentTimeMillis() - startedAt}ms"
                )
                return@withContext OddsFetchResult(odds, source, diagnostics)
            }.onFailure { error ->
                lastError = error
                diagnostics += DataSourceDiagnostic(
                    source,
                    DiagnosticStatus.WARNING,
                    error.message ?: "取得失敗"
                )
            }
        }
        val detail = diagnostics.joinToString(" / ") { "${it.source}: ${it.detail}" }
        throw IllegalStateException("オッズ取得失敗（$detail）", lastError)
    }

    internal fun parseTrifectaOdds(doc: Document, combinations: List<String>): Map<String, Double> {
        val officialTable = doc.select("table.table1").firstOrNull {
            it.select("tbody tr td.oddsPoint").size >= 100
        }
        if (officialTable != null) {
            val oddsCells = officialTable.select("tbody tr td.oddsPoint")
            val secondNumbers = officialTable.select("tbody tr td[rowspan=4]")
                .chunked(6)
                .flatMap { group -> List(4) { group.mapNotNull { it.text().trim().toIntOrNull() } }.flatten() }
            val thirdNumbers = officialTable.select("tbody tr td[class^=is-boatColor]")
                .mapNotNull { it.text().trim().toIntOrNull() }
            if (secondNumbers.size >= oddsCells.size && thirdNumbers.size >= oddsCells.size) {
                val wanted = combinations.toSet()
                return buildMap {
                    oddsCells.forEachIndexed { index, cell ->
                        val combination = "${index % 6 + 1}-${secondNumbers[index]}-${thirdNumbers[index]}"
                        if (combination in wanted) parseOdds(cell.text())?.let { put(combination, it) }
                    }
                }
            }
        }

        val targets = combinations.distinct().mapNotNull { combination ->
            val parts = combination.split("-").mapNotNull(String::toIntOrNull)
            if (parts.size != 3) null else TrifectaOddsLocator.locate(parts[0], parts[1], parts[2])
                ?.let { Triple(combination, it.row, it.column) }
        }

        // 公式サイト内のdiv階層は変更されやすい。全tableを調べ、最も多く正しい
        // オッズを読めた表を採用することで固定XPathへの依存をなくす。
        return doc.select("table").map { table ->
            val rows = table.select("tbody tr").ifEmpty { table.select("tr") }
            buildMap {
                targets.forEach { (combination, rowNumber, columnNumber) ->
                    // 見出しthは公式表の列番号に含まれないためtdだけを数える。
                    val cells = rows.getOrNull(rowNumber - 1)?.select("td").orEmpty()
                    val raw = cells.getOrNull(columnNumber - 1)?.text().orEmpty()
                    parseOdds(raw)?.let { put(combination, it) }
                }
            }
        }.maxByOrNull { it.size }.orEmpty()
    }

    private fun parseOdds(raw: String): Double? = Regex("""\d{1,5}(?:[,.]\d+)?""")
        .find(raw.replace(" ", ""))?.value?.replace(",", "")?.toDoubleOrNull()
        ?.takeIf { it > 0.0 }

    private fun httpGet(url: String): String {
        val connection = URL(url).openConnection() as HttpURLConnection
        return try {
            connection.requestMethod = "GET"
            connection.connectTimeout = 15_000
            connection.readTimeout = 20_000
            connection.setRequestProperty("User-Agent", "BOAT-AI/0.2 Android")
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Cache-Control", "no-cache")
            connection.useCaches = false
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
