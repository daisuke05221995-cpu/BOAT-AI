package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/** Release gate: forecast is validated; live purchase recommendation is enabled without claiming historical ROI validation. */
class ModelAProductionReleaseGateTest {
    @Test
    fun forecastIsQualifiedAndLivePurchaseRecommendationIsEnabledWithoutHistoricalRoiClaim() {
        assertTrue(AverageRoiReferenceStrategy.FORECAST_ENABLED)
        assertTrue(AverageRoiReferenceStrategy.MODEL_A_FORECAST_RELEASE_QUALIFIED)
        assertTrue(AverageRoiReferenceStrategy.PURCHASE_RECOMMENDATION_ENABLED)
        assertFalse(AverageRoiReferenceStrategy.RELEASE_QUALIFIED)
        assertFalse(AverageRoiReferenceStrategy.HISTORICAL_ROI_APPLIES_TO_CURRENT)
    }
}
