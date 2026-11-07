package jp.boatai.app

/** Start only when the already-running official app is the actual foreground window. */
internal object PurchaseForegroundStartPolicy {
    const val SWITCH_WINDOW_MS = 60_000L

    fun canStart(
        eventPackage: String?,
        foregroundRootPackage: String?,
        queuedAtMs: Long,
        nowMs: Long
    ): Boolean = queuedAtMs > 0 && nowMs >= queuedAtMs && nowMs - queuedAtMs <= SWITCH_WINDOW_MS &&
        eventPackage == BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE &&
        foregroundRootPackage == BoatPurchaseAccessibilityService.OFFICIAL_APP_PACKAGE
}
