package jp.boatai.app

import java.time.LocalDateTime
import java.time.ZoneId
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OperationalSelfCheckTest {
    private val tokyo = ZoneId.of("Asia/Tokyo")
    private val now = LocalDateTime.of(2026, 10, 11, 12, 0)
    private val nowMillis = now.atZone(tokyo).toInstant().toEpochMilli()

    private fun record(
        id: String,
        date: String,
        settled: Boolean,
        createdAt: Long = nowMillis - 60_000L,
        recommended: Boolean = false,
        strategyId: String? = null,
        sourceAppVersion: String? = "0.18.9"
    ) = PredictionRecord(
        id = id,
        date = date,
        stadiumNumber = 1,
        raceNumber = 1,
        combinations = if (recommended) listOf("1-2-3") else emptyList(),
        stakePerPick = if (recommended) 500 else 0,
        resultCombination = if (settled) "2-1-3" else null,
        trifectaPayout = if (settled) 1000 else 0,
        settled = settled,
        createdAt = createdAt,
        evaluationEligible = true,
        recommended = recommended,
        stakes = if (recommended) listOf(500) else emptyList(),
        strategyId = strategyId,
        sourceAppVersion = sourceAppVersion
    )

    @Test
    fun healthyStateProducesNoIssue() {
        val issues = OperationalSelfCheck.evaluate(
            races = emptyList(),
            predictions = emptyList(),
            monitoringStartedAt = nowMillis - 60_000L,
            currentVersion = "0.18.9",
            backgroundFailureAt = null,
            backgroundFailureSummary = null,
            now = now
        )
        assertTrue(issues.isEmpty())
    }

    @Test
    fun recentBackgroundFailureIsActionable() {
        val issues = OperationalSelfCheck.evaluate(
            races = emptyList(),
            predictions = emptyList(),
            monitoringStartedAt = nowMillis - 60 * 60 * 1000L,
            currentVersion = "0.18.9",
            backgroundFailureAt = nowMillis - 5 * 60 * 1000L,
            backgroundFailureSummary = "scope=PredictionTrackingService.EVALUATE",
            now = now
        )
        assertEquals(OperationalIssueCode.BACKGROUND_FAILURE, issues.single().code)
    }

    @Test
    fun oldBackgroundFailureExpiresFromUi() {
        val issues = OperationalSelfCheck.evaluate(
            races = emptyList(),
            predictions = emptyList(),
            monitoringStartedAt = nowMillis - 12 * 60 * 60 * 1000L,
            currentVersion = "0.18.9",
            backgroundFailureAt = nowMillis - 7 * 60 * 60 * 1000L,
            backgroundFailureSummary = "scope=old",
            now = now
        )
        assertTrue(issues.isEmpty())
    }

    @Test
    fun unsettledPriorDayRecordIsFlagged() {
        val issues = OperationalSelfCheck.evaluate(
            races = emptyList(),
            predictions = listOf(
                record(
                    id = "2026-10-10-01-1",
                    date = "2026-10-10",
                    settled = false
                )
            ),
            monitoringStartedAt = nowMillis - 2 * 60 * 60 * 1000L,
            currentVersion = "0.18.9",
            backgroundFailureAt = null,
            backgroundFailureSummary = null,
            now = now
        )
        assertTrue(issues.any { it.code == OperationalIssueCode.STALE_SETTLEMENT })
    }

    @Test
    fun currentVersionBrokenLiveAuditIsFlagged() {
        val issues = OperationalSelfCheck.evaluate(
            races = emptyList(),
            predictions = listOf(
                record(
                    id = "2026-10-11-01-1",
                    date = "2026-10-11",
                    settled = true,
                    recommended = true,
                    strategyId = "value-v1"
                )
            ),
            monitoringStartedAt = nowMillis - 2 * 60 * 60 * 1000L,
            currentVersion = "0.18.9",
            backgroundFailureAt = null,
            backgroundFailureSummary = null,
            now = now
        )
        assertTrue(issues.any { it.code == OperationalIssueCode.AUDIT_EVIDENCE_MISSING })
    }
}
