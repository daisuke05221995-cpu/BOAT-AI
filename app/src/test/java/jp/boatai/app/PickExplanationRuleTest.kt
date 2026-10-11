package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class PickExplanationRuleTest {
    @Test
    fun expectedReturnIsProbabilityTimesOdds() {
        assertEquals(
            120.0,
            PickExplanationRule.expectedReturnRate(0.10, 12.0)!!,
            0.0001
        )
    }

    @Test
    fun missingProbabilityCannotInventExpectedReturn() {
        assertNull(PickExplanationRule.expectedReturnRate(null, 12.0))
    }

    @Test
    fun allocationLabelsExplain1800_900_200_100Pattern() {
        assertEquals("主力配分", PickExplanationRule.allocationLabel(1800, 1800))
        assertEquals("厚め配分", PickExplanationRule.allocationLabel(900, 1800))
        assertEquals("抑え配分", PickExplanationRule.allocationLabel(200, 1800))
        assertEquals("抑え配分", PickExplanationRule.allocationLabel(100, 1800))
    }
}
