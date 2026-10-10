package jp.boatai.app

data class DataIssuePresentation(
    val title: String,
    val guidance: String,
    val diagnostics: List<DataSourceDiagnostic>,
    val isError: Boolean
)

object DataIssuePresenter {
    fun present(diagnostics: List<DataSourceDiagnostic>): DataIssuePresentation? {
        val actionable = diagnostics.filter { it.status != DiagnosticStatus.OK }
        if (actionable.isEmpty()) return null

        val hasError = actionable.any { it.status == DiagnosticStatus.ERROR }
        val hasWarning = actionable.any { it.status == DiagnosticStatus.WARNING }
        val onlyWaiting = actionable.all { it.status == DiagnosticStatus.WAITING }

        return DataIssuePresentation(
            title = when {
                hasError -> "データ取得エラー"
                hasWarning -> "一部データを取得できません"
                else -> "データ準備中"
            },
            guidance = when {
                hasError -> "通信状況を確認して「今すぐ再取得」を押してください。続く場合は少し時間を空けて再度お試しください。"
                hasWarning -> "一部データが不足しています。予想に必要な情報が揃うまで自動で再確認します。急ぐ場合は「今すぐ再取得」を押してください。"
                onlyWaiting -> "データ公開待ちです。15分後に自動再取得します。急ぐ場合は「今すぐ再取得」を押してください。"
                else -> "自動で再確認します。急ぐ場合は「今すぐ再取得」を押してください。"
            },
            diagnostics = actionable,
            isError = hasError
        )
    }
}
