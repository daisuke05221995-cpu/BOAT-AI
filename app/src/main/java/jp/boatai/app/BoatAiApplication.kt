package jp.boatai.app

import android.app.Application

class BoatAiApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        CrashRecoveryStore(this).installHandler()
    }
}
