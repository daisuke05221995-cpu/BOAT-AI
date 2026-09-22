package jp.boatai.app

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import org.jsoup.Jsoup
import org.jsoup.nodes.Document
import org.jsoup.nodes.Element
import java.net.HttpURLConnection
import java.net.URL
import java.text.Normalizer
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
                .userAgent(OFFICIAL_USER_AGENT)
                .referrer("https://www.boatrace.jp/")
                .header("Accept-Language", "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.5")
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
                val fetched = fetchOfficialPageWithSession(url)
                val odds = parseTrifectaOdds(fetched.document, combinations)
                if (odds.isEmpty()) error("オッズ表の解析結果が空です")
                fetched to odds
            }.onSuccess { (fetched, odds) ->
                diagnostics += DataSourceDiagnostic(
                    source,
                    DiagnosticStatus.OK,
                    "${odds.size}/${combinations.size}点取得 / ${fetched.attempts}回目 / ${System.currentTimeMillis() - startedAt}ms"
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

    private data class SessionFetch(val document: Document, val attempts: Int)

    private fun fetchOfficialPageWithSession(url: String): SessionFetch {
        var lastError: Throwable? = null
        repeat(3) { index ->
            val attempt = index + 1
            val session = Jsoup.newSession()
                .userAgent(OFFICIAL_USER_AGENT)
                .header("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8")
                .header("Accept-Language", "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.5")
                .timeout(20_000)
                .maxBodySize(0)
            try {
                // 公式トップを先に開き、同一セッションのCookieを保持してからレースページへ進む。
                session.newRequest("https://www.boatrace.jp/")
                    .header("Cache-Control", "no-cache")
                    .get()
                val document = session.newRequest(url)
                    .referrer("https://www.boatrace.jp/")
                    .header("Cache-Control", "no-cache, no-store, max-age=0")
                    .header("Pragma", "no-cache")
                    .get()
                if (document.body() == null || document.text().isBlank()) {
                    error("公式ページの応答が空です")
                }
                return SessionFetch(document, attempt)
            } catch (error: Throwable) {
                lastError = error
                if (attempt < 3) Thread.sleep(300L * attempt)
            }
        }
        throw IllegalStateException("公式ページ取得に3回失敗しました: ${lastError?.message ?: "不明なエラー"}", lastError)
    }

    internal fun parseTrifectaOdds(doc: Document, combinations: List<String>): Map<String, Double> {
        val wanted = combinations.distinct().toSet()
        if (wanted.isEmpty()) return emptyMap()

        // 現行公式PC版の3連単表は rowspan で2着艇を省略する構造。
        // 行を論理セルへ展開してから「1着・2着・3着・オッズ」を復元する。
        val officialTable = doc.select(".table1 table").lastOrNull { it.select(".oddsPoint").isNotEmpty() }
            ?: doc.select("table").lastOrNull { it.select(".oddsPoint").isNotEmpty() }
        if (officialTable != null) {
            val firstLanes = officialTable.select("thead th")
                .mapNotNull { parseLane(it.text()) }
                .distinct()
                .take(6)
            if (firstLanes.isNotEmpty()) {
                val expandedRows = expandRows(officialTable.select("tbody tr"))
                val parsed = buildMap {
                    expandedRows.forEach { row ->
                        if (row.size < firstLanes.size * 3) return@forEach
                        firstLanes.forEachIndexed { index, first ->
                            val offset = index * 3
                            val second = parseLane(row.getOrNull(offset).orEmpty()) ?: return@forEachIndexed
                            val third = parseLane(row.getOrNull(offset + 1).orEmpty()) ?: return@forEachIndexed
                            val odds = parseOdds(row.getOrNull(offset + 2).orEmpty()) ?: return@forEachIndexed
                            if (first == second || third == first || third == second) return@forEachIndexed
                            val combination = "$first-$second-$third"
                            if (combination in wanted) put(combination, odds)
                        }
                    }
                }
                if (parsed.isNotEmpty()) return parsed
            }
        }

        val targets = combinations.distinct().mapNotNull { combination ->
            val parts = combination.split("-").mapNotNull(String::toIntOrNull)
            if (parts.size != 3) null else TrifectaOddsLocator.locate(parts[0], parts[1], parts[2])
                ?.let { Triple(combination, it.row, it.column) }
        }

        // スマホ版や将来のDOM変更時は固定divではなく全tableを走査し、
        // 欲しい買い目を最も多く取得できた表を採用する。
        return doc.select("table").map { table ->
            val rows = table.select("tbody tr").ifEmpty { table.select("tr") }
            buildMap {
                targets.forEach { (combination, rowNumber, columnNumber) ->
                    val cells = rows.getOrNull(rowNumber - 1)?.select("td").orEmpty()
                    val raw = cells.getOrNull(columnNumber - 1)?.text().orEmpty()
                    parseOdds(raw)?.let { put(combination, it) }
                }
            }
        }.maxByOrNull { it.size }.orEmpty()
    }

    private data class SpanCell(val text: String, var rowsLeft: Int)

    private fun expandRows(rows: List<Element>): List<List<String>> {
        val spans = mutableMapOf<Int, SpanCell>()
        return rows.map { row ->
            val expanded = mutableListOf<String>()
            var column = 0

            fun appendActiveSpans() {
                while (true) {
                    val span = spans[column] ?: break
                    expanded += span.text
                    span.rowsLeft -= 1
                    if (span.rowsLeft <= 0) spans.remove(column)
                    column += 1
                }
            }

            row.children()
                .filter { it.tagName() == "td" || it.tagName() == "th" }
                .forEach { cell ->
                    appendActiveSpans()
                    val text = cell.text().trim()
                    val rowSpan = cell.attr("rowspan").toIntOrNull()?.coerceAtLeast(1) ?: 1
                    val colSpan = cell.attr("colspan").toIntOrNull()?.coerceAtLeast(1) ?: 1
                    repeat(colSpan) {
                        expanded += text
                        if (rowSpan > 1) spans[column] = SpanCell(text, rowSpan - 1)
                        column += 1
                    }
                }
            appendActiveSpans()
            expanded
        }
    }

    private fun parseLane(raw: String): Int? {
        val normalized = Normalizer.normalize(raw, Normalizer.Form.NFKC)
        return Regex("[1-6]").find(normalized)?.value?.toIntOrNull()
    }

    private fun parseOdds(raw: String): Double? {
        val normalized = Normalizer.normalize(raw, Normalizer.Form.NFKC)
            .replace(" ", "")
            .replace(",", "")
        return Regex("""\d{1,5}(?:\.\d+)?""")
            .find(normalized)?.value?.toDoubleOrNull()
            ?.takeIf { it > 0.0 }
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

    companion object {
        private const val OFFICIAL_USER_AGENT =
            "Mozilla/5.0 (Linux; Android 16; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36"
    }
}
