#!/usr/bin/env python3
from pathlib import Path


def rep(text, old, new, label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'{label}: expected 1 match, got {n}')
    return text.replace(old,new,1)

manifest=Path('app/src/main/AndroidManifest.xml')
t=manifest.read_text()
for name in ('.PredictionTrackingService','.PredictionTrackingReceiver','.PredictionTrackingBootReceiver'):
    old=f'''            android:name="{name}"\n            android:enabled="false"\n'''
    new=f'''            android:name="{name}"\n            android:enabled="true"\n'''
    t=rep(t,old,new,f'enable {name}')
manifest.write_text(t)

main=Path('app/src/main/java/jp/boatai/app/MainActivity.kt')
t=main.read_text()
t=rep(t,
'''        super.onCreate(savedInstanceState)\n        enableEdgeToEdge()\n        setContent { BoatAiTheme { BoatAiApp(vm) } }\n''',
'''        super.onCreate(savedInstanceState)\n        enableEdgeToEdge()\n        runCatching {\n            PredictionTrackingScheduler(this).apply {\n                scheduleDailyBootstrap()\n                scheduleBootstrapSoon()\n            }\n        }.onFailure { CrashRecoveryStore(this).recordNonFatal("MainActivity.trackingBootstrap", it) }\n        setContent { BoatAiTheme { BoatAiApp(vm) } }\n''','safe tracking bootstrap')
main.write_text(t)
print('prediction tracking components re-enabled with safe app-launch scheduling')
