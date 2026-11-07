package jp.boatai.app

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import java.lang.ref.WeakReference

/**
 * Local opt-in driver for the official Android app. The service cannot be enabled remotely.
 * It never reads passwords, stores credentials, or submits a ticket on its own.
 *
 * Screen-specific scripts will be enabled only after their IDs/text and readback contract
 * have been checked against the user's actual Android 12 app screen.
 */
class BoatPurchaseAccessibilityService : AccessibilityService() {
    override fun onServiceConnected() {
        active = WeakReference(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // The service is intentionally event driven. It never auto-taps on receipt of events.
        if (event?.packageName?.toString() != OFFICIAL_APP_PACKAGE) return
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        active?.get()?.takeIf { it === this }?.let { active = null }
        super.onDestroy()
    }

    /** A local, package-locked semantic view used for testing screen selectors. */
    private fun collectElements(): Pair<List<AccessibilityNodeInfo>, List<PurchaseUiElement>>? {
        val root = rootInActiveWindow ?: return null
        if (root.packageName?.toString() != OFFICIAL_APP_PACKAGE) return null
        val nodes = mutableListOf<AccessibilityNodeInfo>()
        val elements = mutableListOf<PurchaseUiElement>()
        fun visit(node: AccessibilityNodeInfo, depth: Int) {
            if (depth > 24 || nodes.size >= 500) return
            nodes += node
            val sensitive = node.isPassword || node.isEditable
            // Editable content might contain a login ID, amount or another private field.
            // The selector engine receives only non-editable static text / descriptions.
            elements += PurchaseUiElement(
                text = if (sensitive) null else node.text?.toString()?.take(80),
                description = if (sensitive) null else node.contentDescription?.toString()?.take(80),
                resourceId = node.viewIdResourceName,
                clickable = node.isClickable,
                editable = node.isEditable,
                visible = node.isVisibleToUser,
                password = node.isPassword
            )
            for (i in 0 until node.childCount) node.getChild(i)?.let { visit(it, depth + 1) }
        }
        visit(root, 0)
        return nodes to elements
    }

    private fun performVerifiedStep(step: PurchaseUiStep): PurchaseUiStepResult {
        val observed = collectElements() ?: return PurchaseUiStepResult.Blocked("公式アプリが表示されていません")
        val (nodes, elements) = observed
        val match = PurchaseUiMatching.uniqueVisibleMatch(elements, step.selector, step is PurchaseUiStep.EnterText)
            ?: return PurchaseUiStepResult.Blocked("対象画面のボタン・入力欄を一意に確認できません")
        val node = nodes[match]
        if (step is PurchaseUiStep.Click) {
            // Confirm/submit buttons require a separate receipt-verification gate.
            if (step.selector.label?.contains(Regex("投票|購入|確定|申込")) == true ||
                node.text?.toString()?.contains(Regex("投票|購入|確定|申込")) == true) {
                return PurchaseUiStepResult.Blocked("購入確定操作は照合機能が完成するまで無効です")
            }
            return if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) PurchaseUiStepResult.Performed
            else PurchaseUiStepResult.Blocked("ボタンを操作できませんでした")
        }
        if (step is PurchaseUiStep.EnterText) {
            if (node.isPassword) return PurchaseUiStepResult.Blocked("認証情報への自動入力は禁止しています")
            val arguments = Bundle().apply {
                putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, step.value)
            }
            return if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)) PurchaseUiStepResult.Performed
            else PurchaseUiStepResult.Blocked("入力欄を操作できませんでした")
        }
        return PurchaseUiStepResult.Blocked("未対応の操作です")
    }

    companion object {
        const val OFFICIAL_APP_PACKAGE = "jp.boatrace.android.boatraceapp"
        private var active: WeakReference<BoatPurchaseAccessibilityService>? = null
        @Volatile private var armedUntilMs: Long = 0L

        fun isConnected(): Boolean = active?.get() != null

        internal fun armForLocalTest(check: PurchaseAutomationCheck): Boolean {
            if (!check.allowed || !isConnected()) return false
            armedUntilMs = System.currentTimeMillis() + 5 * 60_000L
            return true
        }

        fun disarm() { armedUntilMs = 0L }

        /** Explicit local caller only: never deserialize arbitrary remote click instructions. */
        internal fun tryLocalStep(step: PurchaseUiStep): PurchaseUiStepResult {
            if (System.currentTimeMillis() >= armedUntilMs) {
                return PurchaseUiStepResult.Blocked("自動操作の許可が無効または期限切れです")
            }
            return active?.get()?.performVerifiedStep(step)
                ?: PurchaseUiStepResult.Blocked("Androidのユーザー補助でBOAT AI操作機能を有効にしてください")
        }

        fun observedOfficialElements(): Int? = active?.get()?.collectElements()?.second?.count { it.visible }
    }
}

internal sealed interface PurchaseUiStep {
    val selector: PurchaseUiSelector

    data class Click(override val selector: PurchaseUiSelector) : PurchaseUiStep
    data class EnterText(override val selector: PurchaseUiSelector, val value: String) : PurchaseUiStep
}

internal sealed interface PurchaseUiStepResult {
    data object Performed : PurchaseUiStepResult
    data class Blocked(val reason: String) : PurchaseUiStepResult
}
