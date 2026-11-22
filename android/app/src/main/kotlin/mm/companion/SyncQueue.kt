package mm.companion

import android.content.Context
import mm.core.Change
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.UUID

/**
 * Changes waiting to be done to the OneDrive copy of a photo (so the PC gets them). Kept in a file, so
 * nothing is lost if the app closes or the phone is offline; done in order, one photo at a time.
 */
data class QueueEntry(
    val id: String,
    val photoId: Long,         // the phone's photo (Android media id)
    val name: String,          // its name when the change was made (to find it in OneDrive)
    val originalName: String,  // the name the camera gave it (OneDrive's camera upload keeps that)
    val taken: String,         // its date taken "yyyy:MM:dd HH:mm:ss" (to find it if renamed on the PC)
    val change: Change,
    val created: Long,
    val error: String = "",
)

fun Change.toJson(): JSONObject = JSONObject().apply {
    when (val c = this@toJson) {
        is Change.Keywords -> { put("type", "keywords"); put("add", JSONArray(c.add)); put("remove", JSONArray(c.remove)) }
        is Change.Label -> { put("type", "label"); put("label", c.label) }
        is Change.Flag -> { put("type", "flag"); put("flag", c.flag); put("on", c.on) }
        Change.ClearLabels -> put("type", "clear")
        is Change.DateTaken -> { put("type", "date"); put("exif", c.exif) }
        is Change.Rename -> { put("type", "rename"); put("name", c.name) }
        is Change.Edit -> {
            put("type", "edit")
            put("adjustments", JSONObject(c.adjustments as Map<*, *>))
            c.crop?.let { put("crop", JSONArray(it)) }
            c.turn?.let { put("turn", JSONArray(it)) }
        }
        Change.Delete -> put("type", "delete")
    }
}

private fun JSONArray.strings() = (0 until length()).map { getString(it) }

fun changeFromJson(o: JSONObject): Change = when (o.getString("type")) {
    "keywords" -> Change.Keywords(o.getJSONArray("add").strings(), o.getJSONArray("remove").strings())
    "label" -> Change.Label(o.getString("label"))
    "flag" -> Change.Flag(o.getString("flag"), o.getBoolean("on"))
    "clear" -> Change.ClearLabels
    "date" -> Change.DateTaken(o.getString("exif"))
    "rename" -> Change.Rename(o.getString("name"))
    "edit" -> {
        val a = o.getJSONObject("adjustments")
        Change.Edit(a.keys().asSequence().associateWith { a.getInt(it) },
            o.optJSONArray("crop")?.let { arr -> (0 until arr.length()).map { arr.getDouble(it) } },
            o.optJSONArray("turn")?.let { arr -> (0 until arr.length()).map { arr.getInt(it) } })
    }
    "delete" -> Change.Delete
    else -> throw IllegalArgumentException(o.toString())
}

class SyncQueue(context: Context) {
    private val file = File(context.filesDir, "sync-queue.json")

    @Synchronized fun all(): List<QueueEntry> {
        if (!file.exists()) return emptyList()
        return try {
            val arr = JSONArray(file.readText())
            (0 until arr.length()).map { i ->
                val o = arr.getJSONObject(i)
                QueueEntry(o.getString("id"), o.getLong("photoId"), o.getString("name"), o.optString("originalName"),
                    o.optString("taken"), changeFromJson(o.getJSONObject("change")), o.getLong("created"),
                    o.optString("error"))
            }
        } catch (e: Exception) {
            emptyList()
        }
    }

    @Synchronized private fun save(entries: List<QueueEntry>) {
        val arr = JSONArray()
        for (e in entries) arr.put(JSONObject().apply {
            put("id", e.id); put("photoId", e.photoId); put("name", e.name); put("originalName", e.originalName)
            put("taken", e.taken); put("change", e.change.toJson()); put("created", e.created); put("error", e.error)
        })
        val tmp = File(file.parentFile, file.name + ".tmp")
        tmp.writeText(arr.toString())
        if (!tmp.renameTo(file)) {  // (renaming over the old file failed: write it in place)
            file.writeText(arr.toString())
            tmp.delete()
        }
    }

    @Synchronized fun add(photoId: Long, name: String, originalName: String, taken: String, change: Change) {
        save(all() + QueueEntry(UUID.randomUUID().toString(), photoId, name, originalName, taken, change,
            System.currentTimeMillis()))
    }

    @Synchronized fun remove(ids: Set<String>) = save(all().filterNot { it.id in ids })

    /** Forget everything waiting. */
    @Synchronized fun clear() {
        file.delete()
        File(file.parentFile, file.name + ".tmp").delete()
    }

    @Synchronized fun setError(ids: Set<String>, error: String) =
        save(all().map { if (it.id in ids) it.copy(error = error) else it })
}
