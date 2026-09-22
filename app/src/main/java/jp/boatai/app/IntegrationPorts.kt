package jp.boatai.app

import java.time.LocalDate

/** 公式API・別データ事業者へ差し替えるための接続口。 */
interface RaceDataProvider {
    suspend fun loadDateDetailed(date: LocalDate): DateLoadResult
}

interface OddsProvider {
    suspend fun loadOfficialTrifectaOddsDetailed(
        race: RaceData,
        combinations: List<String>
    ): OddsFetchResult
}

/** 将来のGoogle Drive等への同期は、この接続口だけを実装して差し替える。 */
interface CloudBackupPort {
    suspend fun upload(name: String, contents: ByteArray): Result<Unit>
    suspend fun downloadLatest(): Result<ByteArray>
}

/** 投票確定は行わず、認可された公式連携が提供された場合の受け渡し口だけ定義する。 */
interface PurchaseHandoffPort {
    fun buildOfficialPurchaseUri(race: RaceData, picks: List<PredictionPick>): String
}
