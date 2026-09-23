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
    fun parsesAll120TrifectaOddsFromOfficialRowspanLayout() {
        val combinationsByFirst = (1..6).associateWith { first ->
            buildList {
                for (second in 1..6) {
                    if (second == first) continue
                    for (third in 1..6) {
                        if (third == first || third == second) continue
                        add(Triple(first, second, third))
                    }
                }
            }
        }
        val expected = linkedMapOf<String, Double>()
        val bodyRows = buildString {
            repeat(20) { rowIndex ->
                append("<tr>")
                for (first in 1..6) {
                    val (_, second, third) = combinationsByFirst.getValue(first)[rowIndex]
                    val combination = "$first-$second-$third"
                    val odds = first * 100.0 + second * 10.0 + third + rowIndex / 100.0
                    expected[combination] = odds
                    if (rowIndex % 4 == 0) {
                        append("<td rowspan=\"4\">$second</td>")
                    }
                    append("<td>$third</td><td class=\"oddsPoint\">$odds</td>")
                }
                append("</tr>")
            }
        }
        val headers = (1..6).joinToString("") { first ->
            "<th class=\"is-boatColor$first\">$first</th><th colspan=\"2\">${first}号艇</th>"
        }
        val html = "<html><body><div class=\"table1\"><table><thead><tr>$headers</tr></thead><tbody>$bodyRows</tbody></table></div></body></html>"
        val requested = expected.keys.toList()

        val actual = BoatRaceRepository().parseTrifectaOdds(Jsoup.parse(html), requested)

        assertEquals(120, requested.size)
        assertEquals(120, actual.size)
        assertEquals(expected.keys, actual.keys)
        expected.forEach { (combination, odds) ->
            assertEquals(odds, actual.getValue(combination), 0.000001)
        }
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
