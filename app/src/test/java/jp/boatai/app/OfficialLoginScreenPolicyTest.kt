package jp.boatai.app

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class OfficialLoginScreenPolicyTest {
    private fun element(label: String?, editable: Boolean = false, password: Boolean = false) =
        PurchaseUiElement(label, null, null, false, editable, true, password)

    @Test fun recognizesLoginFormWithoutReadingPrivateField() {
        assertTrue(OfficialLoginScreenPolicy.requiresLogin(listOf(
            element("ログイン"), element(null, editable = true, password = true)
        )))
        assertTrue(OfficialLoginScreenPolicy.requiresLogin(listOf(
            element("ログイン"), element("暗証番号"), element(null, editable = true)
        )))
    }

    @Test fun ignoresAuthenticatedNavigationOrUnrelatedPasswordField() {
        assertFalse(OfficialLoginScreenPolicy.requiresLogin(listOf(element("ログイン履歴"))))
        assertFalse(OfficialLoginScreenPolicy.requiresLogin(listOf(element("レース選択"),
            element(null, editable = true, password = true))))
    }
}
