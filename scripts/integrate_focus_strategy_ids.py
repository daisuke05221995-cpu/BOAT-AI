from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text()
    if new in text:
        print(f"{label}: already wired")
        return
    if old not in text:
        raise SystemExit(f"{label}: insertion point not found")
    path.write_text(text.replace(old, new, 1))
    print(f"{label}: wired")


models = Path("app/src/main/java/jp/boatai/app/Models.kt")
replace_once(
    models,
    '''    val payout: Int,
    val settled: Boolean,
    val createdAt: Long
) {''',
    '''    val payout: Int,
    val settled: Boolean,
    val createdAt: Long,
    val strategyId: String? = null
) {''',
    "BetRecord strategy field",
)
replace_once(
    models,
    '''        put("settled", settled)
        put("createdAt", createdAt)
    }
''',
    '''        put("settled", settled)
        put("createdAt", createdAt)
        if (!strategyId.isNullOrBlank()) put("strategyId", strategyId)
    }
''',
    "BetRecord strategy serialization",
)
replace_once(
    models,
    '''            payout = obj.optInt("payout"),
            settled = obj.optBoolean("settled"),
            createdAt = obj.optLong("createdAt")
        )
''',
    '''            payout = obj.optInt("payout"),
            settled = obj.optBoolean("settled"),
            createdAt = obj.optLong("createdAt"),
            strategyId = obj.optString("strategyId").takeIf { it.isNotBlank() }
        )
''',
    "BetRecord strategy parsing",
)

pending = Path("app/src/main/java/jp/boatai/app/PendingPurchaseStore.kt")
replace_once(
    pending,
    '''    val venueName: String,
    val recommended: Boolean,
    val tickets: List<PendingPurchaseTicket>
) {''',
    '''    val venueName: String,
    val recommended: Boolean,
    val tickets: List<PendingPurchaseTicket>,
    val strategyId: String? = null
) {''',
    "Pending purchase strategy field",
)
replace_once(
    pending,
    '''            .put("venueName", venueName)
            .put("recommended", recommended)
            .put("tickets", ticketArray)
''',
    '''            .put("venueName", venueName)
            .put("recommended", recommended)
            .put("tickets", ticketArray)
            .apply { if (!strategyId.isNullOrBlank()) put("strategyId", strategyId) }
''',
    "Pending purchase strategy serialization",
)
replace_once(
    pending,
    '''                venueName = json.optString("venueName").ifBlank { Venues.name(stadiumNumber) },
                recommended = json.optBoolean("recommended", true),
                tickets = tickets
            )
''',
    '''                venueName = json.optString("venueName").ifBlank { Venues.name(stadiumNumber) },
                recommended = json.optBoolean("recommended", true),
                tickets = tickets,
                strategyId = json.optString("strategyId").takeIf { it.isNotBlank() }
            )
''',
    "Pending purchase strategy parsing",
)
replace_once(
    pending,
    '''        fun create(entries: List<Pair<RaceData, List<PredictionPick>>>): PendingPurchaseSession? {
            val races = entries.mapNotNull { (race, picks) ->''',
    '''        fun create(
            entries: List<Pair<RaceData, List<PredictionPick>>>,
            strategyId: String? = null
        ): PendingPurchaseSession? {
            val races = entries.mapNotNull { (race, picks) ->''',
    "Pending session strategy argument",
)
replace_once(
    pending,
    '''                    venueName = race.venueName,
                    recommended = PredictionEngine.isRecommended(race),
                    tickets = tickets
                )
''',
    '''                    venueName = race.venueName,
                    recommended = PredictionEngine.isRecommended(race),
                    tickets = tickets,
                    strategyId = strategyId
                )
''',
    "Pending session strategy propagation",
)

bet_store = Path("app/src/main/java/jp/boatai/app/BetStore.kt")
replace_once(
    bet_store,
    '''                        payout = 0,
                        settled = false,
                        createdAt = now + sequence++
                    )
''',
    '''                        payout = 0,
                        settled = false,
                        createdAt = now + sequence++,
                        strategyId = race.strategyId
                    )
''',
    "Confirmed purchase strategy propagation",
)
