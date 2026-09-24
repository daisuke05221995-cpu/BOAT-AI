#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path): return (ROOT / path).read_text()
def write(path, text): (ROOT / path).write_text(text)

def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected 1 occurrence, got {count}: {old[:100]!r}")
    write(path, text.replace(old, new, 1))

def replace_method(path, start_marker, end_marker, new_body):
    text = read(path)
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    write(path, text[:start] + new_body + text[end:])

# Preserve the existing legacy prediction before 120-way official odds are resolved.
p = "app/src/main/java/jp/boatai/app/PredictionEngine.kt"
replace_once(p, '''        if (ReferenceR3Strategy.ENABLED) {
            ReferenceR3Strategy.cached(race)?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
            return if (isDecisionReady(race) && race.isPurchasable()) {
                RecommendationDecision(RaceRecommendation.SKIP, "r3参考モデル：公式3連単オッズを判定中")
            } else {
                RecommendationDecision(RaceRecommendation.SKIP, "r3参考モデル：展示・進入など直前情報待ち")
            }
        }
''', '''        if (ReferenceR3Strategy.ENABLED) {
            ReferenceR3Strategy.cached(race)?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
        }
''')
replace_once(p, '''        if (ReferenceR3Strategy.ENABLED) {
            val selection = ReferenceR3Strategy.cached(race) ?: return emptyList()
            return if (selection.recommendation == RaceRecommendation.BUY) selection.picks.take(maxPicks.coerceAtLeast(1)) else emptyList()
        }
''', '''        if (ReferenceR3Strategy.ENABLED) {
            ReferenceR3Strategy.cached(race)?.let { selection ->
                return if (selection.recommendation == RaceRecommendation.BUY) {
                    selection.picks.take(maxPicks.coerceAtLeast(1))
                } else emptyList()
            }
        }
''')

p = "app/src/main/java/jp/boatai/app/BoatViewModel.kt"
replace_once(p,
'''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null
''',
'''    private var oddsRefreshJob: Job? = null
    private var valueRefreshJob: Job? = null
    // 0 = nationwide, 1..24 = venue. A single tap on recommended-only stays active
    // while official 120-way odds are resolved sequentially.
    private var recommendedBulkScope: Int? = null
''')

replace_once(p,
'''                    if (referenceMode) {
                        PredictionEngine.applyReferenceOdds(race, result.odds, _ui.value.raceBudget)
                    } else {
                        PredictionEngine.applyValueOdds(race, result.odds)
                    }
                    val history = predictionStore.captureOpenRaces(listOf(race))
''',
'''                    if (referenceMode) {
                        PredictionEngine.applyReferenceOdds(race, result.odds, _ui.value.raceBudget)
                    } else {
                        PredictionEngine.applyValueOdds(race, result.odds)
                    }
                    val activeScope = recommendedBulkScope
                    if (activeScope != null && (activeScope == 0 || activeScope == race.stadiumNumber)) {
                        _ui.update { state ->
                            val next = state.selectedForBulk.toMutableSet()
                            if (PredictionEngine.isRecommended(race)) next.add(race.id) else next.remove(race.id)
                            state.copy(
                                selectedForBulk = next,
                                actionMessage = "購入推奨を判定中… 現在${next.size}レース選択"
                            )
                        }
                    }
                    val history = predictionStore.captureOpenRaces(listOf(race))
''')

replace_once(p,
'''                delay(250)
            }
        }
    }

    fun retryOdds()''',
'''                delay(250)
            }
            if (recommendedBulkScope != null) {
                _ui.update { state ->
                    val count = state.selectedForBulk.size
                    state.copy(
                        actionMessage = if (count == 0) {
                            "判定完了：現在の対象レースに購入推奨はありません"
                        } else {
                            "判定完了：購入推奨 ${count}レースを選択"
                        }
                    )
                }
                recommendedBulkScope = null
            }
        }
    }

    fun retryOdds()''')

replace_method(p, '    fun selectVenuePurchasable(stadiumNumber: Int) {', '    fun selectVenueIncludingSkipped(stadiumNumber: Int) {', '''    fun selectVenuePurchasable(stadiumNumber: Int) {
        recommendedBulkScope = stadiumNumber
        val candidates = purchasableCandidates(stadiumNumber)
        val ids = candidates.filter(PredictionEngine::isRecommended).mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (ids.isEmpty()) {
                    "購入推奨を判定中…"
                } else {
                    "購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""
                }
            )
        }
        refreshValueSelections(_ui.value.races)
    }

''')

replace_method(p, '    fun selectAllPurchasable() {', '    fun selectAllIncludingSkipped() {', '''    fun selectAllPurchasable() {
        recommendedBulkScope = 0
        val candidates = purchasableCandidates()
        val ids = candidates.filter(PredictionEngine::isRecommended).mapTo(linkedSetOf()) { it.id }
        val skipped = candidates.size - ids.size
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (ids.isEmpty()) {
                    "全国の購入推奨を判定中…"
                } else {
                    "全国の購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""
                }
            )
        }
        refreshValueSelections(_ui.value.races)
    }

''')

# Explicit/manual selection cancels any outstanding recommended-only auto request.
for marker in [
    '    fun selectVenueIncludingSkipped(stadiumNumber: Int) {\n',
    '    fun selectAllIncludingSkipped() {\n',
    '    fun toggleBulkRace(raceId: String) {\n',
]:
    replace_once(p, marker, marker + '        recommendedBulkScope = null\n')
replace_once(p, '''    fun clearBulkSelection() {
        _ui.update { it.copy(selectedForBulk = emptySet(), actionMessage = null) }
    }
''', '''    fun clearBulkSelection() {
        recommendedBulkScope = null
        _ui.update { it.copy(selectedForBulk = emptySet(), actionMessage = null) }
    }
''')

print("v0.15.13 hardened follow-up applied")
