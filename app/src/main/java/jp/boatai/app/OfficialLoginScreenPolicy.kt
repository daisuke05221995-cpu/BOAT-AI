package jp.boatai.app

/** Detect a sign-in interruption without reading or storing entered credentials. */
internal object OfficialLoginScreenPolicy {
    private val loginTitle = Regex(".*(ログイン|ログオン|会員ログイン).*", RegexOption.IGNORE_CASE)
    private val credentialLabel = Regex(".*(パスワード|暗証番号|承認番号|会員番号|ログインID).*", RegexOption.IGNORE_CASE)

    fun requiresLogin(elements: List<PurchaseUiElement>): Boolean {
        val visible = elements.filter { it.visible }
        val hasLoginTitle = visible.any { element ->
            listOfNotNull(element.text, element.description).any(loginTitle::matches)
        }
        val hasCredentialField = visible.any { element ->
            element.editable && element.password ||
                listOfNotNull(element.text, element.description).any(credentialLabel::matches)
        }
        return hasLoginTitle && hasCredentialField
    }
}
