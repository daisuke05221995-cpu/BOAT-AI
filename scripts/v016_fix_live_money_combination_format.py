from pathlib import Path

EVAL = Path('scripts/v016_live_money_eval.py')
TEST = Path('scripts/v016_live_money_eval_test.py')
PROTOCOL = Path('data/v016_live_money_protocol.json')
REPORT = Path('data/v016_live_money_research_report.md')

text = EVAL.read_text(encoding='utf-8')
old = 'COMBINATION = re.compile(r"^[1-6]{3}$")\n'
new = '''COMBINATION = re.compile(r"^[1-6]-[1-6]-[1-6]$")\n\n\ndef valid_combination(value):\n    return (isinstance(value, str)\n            and COMBINATION.fullmatch(value) is not None\n            and len(set(value.split("-"))) == 3)\n'''
if old not in text:
    raise SystemExit('combination regex anchor not found')
text = text.replace(old, new, 1)

old = '    if any(not isinstance(p, str) or not COMBINATION.fullmatch(p) or len(set(p)) != 3 for p in record["combinations"]):\n'
new = '    if any(not valid_combination(p) for p in record["combinations"]):\n'
if old not in text:
    raise SystemExit('prediction combination validation anchor not found')
text = text.replace(old, new, 1)

old = '    if result is not None and (not isinstance(result, str) or not COMBINATION.fullmatch(result) or len(set(result)) != 3):\n'
new = '    if result is not None and not valid_combination(result):\n'
if old not in text:
    raise SystemExit('result combination validation anchor not found')
text = text.replace(old, new, 1)

old = '    if not isinstance(row["combination"], str) or not COMBINATION.fullmatch(row["combination"]) or len(set(row["combination"])) != 3:\n'
new = '    if not valid_combination(row["combination"]):\n'
if old not in text:
    raise SystemExit('actual purchase combination validation anchor not found')
text = text.replace(old, new, 1)
EVAL.write_text(text, encoding='utf-8')

# Synthetic fixtures must mirror the exact strings emitted by the Android app backup.
test = TEST.read_text(encoding='utf-8')
for before, after in [
    ('"123"', '"1-2-3"'),
    ('"234"', '"2-3-4"'),
    ('"345"', '"3-4-5"'),
]:
    test = test.replace(before, after)
TEST.write_text(test, encoding='utf-8')

protocol = PROTOCOL.read_text(encoding='utf-8')
needle = '    "moneyUnit": "JPY integers; trifectaPayout is JPY per 100 JPY ticket",\n'
replacement = needle + '    "combinationFormat": "Android backup exact format N-N-N, e.g. 1-2-3; three distinct lanes 1..6",\n'
if '"combinationFormat"' not in protocol:
    if needle not in protocol:
        raise SystemExit('protocol insertion anchor not found')
    protocol = protocol.replace(needle, replacement, 1)
PROTOCOL.write_text(protocol, encoding='utf-8')

report = REPORT.read_text(encoding='utf-8')
section = '''\n## 2026-09-27 Android backup format compatibility correction\n\nPost-merge cross-check against the Android `PredictionRecord`/`BetRecord` fixtures found that production backup combinations are serialized as `1-2-3`, while the first evaluator fixture used compact `123`. The evaluator and all synthetic fixtures now require the exact Android `N-N-N` format with three distinct lanes. This is a parser compatibility correction only; it does not change cohort, accounting, audit gates, profitability claims, or promotion rules.\n'''
if 'Android backup format compatibility correction' not in report:
    report += section
REPORT.write_text(report, encoding='utf-8')

print('Aligned research evaluator and fixtures with Android N-N-N combination strings.')
