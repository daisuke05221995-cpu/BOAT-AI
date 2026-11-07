package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class PurchaseAutomationRunnerTest {
    private val click = PurchaseUiStep.Click(PurchaseUiSelector(resourceId = "official:next"))
    private val amount = PurchaseUiStep.EnterText(PurchaseUiSelector(resourceId = "official:amount"), "500")
    private val plan = PurchaseAutomationScript(listOf(click, amount), listOf("1:1:1-3-5:500"), 500)
    private val check = PurchaseAutomationCheck(true, "OK", 500, 1)

    @Test fun eachSuccessfulActionAdvancesOnceAndEndsBeforeSubmitting() {
        val runner = PurchaseAutomationRunner()
        assertTrue(runner.start(plan, check, 100L))
        assertEquals(click, runner.currentStep(100L))
        runner.acknowledge(PurchaseUiStepResult.Performed, 200L)
        assertEquals(amount, runner.currentStep(200L))
        runner.acknowledge(PurchaseUiStepResult.Performed, 300L)
        assertEquals(PurchaseAutomationRunner.State.AwaitingReview(500), runner.state)
        assertNull(runner.currentStep(301L))
        runner.markSubmissionAttempted(302L)
        assertEquals(PurchaseAutomationRunner.State.AwaitingReceipt(302L), runner.state)
    }

    @Test fun errorsAndTimeoutsStopWithoutRepeatingAnAction() {
        val failed = PurchaseAutomationRunner()
        assertTrue(failed.start(plan, check, 100L))
        failed.acknowledge(PurchaseUiStepResult.Blocked("画面照合エラー"), 200L)
        assertEquals(PurchaseAutomationRunner.State.Stopped("画面照合エラー"), failed.state)
        assertNull(failed.currentStep(300L))

        val expired = PurchaseAutomationRunner(maxGapMs = 1_000L)
        assertTrue(expired.start(plan, check, 100L))
        assertNull(expired.currentStep(1_101L))
        assertTrue(expired.state is PurchaseAutomationRunner.State.Stopped)
    }

    @Test fun mismatchedStakeAndUnmappedOrEmptyScriptCannotStart() {
        assertFalse(PurchaseAutomationRunner().start(plan, check.copy(sessionStake = 600), 100L))
        assertFalse(PurchaseAutomationRunner().start(plan.copy(steps = emptyList()), check, 100L))
        assertFalse(PurchaseAutomationRunner().start(plan.copy(steps = listOf(
            PurchaseUiStep.Click(PurchaseUiSelector())
        )), check, 100L))
    }
}
