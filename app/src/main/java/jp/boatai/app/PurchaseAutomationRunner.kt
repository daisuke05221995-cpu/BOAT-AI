package jp.boatai.app

/**
 * A single-use, fail-closed sequencer. A performed step is never retried: its acknowledgement
 * advances the cursor before the next UI operation is requested. No purchase-submit step exists
 * in [PurchaseAutomationScript].
 */
internal class PurchaseAutomationRunner(
    private val maxDurationMs: Long = 180_000L,
    private val maxGapMs: Long = 12_000L
) {
    internal sealed interface State {
        data object Idle : State
        data class WaitingForApp(val queuedAtMs: Long) : State
        data class WaitingForLogin(val detectedAtMs: Long) : State
        data class Running(val stepIndex: Int, val totalSteps: Int) : State
        data class AwaitingReview(val expectedTotal: Int) : State
        data class AwaitingReceipt(val attemptedAtMs: Long) : State
        data class ReceiptVerified(val ticketCount: Int, val totalYen: Int) : State
        data class Stopped(val reason: String) : State
    }

    var state: State = State.Idle
        private set

    private var script: PurchaseAutomationScript? = null
    private var stepIndex = 0
    private var startedAtMs = 0L
    private var lastStepAtMs = 0L

    fun start(plan: PurchaseAutomationScript, check: PurchaseAutomationCheck, nowMs: Long): Boolean {
        if (state is State.Running || !check.allowed || plan.steps.isEmpty() ||
            plan.steps.size > 200 || plan.expectedTotal <= 0 ||
            plan.expectedTotal != check.sessionStake ||
            plan.expectedTicketText.size != check.selectedTickets ||
            plan.steps.any { it.selector.label.isNullOrBlank() && it.selector.resourceId.isNullOrBlank() }
        ) return false
        script = plan
        stepIndex = 0
        startedAtMs = nowMs
        lastStepAtMs = nowMs
        state = State.Running(0, plan.steps.size)
        return true
    }

    fun currentStep(nowMs: Long): PurchaseUiStep? {
        val running = state as? State.Running ?: return null
        if (nowMs < startedAtMs || nowMs - startedAtMs > maxDurationMs ||
            nowMs < lastStepAtMs || nowMs - lastStepAtMs > maxGapMs) {
            stop("操作時間の上限を超えたため停止しました")
            return null
        }
        return script?.steps?.getOrNull(running.stepIndex)
    }

    fun acknowledge(result: PurchaseUiStepResult, nowMs: Long) {
        if (state !is State.Running) return
        if (result is PurchaseUiStepResult.Blocked) {
            stop(result.reason)
            return
        }
        if (currentStep(nowMs) == null) return
        val plan = script ?: return stop("操作手順がありません")
        stepIndex++
        lastStepAtMs = nowMs
        state = if (stepIndex == plan.steps.size) State.AwaitingReview(plan.expectedTotal)
        else State.Running(stepIndex, plan.steps.size)
    }

    fun stop(reason: String) {
        script = null
        state = State.Stopped(reason)
    }

    fun markSubmissionAttempted(atMs: Long) {
        if (state !is State.AwaitingReview) return
        script = null
        state = State.AwaitingReceipt(atMs)
    }

    fun markReceiptVerified(receipt: OfficialPurchaseReceipt) {
        if (state !is State.AwaitingReceipt) return
        state = State.ReceiptVerified(receipt.lines.size, receipt.totalYen)
    }
}
