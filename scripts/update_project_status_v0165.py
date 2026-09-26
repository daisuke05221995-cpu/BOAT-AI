from pathlib import Path

p = Path("PROJECT_STATUS.md")
text = p.read_text()

replacements = {
    "更新日: 2026-09-25": "更新日: 2026-09-26",
    "- 公開版: **v0.16.3**": "- 公開版: **v0.16.5**",
    "- versionCode: **38** / versionName: **0.16.3**": "- versionCode: **40** / versionName: **0.16.5**",
    "- Release target commit: `7a3ffe365707c7a1a99b790b3c8eb0aabb45c4de`": "- Release target commit: `a401530f1e697c0ae86adac95dcc5b320cdf4ce1`",
    "- Build Run: `36101879628` SUCCESS": "- Build Run: `36238671361` SUCCESS",
    "- Signed Release Run: `36101879634` SUCCESS": "- Signed Release Run: `36238671351` SUCCESS",
    "- Release ID: `396356442`": "- Release ID: `397209702`",
    "- Release asset: `BOAT-AI-v0.16.3.apk` (13,678,970 bytes)": "- Release asset: `BOAT-AI-v0.16.5.apk` (13,678,970 bytes)",
    "- APK SHA-256: `f054736d1e83a6abb7f50cfb2e5a58f5ac6c41507d1adaad0b9efe1be6316c51`": "- APK SHA-256: `ca070f254f7a13ca423ac7ebe352dec1f604077a34e0079cf0345332121f1e46`",
}
for old, new in replacements.items():
    if text.count(old) != 1:
        raise SystemExit(f"PROJECT_STATUS anchor mismatch for: {old}")
    text = text.replace(old, new, 1)

anchor = "## Android v0.16.3\n"
if text.count(anchor) != 1:
    raise SystemExit("Android v0.16.3 anchor mismatch")
latest = """## Android v0.16.5 最新追加\n\n- v0.16.4で、ライブBUY/SKIP判定に使った公式オッズの取得時刻・取得元・取得件数・選択買い目オッズを `PredictionRecord` へ永続保存。\n- value-v1 のSKIPは旧4点フォールバックを捏造せず、実際のSKIPとして0円・空買い目で保存。\n- 結果画面にライブ判定時刻 / 取得元 / 取得件数 / 選択買い目オッズを表示。\n- v0.16.5で `LiveAuditedPerformance` を追加し、実ライブ成績と回顧仮想成績を完全分離。\n- ライブ監査済み成績へ入れる条件は、settled / evaluationEligible / BUY / value-v1 / 取得時刻 / 取得元 / 公式3連単120通り / 全選択買い目オッズ / 有効な100円単位配分が全て揃うこと。\n- 損益画面に「ライブ監査済みAI購入推奨」を追加し、的中数・購入額・払戻・損益・ROI・監査完備率・監査不足件数を表示。\n- 監査不足・旧ロジック・回顧データはライブ実績へ混ぜない。\n- `LiveAuditedPerformanceTest` で完全記録の採用と、不完全記録/119通り/別strategy/SKIP等の除外を固定。\n- Filter build `36238459254` SUCCESS / UI validation `36238486804` SUCCESS。\n- v0.16.5 Build `36238671361` SUCCESS / Signed Release `36238671351` SUCCESS。\n- 詳細引継ぎ: `data/V0165_AUDITED_LIVE_PERFORMANCE_HANDOFF_20260926.md`。\n\n### v0.16.5 次の具体的1手\n\n1. 既存アプリへv0.16.5を上書き更新。アンインストール・データ消去は禁止。\n2. 実開催でvalue-v1 BUY/SKIPを蓄積し、Resultsの監査行と損益のライブ監査済み件数を照合。\n3. 監査不足BUYが出た場合、120通り不足 / source欠落 / pick odds欠落など原因を画面上で診断できるよう強化。\n4. 新しい締切前スナップショットで未settled記録を更新しても、初回 `createdAt` を維持できることを実機確認。\n5. ライブ監査済み実績は回顧ROIと今後も分離し、実運用データだけで評価する。\n\n"""
text = text.replace(anchor, latest + anchor, 1)
p.write_text(text)
