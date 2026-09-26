package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AppUpdateManagerTest {
    @Test
    fun detectsNewerSemanticVersion() {
        assertTrue(VersionComparator.isNewer("0.16.7", "0.16.6"))
        assertTrue(VersionComparator.isNewer("v1.0.0", "0.99.9"))
        assertTrue(VersionComparator.isNewer("1.2.10", "1.2.9"))
    }

    @Test
    fun doesNotTreatEqualOrOlderAsUpdate() {
        assertFalse(VersionComparator.isNewer("0.16.6", "0.16.6"))
        assertFalse(VersionComparator.isNewer("0.16.5", "0.16.6"))
        assertFalse(VersionComparator.isNewer("v0.16.6", "0.16.6"))
    }

    @Test
    fun ignoresSuffixForReleaseComparison() {
        assertFalse(VersionComparator.isNewer("0.16.6-beta", "0.16.6"))
        assertTrue(VersionComparator.isNewer("0.16.7-beta", "0.16.6"))
    }
}
