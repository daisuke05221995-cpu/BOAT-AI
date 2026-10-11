package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Test

class BetLabelRuleTest {
    @Test
    fun firstPickBelowLongshotThresholdIsFavorite() {
        assertEquals(BetTier.MAIN, BetLabelRule.classify(index = 0, odds = 12.3))
    }

    @Test
    fun otherPickBelowLongshotThresholdIsChallenger() {
        assertEquals(BetTier.MID, BetLabelRule.classify(index = 1, odds = 45.0))
    }

    @Test
    fun overHundredOddsIsLongshot() {
        assertEquals(BetTier.LONG, BetLabelRule.classify(index = 2, odds = 100.1))
    }

    @Test
    fun exactlyHundredOddsIsNotLongshotBecauseRuleSaysOver() {
        assertEquals(BetTier.MID, BetLabelRule.classify(index = 2, odds = 100.0))
    }

    @Test
    fun overTwoHundredOddsIsBigLongshot() {
        assertEquals(BetTier.VERY_LONG, BetLabelRule.classify(index = 3, odds = 200.1))
    }

    @Test
    fun exactlyTwoHundredOddsIsLongshotBecauseBigLongshotRequiresOver() {
        assertEquals(BetTier.LONG, BetLabelRule.classify(index = 3, odds = 200.0))
    }
}
