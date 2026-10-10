package jp.boatai.app

import android.content.Context
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.ZoneId

enum class OperationalIssueCode {
    BACKGROUND_FAILURE,
    MISSED_PREDICTION,
    STALE_SETTLEMENT,
    AUDIT_EVIDENCE_MISSING
}

data class OperationalIssue(
    val code: OperationalIssueCode,
    val title: String,
    val detail: String,
    val guidance: String
)

class OperationalSelfCheckStore(context: Context) {
    private val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun monitoringStartedAt(nowMillis: Long = System.currentTimeMillis()): Long {
        val existing = prefs.getLong(KEY_STARTED_AT, 0L)
        if (existing > 0L) return existing
        prefs.edit().putLong(KEY_STARTED_AT, nowMillis).apply()
        return nowMillis
    }

    companion object {
        private const val PREFS = "boat_ai_operational_self_check"
        private const val KEY_STARTED_AT = "monitoring_started_at"
    }
}

object OperationalSelfCheck {
    private val TOKYO: ZoneId = ZoneId.of("Asia/Tokyo")
    private const val BACKGROUND_FAILURE_VISIBLE_MS = 6 * 60 * 60 * 1000L
    private const val MISSED_GRACE_MINUTES = 15L
    private const val SETTLEMENT_GRACE_MINUTES = 120L

    fun evaluate(
        races: List<RaceData>,
        predictions: List<PredictionRecord>,
        monitoringStartedAt: Long,
        currentVersion: String,
        backgroundFailureAt: Long?,
        backgroundFailureSummary: String?,
        now: LocalDateTime = LocalDateTime.now(TOKYO)
    ): List<OperationalIssue> = buildList {
        val nowMillis = now.atZone(TOKYO).toInstant().toEpochMilli()

        if (
            backgroundFailureAt != null &&
            backgroundFailureAt >= monitoringStartedAt &&
            nowMillis - backgroundFailureAt in 0..BACKGROUND_FAILURE_VISIBLE_MS
        ) {
            add(
                OperationalIssue(
                    code = OperationalIssueCode.BACKGROUND_FAILURE,
                    title = "バックグラウンド処理でエラーがありました",
                    detail = backgroundFailureSummary?.lineSequence()?.firstOrNull { it.startsWith("scope=") }
                        ?.removePrefix("scope=")
                        ?.let { "処理: $it" }
                        ?: "直近の自動処理で失敗を検知しました。",
                    guidance = "「今すぐ再取得」を実行してください。繰り返す場合は設定からバックアップを保存して共有してください。"
                )
            )
        }

        val recordsById = predictions.associateBy { it.id }
        val missed = races.count { race ->
            val close = closeAt(race) ?: return@count false
            val closeMillis = close.atZone(TOKYO).toInstant().toEpochMilli()
            race.date.take(10) == now.toLocalDate().toString() &&
                close.plusMinutes(MISSED_GRACE_MINUTES).isBefore(now) &&
                closeMillis >= monitoringStartedAt &&
                PredictionEngine.isDecisionReady(race) &&
                recordsById[race.id] == null
        }
        if (missed > 0) {
            add(
                OperationalIssue(
                    code = OperationalIssueCode.MISSED_PREDICTION,
                    title = "締切前予想の記録漏れを検知",
                    detail = "本日 $missed レースで締切前予想の保存を確認できません。",
                    guidance = "今すぐ再取得してください。次のレースでも続く場合はバックアップを保存して共有してください。"
                )
            )
        }

        val staleSettlement = predictions.count { record ->
            if (record.settled || record.createdAt < monitoringStartedAt) return@count false
            val date = runCatching { LocalDate.parse(record.date.take(10)) }.getOrNull() ?: return@count false
            when {
                date.isBefore(now.toLocalDate()) -> true
                date.isAfter(now.toLocalDate()) -> false
                else -> {
                    val race = races.firstOrNull { it.id == record.id } ?: return@count false
                    val close = closeAt(race) ?: return@count false
                    close.plusMinutes(SETTLEMENT_GRACE_MINUTES).isBefore(now)
                }
            }
        }
        if (staleSettlement > 0) {
            add(
                OperationalIssue(
                    code = OperationalIssueCode.STALE_SETTLEMENT,
                    title = "結果反映が止まっている可能性があります",
                    detail = "$staleSettlement レースが長時間未精算のままです。",
                    guidance = "「今すぐ再取得」を実行してください。解消しない場合はバックアップを保存して共有してください。"
                )
            )
        }

        val brokenAudit = predictions.count { record ->
            record.sourceAppVersion == currentVersion &&
                record.createdAt >= monitoringStartedAt &&
                LiveAuditedPerformance.isLiveBuyCandidate(record) &&
                LiveAuditedPerformance.auditFailures(record).isNotEmpty()
        }
        if (brokenAudit > 0) {
            add(
                OperationalIssue(
                    code = OperationalIssueCode.AUDIT_EVIDENCE_MISSING,
                    title = "予想記録の監査データに異常があります",
                    detail = "現行版で $brokenAudit レースの公式オッズ監査情報が不足しています。",
                    guidance = "過去分は再作成せず、設定からバックアップを保存して共有してください。"
                )
            )
        }
    }

    private fun closeAt(race: RaceData): LocalDateTime? {
        val date = runCatching { LocalDate.parse(race.date.take(10)) }.getOrNull() ?: return null
        val match = Regex("""(\d{1,2}):(\d{2})""").findAll(race.closedAt).lastOrNull() ?: return null
        val time = runCatching {
            LocalTime.of(match.groupValues[1].toInt(), match.groupValues[2].toInt())
        }.getOrNull() ?: return null
        return LocalDateTime.of(date, time)
    }
}
