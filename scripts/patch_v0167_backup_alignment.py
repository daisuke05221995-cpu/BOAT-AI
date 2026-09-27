from pathlib import Path

PATH = Path('app/src/main/java/jp/boatai/app/DataBackupManager.kt')
text = PATH.read_text(encoding='utf-8')

old_export = '''    fun backupJson(): String {
        val bets = context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .getString("records", "[]") ?: "[]"
        val predictions = context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .getString("prediction_records", "[]") ?: "[]"
        val learningPrefs = context.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)
        val learning = learningPrefs.getString("profile", "{}") ?: "{}"
        return JSONObject().apply {
            put("schemaVersion", 1)
            put("appVersion", BuildConfig.VERSION_NAME)
            put("exportedAt", Instant.now().toString())
            put("bets", JSONArray(bets))
            put("predictions", JSONArray(predictions))
            put("learning", JSONObject(learning))
            put("historicalBaselineMigratedThrough", learningPrefs.getString("historical_baseline_migrated_through", ""))
        }.toString(2)
    }
'''
new_export = '''    fun backupJson(): String {
        // Read through the stores instead of raw SharedPreferences so their ledger-recovery
        // path can heal a malformed primary payload before we export the user's history.
        val bets = JSONArray().apply {
            BetStore(context).load().forEach { put(it.toJson()) }
        }
        val predictions = JSONArray().apply {
            PredictionHistoryStore(context).load().forEach { put(it.toJson()) }
        }
        val learningPrefs = context.getSharedPreferences("boat_ai_learning", Context.MODE_PRIVATE)
        val learning = learningPrefs.getString("profile", "{}") ?: "{}"
        return JSONObject().apply {
            put("schemaVersion", 1)
            put("appVersion", BuildConfig.VERSION_NAME)
            put("exportedAt", Instant.now().toString())
            put("bets", bets)
            put("predictions", predictions)
            put("learning", JSONObject(learning))
            put("historicalBaselineMigratedThrough", learningPrefs.getString("historical_baseline_migrated_through", ""))
        }.toString(2)
    }
'''
if old_export not in text:
    raise SystemExit('backupJson anchor not found; refusing unsafe patch')
text = text.replace(old_export, new_export, 1)

old_restore = '''        context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .edit().putString("records", bets.toString()).commit()
        context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .edit().putString("prediction_records", predictions.toString()).commit()
'''
new_restore = '''        val betsPayload = bets.toString()
        val predictionsPayload = predictions.toString()
        // Imported data has already been fully parsed above, so seed both the primary and the
        // recovery copy with the same known-good payload. This prevents a stale pre-import
        // backup from being resurrected if the primary preference is later damaged.
        context.getSharedPreferences("boat_ai_bets", Context.MODE_PRIVATE)
            .edit()
            .putString("records", betsPayload)
            .putString("records_backup", betsPayload)
            .commit()
        context.getSharedPreferences("boat_ai_predictions", Context.MODE_PRIVATE)
            .edit()
            .putString("prediction_records", predictionsPayload)
            .putString("prediction_records_backup", predictionsPayload)
            .commit()
'''
if old_restore not in text:
    raise SystemExit('restore anchor not found; refusing unsafe patch')
text = text.replace(old_restore, new_restore, 1)

PATH.write_text(text, encoding='utf-8')
print('Patched backup export/restore to align with ledger recovery.')
