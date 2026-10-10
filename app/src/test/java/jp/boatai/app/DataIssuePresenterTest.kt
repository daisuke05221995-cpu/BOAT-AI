package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class DataIssuePresenterTest {
    @Test
    fun healthyDiagnosticsStayHidden() {
        val result = DataIssuePresenter.present(
            listOf(DataSourceDiagnostic("開催・出走データ", DiagnosticStatus.OK, "取得済み"))
        )
        assertNull(result)
    }

    @Test
    fun waitingShowsAutomaticRetryGuidance() {
        val result = requireNotNull(
            DataIssuePresenter.present(
                listOf(DataSourceDiagnostic("開催・出走データ", DiagnosticStatus.WAITING, "本日分の公開待ち"))
            )
        )

        assertEquals("データ準備中", result.title)
        assertTrue(result.guidance.contains("15分後に自動再取得"))
        assertEquals(1, result.diagnostics.size)
    }

    @Test
    fun errorShowsManualRetryGuidance() {
        val result = requireNotNull(
            DataIssuePresenter.present(
                listOf(DataSourceDiagnostic("開催・出走データ", DiagnosticStatus.ERROR, "HTTP 500"))
            )
        )

        assertEquals("データ取得エラー", result.title)
        assertTrue(result.guidance.contains("今すぐ再取得"))
        assertTrue(result.isError)
    }
}
