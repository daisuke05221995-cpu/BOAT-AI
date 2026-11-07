package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class PurchaseForegroundStartPolicyTest {
    private val official = BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE

    @Test fun startsOnlyOnActualForegroundOfficialWindowWithinSwitchInterval() {
        assertTrue(PurchaseForegroundStartPolicy.canStart(official, official, 1_000L, 10_000L))
        assertFalse(PurchaseForegroundStartPolicy.canStart("jp.boatai.app", official, 1_000L, 10_000L))
        assertFalse(PurchaseForegroundStartPolicy.canStart(official, "jp.boatai.app", 1_000L, 10_000L))
        assertFalse(PurchaseForegroundStartPolicy.canStart(official, null, 1_000L, 10_000L))
        assertFalse(PurchaseForegroundStartPolicy.canStart(official, official, 1_000L, 61_001L))
        assertFalse(PurchaseForegroundStartPolicy.canStart(official, official, 2_000L, 1_000L))
    }
}
