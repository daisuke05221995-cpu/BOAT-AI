package jp.boatai.app

import android.app.Activity
import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch
import java.time.LocalDate
import java.time.ZoneId


data class BoatUiState(
    val date: LocalDate = LocalDate.now(ZoneId.of("Asia/Tokyo")),
    val races: List<RaceData> = emptyList(),
    val loading: Boolean = false,
    val error: String? = null,
    val selectedRace: RaceData? = null,
    val predictions: List<PredictionPick> = emptyList(),
    val oddsLoading: Boolean = false,
    val records: List<BetRecord> = emptyList(),
    val stakePerPick: Int = 300,
    val tab: Int = 0,
    val lastUpdatedAt: Long? = null,
    val update: AppUpdateState = AppUpdateState()
)

class BoatViewModel(application: Application) : AndroidViewModel(application) {
    private val repository = BoatRaceRepository()
    private val betStore = BetStore(application)
    private val appUpdateManager = AppUpdateManager(application)
    private val today = LocalDate.now(ZoneId.of("Asia/Tokyo"))

    private val _ui = MutableStateFlow(BoatUiState(records = betStore.load()))
    val ui: StateFlow<BoatUiState> = _ui.asStateFlow()

    init {
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
            _ui.update { it.copy(date = date, loading = true, error = null, selectedRace = null, predictions = emptyList()) }
            runCatching { repository.loadDate(date) }
                .onSuccess { races ->
                    val records = betStore.settle(races)
                    _ui.update {
                        it.copy(
                            races = races,
                            records = records,
                            loading = false,
                            error = if (races.isEmpty()) "この日のレースデータがありません" else null,
                            lastUpdatedAt = System.currentTimeMillis()
                        )
                    }
                }
                .onFailure { error ->
                    _ui.update { it.copy(loading = false, error = error.message ?: "データ取得に失敗しました") }
                }
        }
    }

    fun previousDay() = loadDate(_ui.value.date.minusDays(1))
    fun nextDay() = loadDate(_ui.value.date.plusDays(1))
    fun refresh() = loadDate(_ui.value.date)

    fun selectRace(race: RaceData) {
        val initial = PredictionEngine.predict(race)
        _ui.update { it.copy(selectedRace = race, predictions = initial, oddsLoading = true, error = null) }
        viewModelScope.launch {
            runCatching { repository.loadOfficialTrifectaOdds(race, initial.map { it.combination }) }
                .onSuccess { odds ->
                    _ui.update { state ->
                        state.copy(predictions = PredictionEngine.withOdds(initial, odds), oddsLoading = false)
                    }
                }
                .onFailure {
                    _ui.update { state -> state.copy(oddsLoading = false) }
                }
        }
    }

    fun closeRace() {
        _ui.update { it.copy(selectedRace = null, predictions = emptyList(), oddsLoading = false) }
    }

    fun setTab(tab: Int) {
        _ui.update { it.copy(tab = tab, selectedRace = null) }
    }

    fun increaseStake() {
        _ui.update { it.copy(stakePerPick = (it.stakePerPick + 100).coerceAtMost(1000)) }
    }

    fun decreaseStake() {
        _ui.update { it.copy(stakePerPick = (it.stakePerPick - 100).coerceAtLeast(100)) }
    }

    fun recordPredictions() {
        val state = _ui.value
        val race = state.selectedRace ?: return
        if (state.predictions.isEmpty()) return
        val records = betStore.addPicks(race, state.predictions, state.stakePerPick)
        _ui.update { it.copy(records = records) }
    }

    fun clearRecords() {
        _ui.update { it.copy(records = betStore.clear()) }
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
