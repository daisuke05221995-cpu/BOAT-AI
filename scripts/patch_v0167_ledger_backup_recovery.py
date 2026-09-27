from pathlib import Path

BET = Path('app/src/main/java/jp/boatai/app/BetStore.kt')
PRED = Path('app/src/main/java/jp/boatai/app/PredictionHistoryStore.kt')

bet = BET.read_text(encoding='utf-8')
old_bet_load = '''    fun load(): List<BetRecord> {
        val raw = prefs.getString(KEY, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(BetRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrDefault(emptyList())
    }
'''
new_bet_load = '''    fun load(): List<BetRecord> {
        val raw = prefs.getString(KEY, null)
        decode(raw)?.let { return it }

        // Cumulative real-money records are too important to silently become empty when a
        // SharedPreferences payload is damaged. Fall back to the previous known-good payload
        // and heal the primary copy for subsequent reads.
        val backupRaw = prefs.getString(BACKUP_KEY, null)
        val recovered = decode(backupRaw) ?: return emptyList()
        if (backupRaw != null) prefs.edit().putString(KEY, backupRaw).apply()
        return recovered
    }

    private fun decode(raw: String?): List<BetRecord>? {
        if (raw == null) return null
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(BetRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrNull()
    }
'''
if old_bet_load not in bet:
    raise SystemExit('BetStore load anchor not found')
bet = bet.replace(old_bet_load, new_bet_load, 1)

old_bet_tail = '''    fun clear(): List<BetRecord> {
        prefs.edit().remove(KEY).apply()
        return emptyList()
    }

    private fun save(records: List<BetRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    companion object {
        private const val KEY = "records"
    }
}'''
new_bet_tail = '''    fun clear(): List<BetRecord> {
        prefs.edit().remove(KEY).remove(BACKUP_KEY).apply()
        return emptyList()
    }

    private fun save(records: List<BetRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        val payload = array.toString()
        val current = prefs.getString(KEY, null)
        val editor = prefs.edit()
        if (current != null && decode(current) != null) {
            editor.putString(BACKUP_KEY, current)
        }
        editor.putString(KEY, payload).apply()
    }

    companion object {
        private const val KEY = "records"
        private const val BACKUP_KEY = "records_backup"
    }
}'''
if old_bet_tail not in bet:
    raise SystemExit('BetStore save/clear anchor not found')
bet = bet.replace(old_bet_tail, new_bet_tail, 1)
BET.write_text(bet, encoding='utf-8')

pred = PRED.read_text(encoding='utf-8')
old_pred_load = '''    fun load(): List<PredictionRecord> {
        val raw = prefs.getString(KEY, "[]") ?: "[]"
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(PredictionRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrDefault(emptyList())
    }
'''
new_pred_load = '''    fun load(): List<PredictionRecord> {
        val raw = prefs.getString(KEY, null)
        decode(raw)?.let { return it }

        // Preserve the audited AI ledger across a malformed primary preference payload.
        val backupRaw = prefs.getString(BACKUP_KEY, null)
        val recovered = decode(backupRaw) ?: return emptyList()
        if (backupRaw != null) prefs.edit().putString(KEY, backupRaw).apply()
        return recovered
    }

    private fun decode(raw: String?): List<PredictionRecord>? {
        if (raw == null) return null
        return runCatching {
            val array = JSONArray(raw)
            buildList {
                for (i in 0 until array.length()) {
                    val obj = array.optJSONObject(i) ?: continue
                    add(PredictionRecord.fromJson(obj))
                }
            }.sortedByDescending { it.createdAt }
        }.getOrNull()
    }
'''
if old_pred_load not in pred:
    raise SystemExit('PredictionHistoryStore load anchor not found')
pred = pred.replace(old_pred_load, new_pred_load, 1)

old_pred_tail = '''    private fun save(records: List<PredictionRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        prefs.edit().putString(KEY, array.toString()).apply()
    }

    companion object {
        const val DEFAULT_SIMULATION_STAKE = 300
        private const val KEY = "prediction_records"
    }
}'''
new_pred_tail = '''    private fun save(records: List<PredictionRecord>) {
        val array = JSONArray()
        records.forEach { array.put(it.toJson()) }
        val payload = array.toString()
        val current = prefs.getString(KEY, null)
        val editor = prefs.edit()
        if (current != null && decode(current) != null) {
            editor.putString(BACKUP_KEY, current)
        }
        editor.putString(KEY, payload).apply()
    }

    companion object {
        const val DEFAULT_SIMULATION_STAKE = 300
        private const val KEY = "prediction_records"
        private const val BACKUP_KEY = "prediction_records_backup"
    }
}'''
if old_pred_tail not in pred:
    raise SystemExit('PredictionHistoryStore save anchor not found')
pred = pred.replace(old_pred_tail, new_pred_tail, 1)
PRED.write_text(pred, encoding='utf-8')

print('Patched backup recovery for actual-purchase and audited prediction ledgers.')
