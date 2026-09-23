#!/usr/bin/env python3
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 match, found {count}")
    return text.replace(old, new, 1)

p = Path('app/src/main/java/jp/boatai/app/NotificationScheduler.kt')
text = p.read_text()
text = replace_once(
    text,
    '        manager.createNotificationChannel(\n            NotificationChannel(CHANNEL, "レース・更新通知", NotificationManager.IMPORTANCE_DEFAULT)\n        )\n',
    '        manager.createNotificationChannel(\n            NotificationChannel(CHANNEL, "レース・更新通知（無音）", NotificationManager.IMPORTANCE_DEFAULT).apply {\n                description = "BOAT AIの画面通知です。音と振動は使用しません"\n                setSound(null, null)\n                enableVibration(false)\n            }\n        )\n',
    'generic silent channel'
)
text = replace_once(
    text,
    '        .setContentText(body)\n        .setAutoCancel(true)\n',
    '        .setContentText(body)\n        .setSilent(true)\n        .setAutoCancel(true)\n',
    'generic notification silent flag'
)
text = replace_once(text, '        const val CHANNEL = "boat_ai_events"\n',
                    '        const val CHANNEL = "boat_ai_events_visual_only_v4"\n', 'event channel id')
text = replace_once(text, '        const val ALERT_CHANNEL = "boat_ai_buy_alerts_silent_v2"\n',
                    '        const val ALERT_CHANNEL = "boat_ai_buy_alerts_visual_only_v4"\n', 'alert channel id')
text = replace_once(text, '        const val SERVICE_CHANNEL = "boat_ai_alert_checks_silent_v2"\n',
                    '        const val SERVICE_CHANNEL = "boat_ai_alert_checks_visual_only_v4"\n', 'alert service channel id')
p.write_text(text)

p = Path('app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt')
text = p.read_text()
text = replace_once(text, '        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking"\n',
                    '        const val SERVICE_CHANNEL = "boat_ai_prediction_tracking_visual_only_v4"\n', 'tracking service channel id')
p.write_text(text)
print('visual-only notification channel patch applied')
