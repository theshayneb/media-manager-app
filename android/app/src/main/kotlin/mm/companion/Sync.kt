package mm.companion

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mm.core.Adjustments
import mm.core.Change
import mm.core.DEFAULT_RENAME_PATTERN
import mm.core.DEFAULT_TEMPLATES
import mm.core.FilenameTemplate
import mm.core.applyTags
import mm.core.formatPattern
import org.json.JSONObject
import java.io.File
import java.time.LocalDateTime
import java.util.concurrent.TimeUnit

/** What the Windows app shares through OneDrive (companion.json), kept on the phone for when it's offline. */
class Shared(context: Context) {
    private val file = File(context.filesDir, "companion.json")
    private val json: JSONObject = runCatching { JSONObject(file.readText()) }.getOrDefault(JSONObject())

    fun save(text: String) { JSONObject(text); file.writeText(text) }

    val keywordSets: LinkedHashMap<String, List<String>>
        get() {
            val out = LinkedHashMap<String, List<String>>()
            val sets = json.optJSONObject("keyword_sets") ?: return out
            for (k in sets.keys()) { val a = sets.getJSONArray(k); out[k] = (0 until a.length()).map { a.getString(it) } }
            return out
        }
    val currentSet: String get() = json.optString("current_keyword_set", "")
    val renamePattern: String get() = json.optString("rename_pattern", DEFAULT_RENAME_PATTERN).ifBlank { DEFAULT_RENAME_PATTERN }
    val templates: List<FilenameTemplate>
        get() {
            val arr = json.optJSONArray("templates") ?: return DEFAULT_TEMPLATES
            return (0 until arr.length()).map { arr.getJSONObject(it) }
                .map { FilenameTemplate(it.optString("name"), it.optString("pattern"), it.optBoolean("utc")) }
                .ifEmpty { DEFAULT_TEMPLATES }
        }
    val lastEdit: Map<String, Int>
        get() = json.optJSONObject("last_edit")?.let { o -> o.keys().asSequence().associateWith { o.optInt(it) } } ?: emptyMap()
}

object Sync {
    private const val ONCE = "sync-now"
    private const val HOURLY = "sync-hourly"

    fun schedule(context: Context) {
        val online = Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
        val wm = WorkManager.getInstance(context)
        wm.enqueueUniqueWork(ONCE, ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<SyncWorker>().setConstraints(online).build())
        wm.enqueueUniquePeriodicWork(HOURLY, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<SyncWorker>(1, TimeUnit.HOURS).setConstraints(online).build())
    }
}

/** Does the queued changes to the OneDrive copies (in order; a photo not uploaded yet waits). */
class SyncWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val drive = OneDrive(applicationContext)
        if (!drive.signedIn) return@withContext Result.success()
        runCatching { drive.companion()?.let { Shared(applicationContext).save(it) } }
        val queue = SyncQueue(applicationContext)
        val shared = Shared(applicationContext)
        val ids = applicationContext.getSharedPreferences("onedrive-items", Context.MODE_PRIVATE)
        var waiting = false
        for ((photoId, entries) in queue.all().groupBy { it.photoId }) {
            try {
                val first = entries.first()
                val taken = runCatching { LocalDateTime.parse(first.taken, EXIF_DATE) }.getOrNull()
                var item = ids.getString(photoId.toString(), null)?.let { drive.itemById(it) }
                if (item == null) {
                    val patternName = taken?.let { formatPattern(shared.renamePattern, it) + "." + first.name.substringAfterLast('.', "jpg") }
                    item = drive.find(listOf(first.name, first.originalName), taken, listOfNotNull(patternName))
                }
                if (item == null) {
                    queue.setError(entries.map { it.id }.toSet(), "Not in OneDrive yet (waiting for camera upload)")
                    waiting = true
                    continue
                }
                val found = item
                ids.edit().putString(photoId.toString(), found.id).apply()
                var i = 0
                while (i < entries.size) {
                    val e = entries[i]
                    when (val c = e.change) {
                        is Change.Rename -> { drive.rename(found.id, c.name); i++ }
                        Change.Delete -> { drive.delete(found.id); ids.edit().remove(photoId.toString()).apply(); i++ }
                        else -> {
                            // a run of tag / date / edit changes: one download, one upload
                            var bytes = drive.download(found.id)
                            var j = i
                            while (j < entries.size && entries[j].change.let { it !is Change.Rename && it != Change.Delete }) {
                                bytes = applyToBytes(bytes, entries[j].change)
                                j++
                            }
                            drive.upload(found.id, bytes)
                            queue.remove(entries.subList(i, j).map { it.id }.toSet())
                            i = j
                            continue
                        }
                    }
                    queue.remove(setOf(e.id))
                }
            } catch (ex: Exception) {
                queue.setError(entries.map { it.id }.toSet(), ex.message ?: ex.toString())
                waiting = true
            }
        }
        if (waiting) Result.retry() else Result.success()
    }

    private fun applyToBytes(bytes: ByteArray, change: Change): ByteArray = when {
        change.isTag -> applyTags(bytes, change)
        change is Change.DateTaken -> {
            val tmp = File.createTempFile("date", ".jpg", applicationContext.cacheDir)
            try { tmp.writeBytes(bytes); setDateInFile(tmp, change.exif); tmp.readBytes() } finally { tmp.delete() }
        }
        change is Change.Edit -> editJpeg(bytes, Adjustments.fromMap(change.adjustments), change.crop)
        else -> bytes
    }
}
