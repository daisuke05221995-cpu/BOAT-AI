package jp.boatai.app

import android.app.Activity
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId

data class BoatUiState(
    val date: LocalDate = LocalDate.now(ZoneId.of("Asia/Tokyo")),
    val races: List<RaceData> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val selectedRace: RaceData? = null,
    val selectedVenue: Int? = null,
    val predictions: List<PredictionPick> = emptyList(),
    val oddsLoading: Boolean = false,
    val oddsError: String? = null,
    val oddsUpdatedAt: Long? = null,
    val records: List<BetRecord> = emptyList(),
    val predictionHistory: List<PredictionRecord> = emptyList(),
    val selectedForBulk: Set<String> = emptySet(),
    val stakePerPick: Int = 300,
    val tab: Int = 0,
    val lastUpdatedAt: Long? = null,
    val actionMessage: String? = null,
    val learnedRaceCount: Int = 0,
    val update: AppUpdateState = AppUpdateState()
)

class BoatViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = BoatRaceRepository()
    private val betStore = BetStore(application)
    private val predictionStore = PredictionHistoryStore(application)
    private val appUpdateManager = AppUpdateManager(application)
    private val learningStore = LearningStore(application)
    private val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))
    private var oddsRefreshJob: Job? = null

    private val _ui = MutableStateFlow(
        BoatUiState(
            records = betStore.load(),
            predictionHistory = predictionStore.load()
        )
    )
    val ui: StateFlow<BoatUiState> = _ui.asStateFlow()

    init {
        val initialLearning = learningStore.load()
        PredictionEngine.installLearningProfile(initialLearning)
        _ui.update { it.copy(learnedRaceCount = initialLearning.observedRaceIds.size) }
        viewModelScope.launch {
            appUpdateManager.state.collectLatest { updateState ->
                _ui.update { it.copy(update = updateState) }
            }
        }
        viewModelScope.launch {
            appUpdateManager.checkForUpdates()
        }
        loadDate(_ui.value.date)
    }

    fun loadDate(date: LocalDate) {
        if (date.isAfter(today)) return
        viewModelScope.launch {
            _ui.update {
                it.copy(
                    date = date,
                    loading = true,
                    error = null,
                    selectedRace = null,
                    selectedVenue = null,
                    predictions = emptyList(),
                    selectedForBulk = emptySet(),
                    actionMessage = null
                )
            }
            runCatching { repository.loadDate(date) }
                .onSuccess { races ->
                    val records = betStore.settle(races)
                    predictionStore.captureOpenRaces(races)
                    val predictionHistory = predictionStore.settle(races)
                    val learning = learningStore.observe(races)
                    PredictionEngine.installLearningProfile(learning)
                    _ui.update {
                        it.copy(
                            races = races,
                            records = records,
                            predictionHistory = predictionHistory,
                            loading = false,
                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis(),
                            learnedRaceCount = learning.observedRaceIds.size
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update {
                        it.copy(
                            loading = false,
                            error = error.message ?: "データ取得に失敗しました"
                        )
                    }
                }
        }
    }

    fun previousDay() = loadDate(_ui.value.date.minusDays(1))
    fun nextDay() = loadDate(_ui.value.date.plusDays(1))
    fun refresh() = loadDate(_ui.value.date)

    fun selectRace(race: RaceData) {
        val initial = PredictionEngine.predict(race)
        _ui.update {
            it.copy(
                selectedRace = race,
                predictions = initial,
                oddsLoading = true,
                oddsError = null,
                error = null,
                actionMessage = null
            )
        }
        oddsRefreshJob?.cancel()
        loadOdds(race, initial)
        if (race.isPurchasable()) {
            oddsRefreshJob = viewModelScope.launch {
                while (_ui.value.selectedRace?.id == race.id && race.isPurchasable()) {
                    delay(60_000)
                    loadOdds(race, initial, showLoading = false)
                }
            }
        }
    }

    private fun loadOdds(race: RaceData, initial: List<PredictionPick>, showLoading: Boolean = true) {
        if (showLoading) _ui.update { it.copy(oddsLoading = true, oddsError = null) }
        viewModelScope.launch {
            runCatching {
                repository.loadOfficialTrifectaOdds(race, initial.map { it.combination })
            }
                .onSuccess { odds ->
                    _ui.update { state ->
                        state.copy(
                            predictions = PredictionEngine.withOdds(initial, odds),
                            oddsLoading = false,
                            oddsUpdatedAt = System.currentTimeMillis(),
                            oddsError = null
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update { state ->
                        state.copy(oddsLoading = false, oddsError = error.message ?: "オッズ取得失敗")
                    }
                }
        }
    }

    fun retryOdds() {
        val race = _ui.value.selectedRace ?: return
        loadOdds(race, PredictionEngine.predict(race))
    }

    fun selectVenue(stadiumNumber: Int) {
        _ui.update { it.copy(selectedVenue = stadiumNumber, actionMessage = null) }
    }

    fun closeVenue() {
        _ui.update { it.copy(selectedVenue = null, selectedForBulk = emptySet(), actionMessage = null) }
    }

    fun closeRace() {
        oddsRefreshJob?.cancel()
        _ui.update {
            it.copy(
                selectedRace = null,
                predictions = emptyList(),
                oddsLoading = false,
                actionMessage = null
            )
        }
    }

    fun selectVenuePurchasable(stadiumNumber: Int) {
        val ids = _ui.value.races.filter {
            it.stadiumNumber == stadiumNumber && it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty()
        }.mapTo(linkedSetOf()) { it.id }
        _ui.update { it.copy(selectedForBulk = ids, actionMessage = null) }
    }

    fun selectVenueTop(stadiumNumber: Int, count: Int = 3) {
        val ids = _ui.value.races.filter {
            it.stadiumNumber == stadiumNumber && it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty()
        }.sortedByDescending(PredictionEngine::confidence).take(count).mapTo(linkedSetOf()) { it.id }
        _ui.update { it.copy(selectedForBulk = ids, actionMessage = null) }
    }

    fun selectConfidenceAtLeast(minimum: Int) {
        val ids = _ui.value.races.filter {
            it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty() && PredictionEngine.confidence(it) >= minimum
        }.mapTo(linkedSetOf()) { it.id }
        _ui.update {
            it.copy(
                selectedForBulk = ids,
                actionMessage = if (ids.isEmpty()) "AI期待度${minimum}以上の対象レースはありません" else null
            )
        }
    }

    fun setTab(tab: Int) {
        _ui.update {
            it.copy(
                tab = tab.coerceIn(0, 2),
                selectedRace = null,
                selectedVenue = null,
                predictions = emptyList(),
                actionMessage = null
            )
        }
    }

    fun increaseStake() {
        _ui.update { it.copy(stakePerPick = (it.stakePerPick + 100).coerceAtMost(3000)) }
    }

    fun decreaseStake() {
        _ui.update { it.copy(stakePerPick = (it.stakePerPick - 100).coerceAtLeast(100)) }
    }

    fun toggleBulkRace(raceId: String) {
        val race = _ui.value.races.firstOrNull { it.id == raceId } ?: return
        if (!race.isPurchasable()) return
        _ui.update { state ->
            val next = state.selectedForBulk.toMutableSet()
            if (!next.add(raceId)) next.remove(raceId)
            state.copy(selectedForBulk = next, actionMessage = null)
        }
    }

    fun selectAllPurchasable() {
        val ids = _ui.value.races
            .filter { it.isPurchasable() && PredictionEngine.predict(it).isNotEmpty() }
            .mapTo(linkedSetOf()) { it.id }
        _ui.update { it.copy(selectedForBulk = ids, actionMessage = null) }
    }

    fun clearBulkSelection() {
        _ui.update { it.copy(selectedForBulk = emptySet(), actionMessage = null) }
    }

    fun recordSelectedRaces() {
        val state = _ui.value
        val races = state.races.filter {
            it.id in state.selectedForBulk && it.isPurchasable()
        }
        if (races.isEmpty()) {
            _ui.update { it.copy(actionMessage = "購入するレースを選択してください") }
            return
        }

        val before = state.records.size
        val records = betStore.addRacePicks(races, state.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                selectedForBulk = emptySet(),
                actionMessage = "${races.size}レース / ${addedTickets}点を購入記録に追加しました"
            )
        }
    }

    fun recordRace(race: RaceData) {
        if (!race.isPurchasable()) return
        val picks = PredictionEngine.predict(race)
        if (picks.isEmpty()) return
        val before = _ui.value.records.size
        val records = betStore.addPicks(race, picks, _ui.value.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました"
                } else {
                    "${race.venueName} ${race.raceNumber}Rはすでに購入記録済みです"
                }
            )
        }
    }

    fun recordPredictions() {
        val state = _ui.value
        val race = state.selectedRace ?: return
        if (state.predictions.isEmpty() || !race.isPurchasable()) return
        val before = state.records.size
        val records = betStore.addPicks(race, state.predictions, state.stakePerPick)
        val addedTickets = (records.size - before).coerceAtLeast(0)
        _ui.update {
            it.copy(
                records = records,
                actionMessage = if (addedTickets > 0) {
                    "${race.venueName} ${race.raceNumber}Rを${addedTickets}点、購入記録に追加しました"
                } else {
                    "このレースはすでに購入記録済みです"
                }
            )
        }
    }

    fun clearRecords() {
        _ui.update {
            it.copy(
                records = betStore.clear(),
                actionMessage = "実購入の記録を削除しました"
            )
        }
    }

    fun checkForAppUpdate() {
        viewModelScope.launch {
            appUpdateManager.checkForUpdates(userInitiated = true)
        }
    }

    fun downloadAndInstallUpdate(activity: Activity) {
        viewModelScope.launch {
            appUpdateManager.downloadAndInstall(activity)
        }
    }

    fun resumePendingInstall(activity: Activity) {
        appUpdateManager.resumePendingInstall(activity)
    }
}
