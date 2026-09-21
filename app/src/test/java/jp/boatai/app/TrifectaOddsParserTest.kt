package jp.boatai.app

import org.jsoup.Jsoup
import org.junit.Assert.assertEquals
import org.junit.Test

class TrifectaOddsParserTest {
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
