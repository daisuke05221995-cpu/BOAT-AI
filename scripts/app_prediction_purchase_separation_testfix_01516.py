#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'app/src/test/java/jp/boatai/app/RecommendationDecisionTest.kt'
text = path.read_text(encoding='utf-8')
old = '''    @Test
    fun strongRaceWithPreviewIsBuyRecommendation() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 8.0, 8.0, 50.0, 0.12, 6.70),
                racer(2, 4.5, 4.0, 25.0, 0.18, 6.84),
                racer(3, 4.2, 4.0, 25.0, 0.18, 6.86),
                racer(4, 4.0, 3.8, 24.0, 0.19, 6.88),
                racer(5, 3.8, 3.6, 23.0, 0.19, 6.90),
                racer(6, 3.5, 3.4, 22.0, 0.20, 6.92)
            )
        )

        assertEquals(RaceRecommendation.BUY, PredictionEngine.recommendation(race).recommendation)
    }
'''
new = '''    @Test
    fun strongRaceStillHasForecastWhileAutoPurchaseIsPaused() {
        resetProfiles()
        val race = race(
            racers = listOf(
                racer(1, 8.0, 8.0, 50.0, 0.12, 6.70),
                racer(2, 4.5, 4.0, 25.0, 0.18, 6.84),
                racer(3, 4.2, 4.0, 25.0, 0.18, 6.86),
                racer(4, 4.0, 3.8, 24.0, 0.19, 6.88),
                racer(5, 3.8, 3.6, 23.0, 0.19, 6.90),
                racer(6, 3.5, 3.4, 22.0, 0.20, 6.92)
            )
        )

        assertEquals(RaceRecommendation.SKIP, PredictionEngine.recommendation(race).recommendation)
        check(PredictionEngine.predict(race).isNotEmpty())
    }
'''
if text.count(old) != 1:
    raise SystemExit(f'expected old recommendation test exactly once, found {text.count(old)}')
path.write_text(text.replace(old, new, 1), encoding='utf-8')
print('recommendation test migrated for v0.15.16')
