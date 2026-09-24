package jp.boatai.app

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri

internal data class OfficialBetLaunchResult(
    val openedOfficialApp: Boolean,
    val message: String
)

internal object OfficialBetLauncher {
    private const val OFFICIAL_APP_PACKAGE = "jp.boatrace.android.boatraceapp"
    private const val OFFICIAL_SMARTPHONE_URL = "https://spweb.brtb.jp/"

    fun launch(context: Context, session: PendingPurchaseSession): OfficialBetLaunchResult {
        copyTickets(context, session)
        val packageManager = context.packageManager
        val webIntent = Intent(Intent.ACTION_VIEW, Uri.parse(OFFICIAL_SMARTPHONE_URL)).apply {
            setPackage(OFFICIAL_APP_PACKAGE)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val packageIntent = packageManager.getLaunchIntentForPackage(OFFICIAL_APP_PACKAGE)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        val officialIntent = when {
            webIntent.resolveActivity(packageManager) != null -> webIntent
            packageIntent != null -> packageIntent
            else -> null
        }
        return if (officialIntent != null) {
            context.startActivity(officialIntent)
            OfficialBetLaunchResult(
                openedOfficialApp = true,
                message = "買い目をコピーして公式BOATRACEアプリを開きました。公式側で内容を確認して投票してください。"
            )
        } else {
            context.startActivity(
                Intent(Intent.ACTION_VIEW, Uri.parse(OFFICIAL_SMARTPHONE_URL)).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
            )
            OfficialBetLaunchResult(
                openedOfficialApp = false,
                message = "買い目をコピーして公式投票サイトを開きました。公式側で内容を確認して投票してください。"
            )
        }
    }

    internal fun clipboardText(session: PendingPurchaseSession): String = buildString {
        appendLine("BOAT AI 投票予定")
        session.selectedRaces.forEach { race ->
            appendLine("${race.venueName} ${race.raceNumber}R")
            race.tickets.forEach { ticket ->
                appendLine("${ticket.combination} ${ticket.amount}円")
            }
        }
        append("合計 ${session.selectedStake}円")
    }

    private fun copyTickets(context: Context, session: PendingPurchaseSession) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(ClipData.newPlainText("BOAT AI 投票予定", clipboardText(session)))
    }
}
