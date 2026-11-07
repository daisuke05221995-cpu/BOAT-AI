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
 * It never reads passwords or stores credentials. A wager submission requires an explicit,
 * session-scoped local user action and strict official-screen readback.
 *
 * Screen-specific scripts will be enabled only after their IDs/text and readback contract
 * have been checked against the user's actual Android 12 app screen.
 */
class BoatPurchaseAccessibilityService : AccessibilityService() {
    private val mainHandler = Handler(Looper.getMainLooper())
    private var runner: PurchaseAutomationRunner? = null
    private data class PendingForegroundStart(
        val script: PurchaseAutomationScript,
        val check: PurchaseAutomationCheck,
        val session: PendingPurchaseSession,
        val profile: OfficialPurchaseScreenProfile,
        val liveRaces: List<RaceData>,
        val liveDataFetchedAtMs: Long,
        val submitRequested: Boolean,
        val queuedAtMs: Long
    )
    private var pendingForegroundStart: PendingForegroundStart? = null
    private var loginWaitDeadlineMs = 0L
    private val foregroundWaitExpired = Runnable {
        if (pendingForegroundStart != null) stopWithReason("60秒以内に公式アプリの画面へ戻らなかったため停止しました")
    }
    private val loginWaitExpired = Runnable {
        if (pendingForegroundStart != null) stopWithReason("再ログイン完了を確認できませんでした。ログイン後に改めて購入指示を送ってください")
    }

    private fun maybeStartOnOfficialForeground(eventPackage: String?) {
        val pending = pendingForegroundStart ?: return
        val nowMs = System.currentTimeMillis()
        val rootPackage = rootInActiveWindow?.packageName?.toString()
        val onOfficial = rootPackage == OFFICIAL_APP_PACKAGE &&
            (eventPackage == null || eventPackage == OFFICIAL_APP_PACKAGE)
        if (!onOfficial) return
        if (loginWaitDeadlineMs == 0L && !PurchaseForegroundStartPolicy.canStart(
                eventPackage ?: rootPackage, rootPackage, pending.queuedAtMs, nowMs)) return
        if (loginWaitDeadlineMs != 0L && nowMs >= loginWaitDeadlineMs) {
            stopWithReason("再ログイン待機時間を超えました。購入指示は実行していません")
            return
        }
        val observed = collectElements()?.second ?: return
        if (OfficialLoginScreenPolicy.requiresLogin(observed)) {
            if (loginWaitDeadlineMs == 0L) {
                loginWaitDeadlineMs = nowMs + 120_000L
                mainHandler.removeCallbacks(foregroundWaitExpired)
                mainHandler.postDelayed(loginWaitExpired, 120_000L)
            }
            lastRunState = PurchaseAutomationRunner.State.WaitingForLogin(nowMs)
            return
        }
        pendingForegroundStart = null
        loginWaitDeadlineMs = 0L
        mainHandler.removeCallbacks(foregroundWaitExpired)
        mainHandler.removeCallbacks(loginWaitExpired)
        val started = startPreparedScript(
            pending.script, pending.check, pending.session, pending.profile,
            pending.liveRaces, pending.liveDataFetchedAtMs, pending.submitRequested
        )
        if (!started) stopWithReason("公式アプリ画面が前面になりましたが、操作を開始できませんでした")
    }
    private data class FinalizationContext(
        val session: PendingPurchaseSession,
        val profile: OfficialPurchaseReviewProfile,
        val liveRaces: List<RaceData>,
        val liveDataFetchedAtMs: Long,
        val submitRequested: Boolean
    )
    private var finalizationContext: FinalizationContext? = null
    private var activeReceiptProfile: OfficialPurchaseReceiptProfile? = null
    private data class PendingReceiptContext(
        val session: PendingPurchaseSession,
        val profile: OfficialPurchaseReceiptProfile,
        val attemptedAtMs: Long
    )
    private var pendingReceiptContext: PendingReceiptContext? = null
    private val receiptTimeout = Runnable {
        if (pendingReceiptContext != null) {
            stopWithReason("公式アプリの受付結果を30秒以内に照合できませんでした。投票履歴を手動確認してください（再送禁止）")
        }
    }
    private fun maybeRecordOfficialReceipt() {
        val pending = pendingReceiptContext ?: return
        val observed = collectElements() ?: return
        val receipt = OfficialPurchaseReceiptParser.parse(
            OFFICIAL_APP_PACKAGE, observed.second, pending.session, pending.profile,
            pending.attemptedAtMs, System.currentTimeMillis()
        ) ?: return
        if (!OfficialPurchaseReceiptStore(this).save(receipt)) {
            stopWithReason("公式の受付結果は一致しましたが、端末への保存に失敗しました。履歴を確認してください")
            return
        }
        mainHandler.removeCallbacks(receiptTimeout)
        pendingReceiptContext = null
        runner?.markReceiptVerified(receipt)
        lastRunState = runner?.state ?: PurchaseAutomationRunner.State.Idle
    }
    private var reviewReadAttempts = 0

    private val verifyOfficialReview = object : Runnable {
        override fun run() {
            if (runner?.state !is PurchaseAutomationRunner.State.AwaitingReview) return
            val context = finalizationContext ?: return
            if (System.currentTimeMillis() >= armedUntilMs) return stopWithReason("画面照合前に操作許可が失効しました")
            val observed = collectElements()
            val review = observed?.let { (_, elements) ->
                OfficialPurchaseReviewParser.parse(
                    OFFICIAL_APP_PACKAGE, elements, context.profile, System.currentTimeMillis())
            }
            if (review == null) {
                if (++reviewReadAttempts < 8) mainHandler.postDelayed(this, 500L)
                else stopWithReason("公式アプリの投票確認画面を完全に読み取れませんでした")
                return
            }
            val (amountNodes, amountElements) = observed ?: return stopWithReason("公式アプリ画面が見つかりません")
            val amountInputIndex = PurchaseUiMatching.uniqueVisibleMatch(
                amountElements, context.profile.confirmationTotalInput, forInput = true
            ) ?: return stopWithReason("最終確認の合計金額入力欄を一意に確認できません")
            if (amountNodes[amountInputIndex].isPassword || !OfficialConfirmationAmount.matches(
                    amountNodes[amountInputIndex].text, context.session.selectedStake)) {
                return stopWithReason("最終確認画面に入力された合計金額が一致しません")
            }
            // Recheck at the time of submission, not when the Android app was launched.
            val currentCheck = PurchaseAutomationSafety.validate(context.session, context.liveRaces)
            val gate = PurchaseSubmitGate.validate(
                context.session, review, currentCheck,
                System.currentTimeMillis(), context.liveDataFetchedAtMs
            )
            if (!gate.allowed) return stopWithReason(gate.reason)
            if (!context.submitRequested) {
                // Dry-run stops at a fully matched confirmation screen.
                armedUntilMs = 0L
                finalizationContext = null
                lastRunState = runner?.state ?: PurchaseAutomationRunner.State.Idle
                return
            }
            val (nodes, elements) = observed
            val buttonIndex = PurchaseUiMatching.uniqueVisibleMatch(elements, context.profile.submitButton)
                ?: return stopWithReason("投票確定ボタンを一意に確認できません")
            val button = nodes[buttonIndex]
            if (button.packageName?.toString() != OFFICIAL_APP_PACKAGE || button.isPassword) {
                return stopWithReason("公式アプリの投票確定ボタンではありません")
            }
            val result = PurchaseSubmissionController(AndroidPurchaseAttemptReservation(this@BoatPurchaseAccessibilityService))
                .submitOnce(context.session, review, currentCheck, System.currentTimeMillis(),
                    context.liveDataFetchedAtMs) {
                    // One click at most. A failed/unknown result is never automatically retried.
                    button.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                }
            when (result) {
                is PurchaseSubmissionResult.Rejected -> stopWithReason(result.reason)
                PurchaseSubmissionResult.TapFailedDoNotRetry -> stopWithReason("投票操作の結果が不明です。公式購入履歴を確認してください（再送禁止）")
                PurchaseSubmissionResult.TapAttemptedReceiptPending -> {
                    val attemptedAt = System.currentTimeMillis()
                    runner?.markSubmissionAttempted(attemptedAt)
                    lastRunState = runner?.state ?: PurchaseAutomationRunner.State.Idle
                    armedUntilMs = 0L
                    finalizationContext = null
                    // Never claim that a successful Android click means a wager was accepted.
                    pendingReceiptContext = activeReceiptProfile?.let { receiptProfile ->
                        PendingReceiptContext(context.session, receiptProfile, attemptedAt)
                    }
                    if (pendingReceiptContext == null) {
                        stopWithReason("公式の受付結果画面が未設定です。投票履歴を手動確認してください（再送禁止）")
                    } else mainHandler.postDelayed(receiptTimeout, 30_000L)
                }
            }
        }
    }

    private fun stopWithReason(reason: String) {
        mainHandler.removeCallbacks(runNextStep)
        mainHandler.removeCallbacks(verifyOfficialReview)
        mainHandler.removeCallbacks(foregroundWaitExpired)
        mainHandler.removeCallbacks(loginWaitExpired)
        mainHandler.removeCallbacks(receiptTimeout)
        pendingForegroundStart = null
        loginWaitDeadlineMs = 0L
        pendingReceiptContext = null
        runner?.stop(reason)
        lastRunState = runner?.state ?: PurchaseAutomationRunner.State.Stopped(reason)
        finalizationContext = null
        activeReceiptProfile = null
        armedUntilMs = 0L
    }

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
            when (sequence.state) {
                is PurchaseAutomationRunner.State.Running -> mainHandler.postDelayed(this, 700L)
                is PurchaseAutomationRunner.State.AwaitingReview -> {
                    if (finalizationContext != null) {
                        reviewReadAttempts = 0
                        mainHandler.postDelayed(verifyOfficialReview, 800L)
                    } else armedUntilMs = 0L
                }
                else -> armedUntilMs = 0L
            }
        }
    }

    override fun onServiceConnected() {
        active = WeakReference(this)
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.packageName?.toString() != OFFICIAL_APP_PACKAGE) return
        // Include static headings and row IDs so review/receipt screens can be calibrated.
        // Text is whitelisted: no bet amount, contract number, ID or password is exported.
        lastProbe = collectElements()?.second?.filter { it.visible }
            ?.take(250)?.map { element ->
                element.copy(
                    text = safeControlLabel(element.text),
                    description = safeControlLabel(element.description)
                )
            } ?: emptyList()
        // A user has already armed one local script. Returning to the already-open official
        // app is the only event that can advance it; other apps are ignored.
        maybeStartOnOfficialForeground(event.packageName?.toString())
        maybeRecordOfficialReceipt()
    }

    override fun onInterrupt() = stopWithReason("Androidのユーザー補助が中断されました")

    override fun onDestroy() {
        mainHandler.removeCallbacks(runNextStep)
        mainHandler.removeCallbacks(verifyOfficialReview)
        mainHandler.removeCallbacks(foregroundWaitExpired)
        mainHandler.removeCallbacks(loginWaitExpired)
        mainHandler.removeCallbacks(receiptTimeout)
        pendingForegroundStart = null
        loginWaitDeadlineMs = 0L
        pendingReceiptContext = null
        finalizationContext = null
        activeReceiptProfile = null
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
                return PurchaseUiStepResult.Blocked("一般画面操作からの投票確定操作はできません")
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
                it.matches(Regex(".*(投票|艇番|買い目|ベット|レース|金額|確認|次へ|戻る|ログイン|3連単|３連単|受付|成立|不成立|契約番号|合計).*")) &&
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
                service.mainHandler.removeCallbacks(service.verifyOfficialReview)
                service.mainHandler.removeCallbacks(service.foregroundWaitExpired)
                service.mainHandler.removeCallbacks(service.loginWaitExpired)
                service.mainHandler.removeCallbacks(service.receiptTimeout)
                service.pendingForegroundStart = null
                service.loginWaitDeadlineMs = 0L
                service.pendingReceiptContext = null
                service.finalizationContext = null
                service.activeReceiptProfile = null
                service.runner?.stop("ユーザーが操作を停止しました")
                lastRunState = service.runner?.state ?: PurchaseAutomationRunner.State.Idle
            }
        }

        /**
         * The official app is assumed to be already running in Recents. Do not call launch intents:
         * wait for the user to bring that existing official screen to the foreground.
         */
        internal fun queueForExistingOfficialScreen(
            plan: PurchaseAutomationScript,
            check: PurchaseAutomationCheck,
            session: PendingPurchaseSession,
            profile: OfficialPurchaseScreenProfile,
            liveRaces: List<RaceData>,
            liveDataFetchedAtMs: Long,
            submitRequested: Boolean = false
        ): Boolean {
            if (System.currentTimeMillis() >= armedUntilMs || Looper.myLooper() != Looper.getMainLooper()) return false
            if (!check.allowed || PurchaseAutomationScriptCompiler.compile(session, profile, check) != plan ||
                (submitRequested && (profile.finalization == null || profile.receipt == null))) return false
            val service = active?.get() ?: return false
            if (service.pendingForegroundStart != null ||
                service.runner?.state is PurchaseAutomationRunner.State.Running ||
                service.runner?.state is PurchaseAutomationRunner.State.AwaitingReview ||
                service.runner?.state is PurchaseAutomationRunner.State.AwaitingReceipt) return false
            val queuedAt = System.currentTimeMillis()
            service.pendingForegroundStart = PendingForegroundStart(
                plan, check, session, profile, liveRaces, liveDataFetchedAtMs, submitRequested, queuedAt
            )
            service.loginWaitDeadlineMs = 0L
            lastRunState = PurchaseAutomationRunner.State.WaitingForApp(queuedAt)
            service.mainHandler.postDelayed(service.foregroundWaitExpired,
                PurchaseForegroundStartPolicy.SWITCH_WINDOW_MS)
            // Also handles the case where the official app was already active when queued.
            service.mainHandler.postDelayed({ service.maybeStartOnOfficialForeground(null) }, 250L)
            return true
        }

        /**
         * Runs an already calibrated, locally compiled script. There is no remote command path,
         * no guessed selector, and no wager submission step. Explicit user activation is needed.
         */
        internal fun startPreparedScript(
            plan: PurchaseAutomationScript,
            check: PurchaseAutomationCheck,
            session: PendingPurchaseSession,
            profile: OfficialPurchaseScreenProfile,
            liveRaces: List<RaceData>,
            liveDataFetchedAtMs: Long,
            submitRequested: Boolean = false
        ): Boolean {
            if (System.currentTimeMillis() >= armedUntilMs) return false
            val service = active?.get() ?: return false
            if (Looper.myLooper() != Looper.getMainLooper()) return false
            if (PurchaseAutomationScriptCompiler.compile(session, profile, check) != plan) return false
            if (submitRequested && (profile.finalization == null || profile.receipt == null)) return false
            val sequence = PurchaseAutomationRunner()
            if (!sequence.start(plan, check, System.currentTimeMillis())) return false
            if (service.runner?.state is PurchaseAutomationRunner.State.Running ||
                service.runner?.state is PurchaseAutomationRunner.State.AwaitingReview ||
                service.runner?.state is PurchaseAutomationRunner.State.AwaitingReceipt) return false
            service.runner = sequence
            service.finalizationContext = profile.finalization?.let {
                FinalizationContext(session, it, liveRaces, liveDataFetchedAtMs, submitRequested)
            }
            service.activeReceiptProfile = if (submitRequested) profile.receipt else null
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
