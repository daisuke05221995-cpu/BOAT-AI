package jp.boatai.app

import org.jsoup.Jsoup
import org.junit.Assert.assertEquals
import org.junit.Test

class TrifectaOddsParserTest {
    @Test
    fun parsesCurrentOfficialRowspanLayout() {
        val html = """
            <html><body><div class="table1"><table>
              <thead><tr>
                <th class="is-boatColor1">1</th><th colspan="2">1号艇</th>
                <th class="is-boatColor2">2</th><th colspan="2">2号艇</th>
              </tr></thead>
              <tbody>
                <tr>
                  <td rowspan="2">2</td><td>3</td><td class="oddsPoint">21.3</td>
                  <td rowspan="2">1</td><td>3</td><td class="oddsPoint">67.8</td>
                </tr>
                <tr>
                  <td>4</td><td class="oddsPoint">28.4</td>
                  <td>4</td><td class="oddsPoint">211.4</td>
                </tr>
              </tbody>
            </table></div></body></html>
        """.trimIndent()
        val requested = listOf("1-2-3", "1-2-4", "2-1-3", "2-1-4")

        val actual = BoatRaceRepository().parseTrifectaOdds(Jsoup.parse(html), requested)

        assertEquals(
            mapOf(
                "1-2-3" to 21.3,
                "1-2-4" to 28.4,
                "2-1-3" to 67.8,
                "2-1-4" to 211.4
            ),
            actual
        )
    }

    @Test
    fun findsOddsTableWithoutDependingOnPageDivStructure() {
        val cells = Array(20) { Array(18) { "-" } }
        val requested = mapOf("1-2-3" to 12.4, "3-1-6" to 48.7, "6-5-4" to 101.2)
        requested.forEach { (combination, odds) ->
            val (first, second, third) = combination.split("-").map(String::toInt)
            val cell = requireNotNull(TrifectaOddsLocator.locate(first, second, third))
            cells[cell.row - 1][cell.column - 1] = odds.toString()
        }
        val table = cells.joinToString("", "<table><tbody>", "</tbody></table>") { row ->
            row.joinToString("", "<tr>", "</tr>") { "<td>$it</td>" }
        }
        val html = "<html><body><main><div>layout changed</div>$table</main></body></html>"

        val actual = BoatRaceRepository().parseTrifectaOdds(Jsoup.parse(html), requested.keys.toList())

        assertEquals(requested, actual)
    }
}
