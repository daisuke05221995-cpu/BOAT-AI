package jp.boatai.app

/** Maps a 3連単 combination to the BOAT RACE official odds table cell. */
object TrifectaOddsLocator {
    data class Cell(val row: Int, val column: Int)

    fun locate(first: Int, second: Int, third: Int): Cell? {
        val values = listOf(first, second, third)
        if (values.any { it !in 1..6 } || values.distinct().size != 3) return null

        val secondChoices = (1..6).filter { it != first }
        val secondIndex = secondChoices.indexOf(second)
        val thirdChoices = (1..6).filter { it != first && it != second }
        val thirdIndex = thirdChoices.indexOf(third)
        if (secondIndex < 0 || thirdIndex < 0) return null

        val row = secondIndex * 4 + thirdIndex + 1
        val column = if (thirdIndex == 0) first * 3 else first * 2
        return Cell(row, column)
    }
}
