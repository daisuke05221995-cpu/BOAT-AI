package jp.boatai.app

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri

internal enum class OfficialBetRoute {
    SIMPLE_WEB,
    SMARTPHONE_WEB,
    OFFICIAL_APP,
    MANUAL
}

internal data class OfficialBetLaunchResult(
    val openedOfficialSurface: Boolean,
    val route: OfficialBetRoute,
    val message: String,
    val fallbackAvailable: Boolean
)

internal object OfficialBetLauncher {
    private const val OFFICIAL_APP_PACKAGE = "jp.boatrace.android.boatraceapp"
    internal const val SIMPLE_BET_URL = "https://bu.tbbr.jp/"
    internal const val SMARTPHONE_BET_URL = "https://spweb.brtb.jp/"

    fun launch(context: Context, session: PendingPurchaseSession): OfficialBetLaunchResult {
        if (session.selectedRaces.isEmpty()) {
            return OfficialBetLaunchResult(
                openedOfficialSurface = false,
                route = OfficialBetRoute.MANUAL,
                message = "投票するレースを選択してください。",
                fallbackAvailable = false
            )
        }

        copyTickets(context, session)

        if (openWeb(context, SIMPLE_BET_URL)) {
            return OfficialBetLaunchResult(
                openedOfficialSurface = true,
                route = OfficialBetRoute.SIMPLE_WEB,
                message = "買い目をコピーして公式シンプル投票を開きました。ログイン後、内容と合計金額を確認して投票してください。",
                fallbackAvailable = true
            )
        }

        return launchFallback(context, session)
    }

    fun launchFallback(context: Context, session: PendingPurchaseSession): OfficialBetLaunchResult {
        if (session.selectedRaces.isEmpty()) {
            return OfficialBetLaunchResult(
                openedOfficialSurface = false,
                route = OfficialBetRoute.MANUAL,
                message = "投票するレースを選択してください。",
                fallbackAvailable = false
            )
        }

        copyTickets(context, session)

        if (openWeb(context, SMARTPHONE_BET_URL)) {
            return OfficialBetLaunchResult(
                openedOfficialSurface = true,
                route = OfficialBetRoute.SMARTPHONE_WEB,
                message = "別ルートの公式スマホ投票サイトを開きました。コピー済みの買い目を確認して投票してください。",
                fallbackAvailable = false
            )
        }

        val packageManager = context.packageManager
        val packageIntent = packageManager.getLaunchIntentForPackage(OFFICIAL_APP_PACKAGE)?.apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (packageIntent != null) {
            return runCatching {
                context.startActivity(packageIntent)
                OfficialBetLaunchResult(
                    openedOfficialSurface = true,
                    route = OfficialBetRoute.OFFICIAL_APP,
                    message = "公式BOATRACEアプリを開きました。コピー済みの買い目を確認して公式投票へ進んでください。",
                    fallbackAvailable = false
                )
            }.getOrElse {
                manualFallback(context, session)
            }
        }

        return manualFallback(context, session)
    }

    private fun openWeb(context: Context, url: String): Boolean {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (intent.resolveActivity(context.packageManager) == null) return false
        return runCatching {
            context.startActivity(intent)
            true
        }.getOrDefault(false)
    }

    private fun manualFallback(context: Context, session: PendingPurchaseSession): OfficialBetLaunchResult {
        copyTickets(context, session, includeUrl = true)
        return OfficialBetLaunchResult(
            openedOfficialSurface = false,
            route = OfficialBetRoute.MANUAL,
            message = "公式投票画面を自動で開けませんでした。買い目と公式投票URLをコピーしました。ブラウザへ貼り付けて開いてください。",
            fallbackAvailable = false
        )
    }

    internal fun clipboardText(
        session: PendingPurchaseSession,
        includeUrl: Boolean = false
    ): String = buildString {
        appendLine("BOAT AI 投票予定")
        session.selectedRaces.forEach { race ->
            appendLine("${race.venueName} ${race.raceNumber}R")
            race.tickets.forEach { ticket ->
                appendLine("${ticket.combination} ${ticket.amount}円")
            }
        }
        appendLine("合計 ${session.selectedStake}円")
        if (includeUrl) append("公式投票: $SIMPLE_BET_URL")
    }

    private fun copyTickets(
        context: Context,
        session: PendingPurchaseSession,
        includeUrl: Boolean = false
    ) {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
        clipboard.setPrimaryClip(
            ClipData.newPlainText(
                "BOAT AI 投票予定",
                clipboardText(session, includeUrl)
            )
        )
    }
}
