package com.voiceaistudio.mobile

import android.content.ActivityNotFoundException
import android.content.Intent
import android.provider.Settings
import android.speech.tts.TextToSpeech
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

class MainActivity : FlutterActivity() {
    private val systemChannel = "voice_ai_mobile/system"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, systemChannel).setMethodCallHandler { call, result ->
            when (call.method) {
                "openTtsSettings" -> launchIntent(Intent("com.android.settings.TTS_SETTINGS"), result)
                "installTtsData" -> launchIntent(Intent(TextToSpeech.Engine.ACTION_INSTALL_TTS_DATA), result)
                else -> result.notImplemented()
            }
        }
    }

    private fun launchIntent(intent: Intent, result: MethodChannel.Result) {
        try {
            startActivity(intent)
            result.success(null)
        } catch (_: ActivityNotFoundException) {
            try {
                startActivity(Intent(Settings.ACTION_SETTINGS))
                result.success(null)
            } catch (error: Exception) {
                result.error("settings_unavailable", "تعذر فتح إعدادات الصوت في هذا الهاتف.", error.message)
            }
        }
    }
}
