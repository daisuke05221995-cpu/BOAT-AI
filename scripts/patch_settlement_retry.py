from pathlib import Path

path = Path('app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt')
text = path.read_text(encoding='utf-8')

anchor = '''    @SuppressLint("ScheduleExactAlarm")
    private fun schedule(
        triggerAtMillis: Long,
        requestCode: Int,
        action: String,
        race: RaceData? = null
    ) {
        val intent = Intent(context, PredictionTrackingReceiver::class.java).apply {
            this.action = action
            race?.let {
                putExtra(EXTRA_RACE_ID, it.id)
                putExtra(EXTRA_DATE, it.date.take(10))
            }
        }
'''
replacement = '''    fun scheduleSettleRetry(dateText: String, raceId: String, currentAttempt: Int) {
        if (!SettlementRetryPolicy.shouldRetry(currentAttempt, true)) return
        val nextAttempt = SettlementRetryPolicy.nextAttempt(currentAttempt)
        schedule(
            System.currentTimeMillis() + SettlementRetryPolicy.RETRY_DELAY_MINUTES * 60_000L,
            raceId.hashCode() xor SETTLE_RETRY_REQUEST_XOR xor nextAttempt,
            ACTION_SETTLE,
            dateText = dateText.take(10),
            raceId = raceId,
            settleAttempt = nextAttempt
        )
    }

    @SuppressLint("ScheduleExactAlarm")
    private fun schedule(
        triggerAtMillis: Long,
        requestCode: Int,
        action: String,
        race: RaceData? = null,
        dateText: String? = null,
        raceId: String? = null,
        settleAttempt: Int = 0
    ) {
        val intent = Intent(context, PredictionTrackingReceiver::class.java).apply {
            this.action = action
            race?.let {
                putExtra(EXTRA_RACE_ID, it.id)
                putExtra(EXTRA_DATE, it.date.take(10))
            }
            dateText?.takeIf { it.isNotBlank() }?.let { putExtra(EXTRA_DATE, it.take(10)) }
            raceId?.takeIf { it.isNotBlank() }?.let { putExtra(EXTRA_RACE_ID, it) }
            if (action == ACTION_SETTLE) putExtra(EXTRA_SETTLE_ATTEMPT, settleAttempt)
        }
'''
if anchor not in text:
    raise SystemExit('schedule anchor not found')
text = text.replace(anchor, replacement, 1)

companion_anchor = '''        const val EXTRA_RACE_ID = "tracking_race_id"
        const val EXTRA_DATE = "tracking_date"
        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking_visual_only_v4"
'''
companion_replacement = '''        const val EXTRA_RACE_ID = "tracking_race_id"
        const val EXTRA_DATE = "tracking_date"
        const val EXTRA_SETTLE_ATTEMPT = "tracking_settle_attempt"
        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking_visual_only_v4"
'''
if companion_anchor not in text:
    raise SystemExit('companion extra anchor not found')
text = text.replace(companion_anchor, companion_replacement, 1)

xor_anchor = '''        private const val EVALUATE_REQUEST_XOR = 0x36B1
        private const val SETTLE_REQUEST_XOR = 0x51A7
'''
xor_replacement = '''        private const val EVALUATE_REQUEST_XOR = 0x36B1
        private const val SETTLE_REQUEST_XOR = 0x51A7
        private const val SETTLE_RETRY_REQUEST_XOR = 0x6C2D
'''
if xor_anchor not in text:
    raise SystemExit('xor anchor not found')
text = text.replace(xor_anchor, xor_replacement, 1)

receiver_anchor = '''            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
'''
receiver_replacement = '''            putExtra(PredictionTrackingScheduler.EXTRA_RACE_ID, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID))
            putExtra(PredictionTrackingScheduler.EXTRA_DATE, intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE))
            putExtra(
                PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT,
                intent.getIntExtra(PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT, 0)
            )
'''
if receiver_anchor not in text:
    raise SystemExit('receiver anchor not found')
text = text.replace(receiver_anchor, receiver_replacement, 1)

service_anchor = '''                    PredictionTrackingScheduler.ACTION_SETTLE -> settleDate(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE)
                    )
'''
service_replacement = '''                    PredictionTrackingScheduler.ACTION_SETTLE -> settleDate(
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_DATE),
                        intent.getStringExtra(PredictionTrackingScheduler.EXTRA_RACE_ID),
                        intent.getIntExtra(PredictionTrackingScheduler.EXTRA_SETTLE_ATTEMPT, 0)
                    )
'''
if service_anchor not in text:
    raise SystemExit('service settle anchor not found')
text = text.replace(service_anchor, service_replacement, 1)

settle_anchor = '''    private suspend fun settleDate(dateText: String?) {
        if (dateText.isNullOrBlank()) return
        val date = runCatching { LocalDate.parse(dateText.take(10)) }.getOrNull() ?: return
        val races = runCatching { BoatRaceRepository().loadDate(date) }.getOrNull() ?: return
        PredictionHistoryStore(this).settle(races)
        BetStore(this).settle(races)
    }
'''
settle_replacement = '''    private suspend fun settleDate(dateText: String?, raceId: String?, attempt: Int) {
        if (dateText.isNullOrBlank()) return
        val normalizedDate = dateText.take(10)
        val date = runCatching { LocalDate.parse(normalizedDate) }.getOrNull() ?: return
        val predictionStore = PredictionHistoryStore(this)
        val betStore = BetStore(this)

        fun hasPendingTarget(): Boolean {
            if (raceId.isNullOrBlank()) return false
            val predictionPending = predictionStore.load().any { record ->
                !record.settled && record.id == raceId
            }
            val purchasePending = betStore.load().any { bet ->
                !bet.settled &&
                    "${bet.date.take(10)}-${Venues.code(bet.stadiumNumber)}-${bet.raceNumber}" == raceId
            }
            return predictionPending || purchasePending
        }

        val pendingBeforeFetch = hasPendingTarget()
        val races = runCatching { BoatRaceRepository().loadDate(date) }.getOrNull()
        if (races == null) {
            if (pendingBeforeFetch && !raceId.isNullOrBlank()) {
                PredictionTrackingScheduler(this).scheduleSettleRetry(normalizedDate, raceId, attempt)
            }
            return
        }

        predictionStore.settle(races)
        betStore.settle(races)

        if (hasPendingTarget() && !raceId.isNullOrBlank()) {
            PredictionTrackingScheduler(this).scheduleSettleRetry(normalizedDate, raceId, attempt)
        }
    }
'''
if settle_anchor not in text:
    raise SystemExit('settleDate anchor not found')
text = text.replace(settle_anchor, settle_replacement, 1)

path.write_text(text, encoding='utf-8')
print('Patched bounded settlement retries into PredictionTrackingScheduler.')
