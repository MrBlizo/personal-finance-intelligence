package io.github.mrblizo.pfi

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * The Flutter activity, plus one channel ("pfi/launch") that tells the app
 * when it was opened from the home-screen widget or an app shortcut and
 * lets the app refresh the widget's balance.
 */
class MainActivity : FlutterActivity() {
    private var channel: MethodChannel? = null
    private var pending: String? = null

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        pending = actionOf(intent)
        channel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "pfi/launch").apply {
            setMethodCallHandler { call, result ->
                when (call.method) {
                    "takeAction" -> {
                        result.success(pending)
                        pending = null
                    }
                    "updateWidget" -> {
                        QuickAddWidget.save(
                            this@MainActivity,
                            call.argument<String>("title") ?: "",
                            call.argument<String>("value") ?: "",
                            call.argument<String>("add") ?: "Expense",
                            call.argument<String>("income") ?: "Income",
                        )
                        result.success(null)
                    }
                    else -> result.notImplemented()
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val action = actionOf(intent) ?: return
        val ch = channel
        if (ch == null) pending = action else ch.invokeMethod("action", action)
    }

    private fun actionOf(i: Intent?): String? = i?.getStringExtra(QuickAddWidget.EXTRA)
}
