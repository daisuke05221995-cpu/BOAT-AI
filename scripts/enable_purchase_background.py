#!/usr/bin/env python3
from pathlib import Path
p=Path('app/src/main/AndroidManifest.xml')
t=p.read_text()
changes={
'''        <service
            android:name=".AlertEvaluationService"
            android:enabled="false"
''':'''        <service
            android:name=".AlertEvaluationService"
            android:enabled="true"
''',
'''        <receiver
            android:name=".BoatNotificationReceiver"
            android:enabled="false"
''':'''        <receiver
            android:name=".BoatNotificationReceiver"
            android:enabled="true"
''',
'''        <receiver
            android:name=".ExactAlarmPermissionReceiver"
            android:enabled="false"
''':'''        <receiver
            android:name=".ExactAlarmPermissionReceiver"
            android:enabled="true"
''',
'''        <receiver
            android:name=".BoatAlertBootRecoveryReceiver"
            android:enabled="false"
''':'''        <receiver
            android:name=".BoatAlertBootRecoveryReceiver"
            android:enabled="true"
''',
}
for old,new in changes.items():
    if t.count(old)!=1: raise SystemExit(f'expected one manifest match: {old!r}')
    t=t.replace(old,new,1)
p.write_text(t)
print('purchase alert background components enabled; prediction tracker remains disabled')
