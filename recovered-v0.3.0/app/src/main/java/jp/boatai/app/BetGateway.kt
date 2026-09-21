package jp.boatai.app

/**
 * 実投票連携の差し替え境界。
 * v0.2.0では認証情報を保持せず、実投票は送信しない。
 * 将来、公式に利用可能な連携方式が確認できた場合はこのinterfaceを実装して差し替える。
 */
interface BetGateway {
    suspend fun place(request: BetRequest): BetGatewayResult
}

data class BetRequest(
    val date: String,
    val stadiumNumber: Int,
    val raceNumber: Int,
    val tickets: List<BetTicket>
)

data class BetTicket(
    val combination: String,
    val amount: Int
)

sealed interface BetGatewayResult {
    data class Accepted(val referenceId: String) : BetGatewayResult
    data class Rejected(val reason: String) : BetGatewayResult
}

class RecordOnlyBetGateway : BetGateway {
    override suspend fun place(request: BetRequest): BetGatewayResult =
        BetGatewayResult.Rejected("v0.2.0は購入記録モードです")
}
