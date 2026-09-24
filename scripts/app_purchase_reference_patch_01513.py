#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app/src/main/java/jp/boatai/app"

def read(path):
    return (ROOT / path).read_text()

def write(path, text):
    p = ROOT / path
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)

def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected 1 occurrence, found {count}: {old[:80]!r}")
    write(path, text.replace(old, new, 1))

def regex_replace_once(path, pattern, repl):
    text = read(path)
    new, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise RuntimeError(f"{path}: regex expected 1 occurrence, found {count}: {pattern[:80]!r}")
    write(path, new)

# --- New official purchase launcher ---
write("app/src/main/java/jp/boatai/app/OfficialBetLauncher.kt", r'''package jp.boatai.app

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
''')

# --- Reference-only r3 policy: live approximation, NOT the exact historical LightGBM ---
write("app/src/main/java/jp/boatai/app/ReferenceR3Strategy.kt", r'''package jp.boatai.app

import java.util.concurrent.ConcurrentHashMap
import kotlin.math.exp

/**
 * Temporary reference operation requested by the user.
 *
 * Historical r3 place-small showed 258.54% ROI in 2024, but only 24 purchases / 3 hits,
 * failed the preregistered annual gate, and was NOT production-qualified. The original
 * research model is quarterly LightGBM and is not executable in the Android runtime.
 * This object therefore applies the frozen r3 betting policy to a transparent live
 * approximation: market-implied 1st-place probability + current BOAT AI conditional
 * 2nd/3rd strength. The historical ROI MUST NOT be attributed to this approximation.
 */
internal object ReferenceR3Strategy {
    const val ENABLED = true
    const val HISTORICAL_ROI = 258.54
    const val HISTORICAL_PURCHASES = 24
    const val HISTORICAL_HITS = 3
    const val BUDGET = 1_200
    const val MAX_POINTS = 3
    const val MIN_EV = 1.10
    const val MIN_PROBABILITY = 0.01
    const val MAX_ODDS = 40.0

    private val selections = ConcurrentHashMap<String, ValueSelection>()
    private val combinations = buildList(120) {
        for (first in 1..6) for (second in 1..6) for (third in 1..6) {
            if (first != second && first != third && second != third) add("$first-$second-$third")
        }
    }

    fun allCombinations(): List<String> = combinations
    fun cached(race: RaceData): ValueSelection? = selections[race.id]
    fun clear() = selections.clear()

    fun evaluateAndCache(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection = selections.computeIfAbsent(race.id) {
        evaluate(race, officialOdds, budget)
    }

    internal fun evaluate(
        race: RaceData,
        officialOdds: Map<String, Double>,
        budget: Int = BUDGET
    ): ValueSelection {
        if (race.racers.size != 6 || officialOdds.count { it.value > 0.0 } < 100) {
            return skip("公式3連単オッズが十分に取得できていません")
        }
        val inverse = combinations.associateWith { combo ->
            officialOdds[combo]?.takeIf { it > 1.0 }?.let { 1.0 / it } ?: 0.0
        }
        val inverseTotal = inverse.values.sum()
        if (inverseTotal <= 0.0) return skip("公式オッズを確率へ変換できません")

        val firstMarket = DoubleArray(7)
        inverse.forEach { (combo, raw) ->
            val first = combo.substringBefore('-').toIntOrNull() ?: return@forEach
            firstMarket[first] += raw / inverseTotal
        }
        val firstTotal = firstMarket.sum()
        if (firstTotal <= 0.0) return skip("1着市場確率を計算できません")
        for (lane in 1..6) firstMarket[lane] /= firstTotal

        val racers = race.racers.associateBy { it.lane }
        val rawScores = (1..6).associateWith { lane ->
            racers[lane]?.let(PredictionEngine::racerScore) ?: 0.0
        }
        val maxScore = rawScores.values.maxOrNull() ?: 0.0
        val weights = (1..6).associateWith { lane -> exp(((rawScores[lane] ?: 0.0) - maxScore) / 18.0) }

        data class Candidate(val combination: String, val probability: Double, val odds: Double, val ev: Double)
        val candidates = mutableListOf<Candidate>()
        for (combo in combinations) {
            val lanes = combo.split('-').mapNotNull(String::toIntOrNull)
            if (lanes.size != 3) continue
            val (first, second, third) = lanes
            val odds = officialOdds[combo]?.takeIf { it > 1.0 && it <= MAX_ODDS } ?: continue
            val remainingAfterFirst = (1..6).filter { it != first }
            val sumSecond = remainingAfterFirst.sumOf { weights[it] ?: 0.0 }
            if (sumSecond <= 0.0) continue
            val pSecond = (weights[second] ?: 0.0) / sumSecond
            val remainingAfterSecond = remainingAfterFirst.filter { it != second }
            val sumThird = remainingAfterSecond.sumOf { weights[it] ?: 0.0 }
            if (sumThird <= 0.0) continue
            val pThird = (weights[third] ?: 0.0) / sumThird
            val probability = firstMarket[first] * pSecond * pThird
            val ev = probability * odds
            if (probability >= MIN_PROBABILITY && ev >= MIN_EV) {
                candidates += Candidate(combo, probability, odds, ev)
            }
        }
        val selected = candidates.sortedWith(
            compareByDescending<Candidate> { it.ev }.thenByDescending { it.probability }
        ).take(MAX_POINTS)
        if (selected.isEmpty()) return skip("r3参考固定条件に該当する買い目がありません")

        val stakes = BetStrategy.allocateEvenly(selected.size, budget.coerceIn(1_000, 3_000))
        val picks = selected.mapIndexed { index, candidate ->
            PredictionPick(
                combination = candidate.combination,
                score = candidate.ev,
                odds = candidate.odds,
                recommendedStake = stakes[index],
                tier = when {
                    index == 0 && candidate.odds < 15.0 -> BetTier.MAIN
                    candidate.odds >= 35.0 -> BetTier.LONG
                    else -> BetTier.MID
                },
                reason = "r3参考固定条件 EV${"%.2f".format(candidate.ev)}"
            )
        }
        return ValueSelection(
            picks = picks,
            recommendation = RaceRecommendation.BUY,
            reason = "参考購入：r3固定条件を現行確率近似で適用（過去ROI258.5%は24購入・3的中で検証不合格）"
        )
    }

    private fun skip(detail: String) = ValueSelection(
        picks = emptyList(),
        recommendation = RaceRecommendation.SKIP,
        reason = "参考見送り：$detail（r3は検証不合格モデル）"
    )
}
''')

# --- Version ---
replace_once("app/build.gradle.kts", 'versionCode = 30\n        versionName = "0.15.12"', 'versionCode = 31\n        versionName = "0.15.13"')

# --- Android package visibility for official BOATRACE app ---
manifest = read("app/src/main/AndroidManifest.xml")
needle = '    <application\n'
if '<package android:name="jp.boatrace.android.boatraceapp" />' not in manifest:
    if needle not in manifest:
        raise RuntimeError("AndroidManifest application marker not found")
    manifest = manifest.replace(needle, '    <queries>\n        <package android:name="jp.boatrace.android.boatraceapp" />\n    </queries>\n\n' + needle, 1)
write("app/src/main/AndroidManifest.xml", manifest)

# --- PendingPurchaseCard: official app launcher, no direct external browser handoff ---
p = "app/src/main/java/jp/boatai/app/PendingPurchaseCard.kt"
text = read(p)
text = text.replace('import androidx.compose.ui.platform.LocalUriHandler\n', '')
text = text.replace('    val uriHandler = LocalUriHandler.current\n', '')
text = text.replace('Button(onClick = { uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL) }) {\n                    Text("公式投票サイト")\n                }', 'Button(onClick = vm::openOfficialPurchase) {\n                    Text("公式アプリで入力")\n                }')
text = text.replace('"公式サイトで実際に投票できたレースだけチェックを残し、戻ってから実購入として確定してください。"', '"買い目はクリップボードへ自動コピーします。公式側で内容を確認して投票し、戻ってから実購入として確定してください。"')
write(p, text)

# --- MainActivity: use common official launcher and explain reference mode ---
p = "app/src/main/java/jp/boatai/app/MainActivity.kt"
text = read(p)
text = text.replace('private fun VenueDetailScreen(ui: BoatUiState, vm: BoatViewModel, stadium: Int) {\n    val races = ui.races.filter { it.stadiumNumber == stadium }.sortedBy { it.raceNumber }\n    val uriHandler = LocalUriHandler.current\n', 'private fun VenueDetailScreen(ui: BoatUiState, vm: BoatViewModel, stadium: Int) {\n    val races = ui.races.filter { it.stadiumNumber == stadium }.sortedBy { it.raceNumber }\n')
text = text.replace('private fun BulkPurchaseCard(ui: BoatUiState, vm: BoatViewModel) {\n    val uriHandler = LocalUriHandler.current\n', 'private fun BulkPurchaseCard(ui: BoatUiState, vm: BoatViewModel) {\n')
text = text.replace('if (vm.prepareRacePurchase(race)) {\n                        uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL)\n                    }', 'if (vm.prepareRacePurchase(race)) {\n                        vm.openOfficialPurchase()\n                    }')
text = text.replace('if (vm.prepareSelectedPurchase()) {\n                        uriHandler.openUri(PendingPurchaseStore.OFFICIAL_SIMPLE_BET_URL)\n                    }', 'if (vm.prepareSelectedPurchase()) {\n                        vm.openOfficialPurchase()\n                    }')
text = text.replace('公式シンプル投票サイトを開きます。公式側で実際に投票後、BOAT AIへ戻って投票できたレースだけ実購入として確定してください。', '公式BOATRACEアプリを優先して開きます（未導入時は公式投票サイト）。買い目はクリップボードへコピーされるので、公式側で確認して入力・投票後、BOAT AIへ戻って実購入を確定してください。')
text = text.replace('Text("AIの最終判断は「購入推奨 / 見送り」の2択です。", style = MaterialTheme.typography.bodySmall)', 'Text("現在はr3 place-smallの固定条件を参考運用中です。過去ROI258.5%は24購入・3的中で検証不合格のため、最終判断は必ずご自身で行ってください。", style = MaterialTheme.typography.bodySmall)')
write(p, text)

# --- PredictionEngine: reference mode routes all recommendation/pick paths consistently ---
p = "app/src/main/java/jp/boatai/app/PredictionEngine.kt"
text = read(p)
text = text.replace('    fun hasValueStrategyModel(): Boolean = valueStrategyModel != null\n\n    fun valueOddsCombinations(): List<String> = valueStrategyModel?.allCombinations().orEmpty()\n', '''    fun hasValueStrategyModel(): Boolean = valueStrategyModel != null
    fun hasReferenceR3Strategy(): Boolean = ReferenceR3Strategy.ENABLED
    fun referenceOddsCombinations(): List<String> = ReferenceR3Strategy.allCombinations()
    internal fun hasReferenceSelection(race: RaceData): Boolean = ReferenceR3Strategy.cached(race) != null
    internal fun applyReferenceOdds(race: RaceData, odds: Map<String, Double>, budget: Int): ValueSelection =
        ReferenceR3Strategy.evaluateAndCache(race, odds, budget)

    fun valueOddsCombinations(): List<String> = valueStrategyModel?.allCombinations().orEmpty()
''')
text = text.replace('    fun clearValueSelections() {\n        valueSelections.clear()\n    }', '    fun clearValueSelections() {\n        valueSelections.clear()\n        ReferenceR3Strategy.clear()\n    }')
text = text.replace('    fun recommendation(race: RaceData): RecommendationDecision {\n        if (valueStrategyModel != null) {', '''    fun recommendation(race: RaceData): RecommendationDecision {
        if (ReferenceR3Strategy.ENABLED) {
            ReferenceR3Strategy.cached(race)?.let { selection ->
                return RecommendationDecision(selection.recommendation, selection.reason)
            }
            return if (isDecisionReady(race) && race.isPurchasable()) {
                RecommendationDecision(RaceRecommendation.SKIP, "r3参考モデル：公式3連単オッズを判定中")
            } else {
                RecommendationDecision(RaceRecommendation.SKIP, "r3参考モデル：展示・進入など直前情報待ち")
            }
        }
        if (valueStrategyModel != null) {''')
text = text.replace('    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {\n        if (valueStrategyModel != null) {', '''    fun predict(race: RaceData, maxPicks: Int = 4): List<PredictionPick> {
        if (ReferenceR3Strategy.ENABLED) {
            val selection = ReferenceR3Strategy.cached(race) ?: return emptyList()
            return if (selection.recommendation == RaceRecommendation.BUY) selection.picks.take(maxPicks.coerceAtLeast(1)) else emptyList()
        }
        if (valueStrategyModel != null) {''')
text = text.replace('    ): List<PredictionPick> {\n        if (valueStrategyModel != null) {\n            val valueSelection = applyValueOdds(race, odds, learningOverride) ?: return emptyList()', '''    ): List<PredictionPick> {
        if (ReferenceR3Strategy.ENABLED) {
            val selection = ReferenceR3Strategy.evaluateAndCache(race, odds, budget)
            return if (selection.recommendation == RaceRecommendation.BUY) {
                BetStrategy.allocate(race, selection.picks, budget)
            } else emptyList()
        }
        if (valueStrategyModel != null) {
            val valueSelection = applyValueOdds(race, odds, learningOverride) ?: return emptyList()''')
write(p, text)

# --- ViewModel: resolve all 120 odds for reference model; bulk only after a real decision ---
p = "app/src/main/java/jp/boatai/app/BoatViewModel.kt"
text = read(p)
text = text.replace('''            val requested = if (PredictionEngine.hasValueStrategyModel()) {
                PredictionEngine.valueOddsCombinations()
            } else {
                initial.map { it.combination }
            }''', '''            val requested = when {
                PredictionEngine.hasReferenceR3Strategy() -> PredictionEngine.referenceOddsCombinations()
                PredictionEngine.hasValueStrategyModel() -> PredictionEngine.valueOddsCombinations()
                else -> initial.map { it.combination }
            }''')
text = text.replace('oddsDecision = if (PredictionEngine.hasValueStrategyModel()) {', 'oddsDecision = if (PredictionEngine.hasValueStrategyModel() || PredictionEngine.hasReferenceR3Strategy()) {')
start = text.index('    private fun refreshValueSelections(races: List<RaceData>) {')
end = text.index('\n    fun retryOdds()', start)
new_refresh = r'''    private fun refreshValueSelections(races: List<RaceData>) {
        val referenceMode = PredictionEngine.hasReferenceR3Strategy()
        val combinations = when {
            referenceMode -> PredictionEngine.referenceOddsCombinations()
            PredictionEngine.hasValueStrategyModel() -> PredictionEngine.valueOddsCombinations()
            else -> return
        }
        if (combinations.size != 120) return
        val candidates = races.filter { it.isPurchasable() && PredictionEngine.isDecisionReady(it) }
        if (candidates.isEmpty()) return

        valueRefreshJob?.cancel()
        valueRefreshJob = viewModelScope.launch {
            for (race in candidates) {
                if (!race.isPurchasable()) continue
                if (referenceMode && PredictionEngine.hasReferenceSelection(race)) continue
                if (!referenceMode && PredictionEngine.cachedValueSelection(race) != null) continue
                runCatching {
                    repository.loadOfficialTrifectaOddsDetailed(race, combinations)
                }.onSuccess { result ->
                    if (referenceMode) {
                        PredictionEngine.applyReferenceOdds(race, result.odds, _ui.value.raceBudget)
                    } else {
                        PredictionEngine.applyValueOdds(race, result.odds)
                    }
                    val history = predictionStore.captureOpenRaces(listOf(race))
                    val performance = PredictionPerformanceProfile.from(history)
                    PredictionEngine.installPerformanceProfile(performance)
                    _ui.update { state ->
                        if (state.selectedRace?.id == race.id) {
                            val picks = if (PredictionEngine.isRecommended(race)) {
                                BetStrategy.allocate(race, PredictionEngine.predict(race), state.raceBudget)
                            } else state.predictions
                            state.copy(
                                predictions = picks,
                                predictionHistory = history,
                                performance = performance,
                                oddsUpdatedAt = result.fetchedAt,
                                oddsSource = result.source,
                                lastUpdatedAt = System.currentTimeMillis()
                            )
                        } else {
                            state.copy(
                                predictionHistory = history,
                                performance = performance,
                                lastUpdatedAt = System.currentTimeMillis()
                            )
                        }
                    }
                }
                delay(250)
            }
        }
    }
'''
text = text[:start] + new_refresh + text[end:]
# Make zero-selection feedback explicit.
text = text.replace('actionMessage = "購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""', 'actionMessage = if (ids.isEmpty()) "現在の判定済みレースに購入推奨はありません（オッズ判定中は自動更新されます）" else "購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""')
text = text.replace('actionMessage = "全国の購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""', 'actionMessage = if (ids.isEmpty()) "現在の判定済みレースに購入推奨はありません（オッズ判定中は自動更新されます）" else "全国の購入推奨 ${ids.size}レースを選択" + if (skipped > 0) " / 見送り ${skipped}レースは除外" else ""')
# Guard manual toggle while reference odds are unresolved.
text = text.replace('if (PredictionEngine.hasValueStrategyModel() && PredictionEngine.cachedValueSelection(race) == null) {\n            _ui.update { it.copy(actionMessage = "${race.venueName} ${race.raceNumber}Rは公式オッズ判定中です") }', 'if ((PredictionEngine.hasReferenceR3Strategy() && !PredictionEngine.hasReferenceSelection(race)) ||\n            (PredictionEngine.hasValueStrategyModel() && PredictionEngine.cachedValueSelection(race) == null)) {\n            _ui.update { it.copy(actionMessage = "${race.venueName} ${race.raceNumber}Rは公式オッズ判定中です") }')
# Add launcher method just before pending toggle if marker exists.
marker = '    fun togglePendingPurchaseRace(raceId: String) {'
if marker not in text:
    raise RuntimeError('togglePendingPurchaseRace marker not found')
text = text.replace(marker, '''    fun openOfficialPurchase() {
        val session = _ui.value.pendingPurchase ?: return
        runCatching { OfficialBetLauncher.launch(getApplication(), session) }
            .onSuccess { result -> _ui.update { it.copy(actionMessage = result.message) } }
            .onFailure { error -> _ui.update { it.copy(actionMessage = error.message ?: "公式投票画面を開けませんでした") } }
    }

''' + marker, 1)
# Replace purchasableCandidates reference branch by minimally extending value-model condition.
old = '''            if (PredictionEngine.hasValueStrategyModel()) {
                PredictionEngine.isDecisionReady(race) && PredictionEngine.cachedValueSelection(race) != null'''
new = '''            if (PredictionEngine.hasReferenceR3Strategy()) {
                PredictionEngine.isDecisionReady(race) && PredictionEngine.hasReferenceSelection(race)
            } else if (PredictionEngine.hasValueStrategyModel()) {
                PredictionEngine.isDecisionReady(race) && PredictionEngine.cachedValueSelection(race) != null'''
if old not in text:
    raise RuntimeError('purchasableCandidates value-model branch not found')
text = text.replace(old, new, 1)
write(p, text)

# --- Update old constant as a safe browser fallback ---
replace_once("app/src/main/java/jp/boatai/app/PendingPurchaseStore.kt", 'const val OFFICIAL_SIMPLE_BET_URL = "https://bu.tbbr.jp/"', 'const val OFFICIAL_SIMPLE_BET_URL = "https://spweb.brtb.jp/"')

# --- Tests for reference policy metadata and 120 combinations ---
write("app/src/test/java/jp/boatai/app/ReferenceR3StrategyTest.kt", r'''package jp.boatai.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReferenceR3StrategyTest {
    @Test
    fun exposesFrozenReferencePolicyAndAllCombinations() {
        assertEquals(120, ReferenceR3Strategy.allCombinations().distinct().size)
        assertEquals(1_200, ReferenceR3Strategy.BUDGET)
        assertEquals(3, ReferenceR3Strategy.MAX_POINTS)
        assertEquals(1.10, ReferenceR3Strategy.MIN_EV, 0.00001)
        assertEquals(40.0, ReferenceR3Strategy.MAX_ODDS, 0.00001)
        assertFalse(ReferenceR3Strategy.HISTORICAL_PURCHASES >= 360)
    }

    @Test
    fun evaluationNeverReturnsMoreThanThreePicksAndKeepsBudget() {
        val odds = ReferenceR3Strategy.allCombinations().associateWith { 20.0 }
        val result = ReferenceR3Strategy.evaluate(testRace(), odds, 1_200)
        assertTrue(result.picks.size <= 3)
        if (result.recommendation == RaceRecommendation.BUY) {
            assertEquals(1_200, result.picks.sumOf { it.recommendedStake })
            assertTrue(result.picks.all { (it.odds ?: 999.0) <= 40.0 })
            assertTrue(result.reason.contains("検証不合格"))
        }
    }

    private fun testRace() = RaceData(
        date = "2026-09-24", stadiumNumber = 1, raceNumber = 1, closedAt = "23:59",
        gradeNumber = null, title = "test", subtitle = "", distance = 1800, dayNumber = 1,
        racers = (1..6).map { lane ->
            Racer(
                lane = lane, name = "r$lane", registrationNumber = 4000 + lane, rank = "A1",
                branch = null, age = null, weight = 52.0, averageStart = 0.15 + lane * 0.001,
                nationalWinRate = 7.0 - lane * 0.2, nationalTop2 = null, nationalTop3 = null,
                localWinRate = 6.5 - lane * 0.15, localTop2 = null, localTop3 = null,
                motorNumber = lane, motorTop2 = 40.0 - lane, motorTop3 = null,
                boatNumber = lane, boatTop2 = 35.0, boatTop3 = null,
                preview = PreviewRacer(lane, 0.12 + lane * 0.005, 52.0, 0.0, 6.70 + lane * 0.01, 0.0)
            )
        },
        preview = PreviewData(2, null, 2, null, null, null), result = null
    )
}
''')

print("v0.15.13 patch applied")
