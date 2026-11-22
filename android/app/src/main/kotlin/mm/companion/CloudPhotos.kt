package mm.companion

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import mm.core.XmpFields
import mm.core.readFields
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId

/**
 * Photos in OneDrive's Camera Roll, browsed straight from OneDrive. What's listed, small pictures and opened
 * photos are kept on the phone (the app's cache), so they're still there with no connection; changes are made
 * to the phone's copy and queued for OneDrive like every other change (SyncQueue).
 */
class CloudPhotos(private val context: Context, private val drive: OneDrive) {
    private val dir = File(context.cacheDir, "onedrive").apply { mkdirs() }
    private val prefs = context.getSharedPreferences("onedrive", Context.MODE_PRIVATE)

    /** OneDrive only on Wi-Fi (Settings). */
    var wifiOnly: Boolean
        get() = prefs.getBoolean("wifi_only", false)
        set(value) = prefs.edit().putBoolean("wifi_only", value).apply()

    /** OneDrive can be used now: connected, and on Wi-Fi if that's asked for. */
    fun online(): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        val caps = cm.getNetworkCapabilities(cm.activeNetwork) ?: return false
        if (!caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)) return false
        return !wifiOnly || caps.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED)
    }

    fun unmetered(): Boolean {
        val cm = context.getSystemService(ConnectivityManager::class.java) ?: return false
        return cm.getNetworkCapabilities(cm.activeNetwork)?.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_METERED) == true
    }

    fun whyOffline(): String = if (wifiOnly) "Not on Wi-Fi (OneDrive is set to Wi-Fi only)" else "No internet connection"

    // ---------------------------------------------------------------- folders
    /** Camera Roll and its folders (years, and their months), from OneDrive, or as last seen. */
    fun folders(online: Boolean): List<Folder> {
        val saved = File(dir, "folders.json")
        if (online) {
            val root = drive.cameraRoll()
            val out = mutableListOf<Folder>()
            val top = drive.children(root.id)
            out.add(Folder(CLOUD + root.id, "Camera Roll", top.count { !it.folder }))
            for (y in top.filter { it.folder }.sortedByDescending { it.name }) {
                val inside = drive.children(y.id)
                val subs = inside.filter { it.folder }.sortedByDescending { it.name }
                if (inside.any { !it.folder } || subs.isEmpty()) {
                    out.add(Folder(CLOUD + y.id, "Camera Roll › ${y.name}", inside.count { !it.folder }))
                }
                subs.forEach { m -> out.add(Folder(CLOUD + m.id, "Camera Roll › ${y.name} › ${m.name}", m.childCount)) }
            }
            saved.writeText(JSONArray(out.map { JSONObject().put("id", it.id).put("name", it.name).put("count", it.count) }).toString())
            return out
        }
        if (!saved.exists()) throw IOException(whyOffline())
        val a = JSONArray(saved.readText())
        return (0 until a.length()).map { a.getJSONObject(it) }.map { Folder(it.getString("id"), it.getString("name"), it.getInt("count")) }
    }

    // ---------------------------------------------------------------- photos
    /** The photos in a folder (newest first), from OneDrive, or as last seen. */
    fun photos(folder: Folder, online: Boolean): List<Photo> {
        val id = folder.id.removePrefix(CLOUD)
        val saved = File(dir, "list-$id.json")
        val entries: JSONArray = if (online) {
            val a = JSONArray()
            drive.children(id).filter { !it.folder && it.mime.startsWith("image/") }.forEach { e ->
                a.put(JSONObject().put("id", e.id).put("name", e.name).put("mime", e.mime).put("taken", e.taken ?: "")
                    .put("modified", e.modified).put("tag", e.tag))
            }
            saved.writeText(a.toString())
            a
        } else {
            if (!saved.exists()) throw IOException(whyOffline())
            JSONArray(saved.readText())
        }
        return (0 until entries.length()).map { entries.getJSONObject(it) }.map { o ->
            val item = o.getString("id")
            val name = o.getString("name")
            val modified = runCatching { Instant.parse(o.getString("modified")).epochSecond }.getOrDefault(0L)
            Photo(cloudPhotoId(item), file(item, o.getString("tag"), name).path, name,
                wallTime(o.optString("taken"))?.atZone(ZoneId.systemDefault())?.toInstant()?.toEpochMilli() ?: 0L,
                modified, o.getString("mime"), cloudId = item)
        }.sortedByDescending { if (it.takenMillis > 0) it.takenMillis else it.modified * 1000 }
    }

    /** Where the phone keeps its copy: one per version of the file in OneDrive (a newer one is downloaded again,
     *  and changes made here stay in this one until they're uploaded). */
    private fun file(item: String, tag: String, name: String): File =
        File(dir, "photos/$item/${fnv(tag).toULong().toString(16)}.${name.substringAfterLast('.', "jpg").lowercase()}")

    fun isLocal(p: Photo) = File(p.path).exists()

    /** Downloads the photo if the phone doesn't have it yet. */
    fun fetch(p: Photo) {
        val f = File(p.path)
        if (f.exists()) return
        f.parentFile?.listFiles()?.forEach { it.delete() }  // an older version
        f.parentFile?.mkdirs()
        val tmp = File(f.path + ".part")
        tmp.writeBytes(drive.download(p.cloudId!!))
        tmp.renameTo(f)
    }

    /** Forget the phone's copy (deleted). */
    fun forget(p: Photo) {
        File(p.path).parentFile?.deleteRecursively()
        thumbFile(p).delete()
    }

    fun thumbnail(p: Photo, online: Boolean): Bitmap? {
        val f = File(p.path)
        if (f.exists()) return runCatching { decodePreview(f.readBytes(), 320) }.getOrNull()  // changed here: as it is now
        val t = thumbFile(p)
        if (!t.exists()) {
            if (!online) return null
            val bmp = decodePreview(drive.thumbnail(p.cloudId!!), 320) ?: return null
            t.parentFile?.mkdirs()
            t.outputStream().use { bmp.compress(Bitmap.CompressFormat.JPEG, 85, it) }
            return bmp
        }
        return BitmapFactory.decodeFile(t.path)
    }

    private fun thumbFile(p: Photo) = File(dir, "thumbs/${p.cloudId}-${File(p.path).nameWithoutExtension}.jpg")

    /** The tags, from the start of the file in OneDrive (not downloaded yet). */
    fun fields(p: Photo): XmpFields {
        if (!p.canChange) return XmpFields()
        val head = drive.head(p.cloudId!!, if (p.isPng) 4 * 1024 * 1024 else 256 * 1024)
        return runCatching { readFields(head) }.getOrDefault(XmpFields())
    }

    companion object {
        const val CLOUD = "cloud:"

        /** A photo id for a OneDrive file (negative, so never the same as a phone photo's). */
        fun cloudPhotoId(item: String): Long = fnv(item) or Long.MIN_VALUE

        fun fnv(s: String): Long {
            var h = -0x340d631b7bdddcdbL
            for (c in s) { h = h xor c.code.toLong(); h *= 0x100000001b3L }
            return h
        }

        /** OneDrive's date taken is the camera's clock time (marked as UTC). */
        fun wallTime(text: String?): LocalDateTime? = text?.takeIf { it.isNotEmpty() }?.let {
            runCatching { LocalDateTime.parse(it.removeSuffix("Z").substringBefore('+').take(19)) }.getOrNull()
        }
    }
}
