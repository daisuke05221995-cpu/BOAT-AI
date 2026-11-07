package jp.boatai.app

import android.accessibilityservice.AccessibilityService
import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
    private val mainHandler = Handler(Looper.getMainLooper())
    private var runner: PurchaseAutomationRunner? = null
    private val runNextStep = object : Runnable {
        override fun run() {
            val sequence = runner ?: return
            if (System.currentTimeMillis() >= armedUntilMs) {
                sequence.stop("操作許可の期限が切れました")
                lastRunState = sequence.state
                return
            }
            val step = sequence.currentStep(System.currentTimeMillis())
            if (step == null) {
                lastRunState = sequence.state
                return
            }
            // Every screen is re-read from the official app before *each* action.
            // An ambiguous/missing control stops the script; no failed click is retried.
            sequence.acknowledge(performVerifiedStep(step), System.currentTimeMillis())
            lastRunState = sequence.state
            if (sequence.state is PurchaseAutomationRunner.State.Running) {
                mainHandler.postDelayed(this, 700L)
            } else {
                armedUntilMs = 0L
            }
        }
    }

    override fun onServiceConnected() {
        active = WeakReference(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // The service is intentionally event driven. It never auto-taps on receipt of events.
        if (event?.packageName?.toString() != OFFICIAL_APP_PACKAGE) return
        // Record only the structure of actionable elements. Never persist screen content.
        lastProbe = collectElements()?.second?.filter { it.visible && (it.clickable || it.editable) }
            ?.take(100)?.map { element ->
                element.copy(
                    text = safeControlLabel(element.text),
                    description = safeControlLabel(element.description)
                )
            } ?: emptyList()
    }

    override fun onInterrupt() = Unit

    override fun onDestroy() {
        mainHandler.removeCallbacks(runNextStep)
        runner?.stop("Androidの操作サービスが終了しました")
        lastRunState = runner?.state ?: PurchaseAutomationRunner.State.Idle
        armedUntilMs = 0L
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
            if (listOfNotNull(step.selector.label, node.text?.toString(), node.contentDescription?.toString())
                    .any { it.contains(Regex("投票|購入|確定|申込|送信")) } ||
                listOfNotNull(step.selector.resourceId, node.viewIdResourceName)
                    .any { it.contains(Regex("submit|purchase|commit|confirm|vote|bet_now", RegexOption.IGNORE_CASE)) }) {
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
        @Volatile private var lastProbe: List<PurchaseUiElement> = emptyList()
        @Volatile private var lastRunState: PurchaseAutomationRunner.State = PurchaseAutomationRunner.State.Idle

        // Static screen controls only: never expose entered amounts, account IDs or passwords.
        private fun safeControlLabel(value: String?): String? {
            val normalized = value?.trim()?.takeIf { it.length in 1..30 } ?: return null
            return normalized.takeIf {
                it.matches(Regex(".*(投票|艇番|買い目|ベット|レース|金額|確認|次へ|戻る|ログイン|3連単|３連単).*")) &&
                    !it.contains('@') && !it.matches(Regex(".*\\d{4,}.*"))
            }
        }

        fun isConnected(): Boolean = active?.get() != null

        internal fun armForLocalTest(check: PurchaseAutomationCheck): Boolean {
            if (!check.allowed || !isConnected()) return false
            armedUntilMs = System.currentTimeMillis() + 5 * 60_000L
            return true
        }

        fun disarm() {
            armedUntilMs = 0L
            active?.get()?.let { service ->
                service.mainHandler.removeCallbacks(service.runNextStep)
                service.runner?.stop("ユーザーが操作を停止しました")
                lastRunState = service.runner?.state ?: PurchaseAutomationRunner.State.Idle
            }
        }

        /**
         * Runs an already calibrated, locally compiled script. There is no remote command path,
         * no guessed selector, and no wager submission step. Explicit user activation is needed.
         */
        internal fun startPreparedScript(plan: PurchaseAutomationScript, check: PurchaseAutomationCheck): Boolean {
            if (System.currentTimeMillis() >= armedUntilMs) return false
            val service = active?.get() ?: return false
            if (Looper.myLooper() != Looper.getMainLooper()) return false
            val sequence = PurchaseAutomationRunner()
            if (!sequence.start(plan, check, System.currentTimeMillis())) return false
            if (service.runner?.state is PurchaseAutomationRunner.State.Running ||
                service.runner?.state is PurchaseAutomationRunner.State.AwaitingReview) return false
            service.runner = sequence
            lastRunState = sequence.state
            service.mainHandler.postDelayed(service.runNextStep, 700L)
            return true
        }

        internal fun automationStatus(): PurchaseAutomationRunner.State = lastRunState

        /** Explicit local caller only: never deserialize arbitrary remote click instructions. */
        internal fun tryLocalStep(step: PurchaseUiStep): PurchaseUiStepResult {
            if (System.currentTimeMillis() >= armedUntilMs) {
                return PurchaseUiStepResult.Blocked("自動操作の許可が無効または期限切れです")
            }
            return active?.get()?.performVerifiedStep(step)
                ?: PurchaseUiStepResult.Blocked("Androidのユーザー補助でBOAT AI操作機能を有効にしてください")
        }

        fun observedOfficialElements(): Int? = active?.get()?.collectElements()?.second?.count { it.visible }

        /** Export only sanitized labels / resource IDs, after a deliberate local copy action. */
        fun diagnosticControlMap(): String = buildString {
            appendLine("BOAT AI 公式アプリ操作検証（認証情報・入力値なし）")
            appendLine("controls=${lastProbe.size}")
            lastProbe.forEachIndexed { index, item ->
                val id = item.resourceId?.take(100) ?: "-"
                appendLine("$index id=$id click=${item.clickable} edit=${item.editable} " +
                    "label=${item.text ?: item.description ?: "-"}")
            }
        }
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
