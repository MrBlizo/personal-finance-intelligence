package io.github.mrblizo.pfi

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews

/** Home-screen widget: cash on hand and one-tap "add expense / income". */
class QuickAddWidget : AppWidgetProvider() {
    override fun onUpdate(context: Context, manager: AppWidgetManager, ids: IntArray) {
        ids.forEach { manager.updateAppWidget(it, views(context)) }
    }

    companion object {
        const val EXTRA = "pfi_action"
        private const val PREFS = "pfi_widget"

        /** Stores the texts the app sends and redraws every PFI widget. */
        fun save(context: Context, title: String, value: String, add: String, income: String) {
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString("title", title).putString("value", value)
                .putString("add", add).putString("income", income).apply()
            val manager = AppWidgetManager.getInstance(context)
            val ids = manager.getAppWidgetIds(ComponentName(context, QuickAddWidget::class.java))
            ids.forEach { manager.updateAppWidget(it, views(context)) }
        }

        private fun launch(context: Context, action: String, code: Int): PendingIntent {
            val intent = Intent(context, MainActivity::class.java).apply {
                this.action = "io.github.mrblizo.pfi.$action"
                putExtra(EXTRA, action)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP
            }
            return PendingIntent.getActivity(
                context, code, intent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }

        private fun views(context: Context): RemoteViews {
            val p = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            return RemoteViews(context.packageName, R.layout.quick_add_widget).apply {
                setTextViewText(R.id.widget_title, p.getString("title", "PFI"))
                setTextViewText(R.id.widget_value, p.getString("value", ""))
                setTextViewText(R.id.widget_add, "+  " + p.getString("add", "Expense"))
                setTextViewText(R.id.widget_income, "+  " + p.getString("income", "Income"))
                setOnClickPendingIntent(R.id.widget_root, launch(context, "open", 30))
                setOnClickPendingIntent(R.id.widget_add, launch(context, "expense", 31))
                setOnClickPendingIntent(R.id.widget_income, launch(context, "income", 32))
            }
        }
    }
}
