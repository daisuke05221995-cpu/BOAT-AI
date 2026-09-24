package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Test

class ModelARecentVirtualPolicyTest {
    @Test
    fun retrospectiveFeedIsLimitedToThirtyDaysAndSeparatedByStrategy() {
        assertEquals(30, ModelARecentVirtualRepository.WINDOW_DAYS)
        assertEquals("model-a-retro-flex-v2", ModelARecentVirtualRepository.STRATEGY_ID)
    }
}
