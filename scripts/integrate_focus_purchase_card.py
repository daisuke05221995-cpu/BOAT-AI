from pathlib import Path

path = Path("app/src/main/java/jp/boatai/app/FocusPredictionCard.kt")
text = path.read_text()
old = "val session = PendingPurchaseSession.create(listOf(race to picks))"
new = "val session = PendingPurchaseSession.create(listOf(race to picks), mode.strategyId)"
if new in text:
    print("Focus purchase strategy id already wired")
elif old not in text:
    raise SystemExit("Focus purchase session insertion point not found")
else:
    path.write_text(text.replace(old, new, 1))
    print("Focus purchase strategy id wired")
