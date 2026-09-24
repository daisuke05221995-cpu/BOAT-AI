package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Final Android release gate: forecast promotion must never imply purchase promotion. */
class ModelAProductionReleaseGateTest {
    @Test
    fun forecastIsQualifiedButAutomaticPurchaseRemainsDisabled() {
        assertTrue(AverageRoiReferenceStrategy.FORECAST_ENABLED)
        assertTrue(AverageRoiReferenceStrategy.MODEL_A_FORECAST_RELEASE_QUALIFIED)
        assertFalse(AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
        assertFalse(AverageRoiReferenceStrategy.HISTORICAL_ROI_APPLIES_TO_CURRENT)
    }
}
