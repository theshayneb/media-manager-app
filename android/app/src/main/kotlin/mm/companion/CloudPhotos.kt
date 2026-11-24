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
    /** Every folder in OneDrive's Pictures (Camera Roll among them), as a tree, from OneDrive or as last seen. */
    fun folders(online: Boolean): List<Folder> {
        val saved = File(dir, "pictures.json")
        if (online) {
            val out = mutableListOf<Folder>()
            fun walk(id: String, name: String, path: String, depth: Int) {
                val inside = drive.children(id)
                out.add(Folder(CLOUD + id, name, inside.count { !it.folder && it.mime.startsWith("image/") }, path, depth))
                if (depth >= 6 || out.size > 400) return  // (enough for any photo folder tree)
                // year and month folders newest first; others A–Z
                val subs = inside.filter { it.folder }.sortedWith(compareBy<OneDrive.Entry>(
                    { it.name.toIntOrNull()?.let { n -> -n } ?: Int.MAX_VALUE }, { it.name.lowercase() }))
                for (f in subs) walk(f.id, f.name, "$path/${f.name}", depth + 1)
            }
            val root = drive.pictures()
            walk(root.id, root.name, root.name, 0)
            saved.writeText(JSONArray(out.map {
                JSONObject().put("id", it.id).put("name", it.name).put("count", it.count).put("path", it.path).put("depth", it.depth)
            }).toString())
            return out
        }
        if (!saved.exists()) throw IOException(whyOffline())
        val a = JSONArray(saved.readText())
        return (0 until a.length()).map { a.getJSONObject(it) }.map {
            Folder(it.getString("id"), it.getString("name"), it.getInt("count"), it.optString("path"), it.optInt("depth"))
        }
    }

    fun newFolder(parent: Folder, name: String): String = drive.newFolder(parent.id.removePrefix(CLOUD), name)

    // ---------------------------------------------------------------- photos
    /** The photos in a folder (newest first), from OneDrive, or as last seen. */
    fun photos(folder: Folder, online: Boolean): List<Photo> {
        val id = folder.id.removePrefix(CLOUD)
        val saved = File(dir, "list-$id.json")
        val entries: JSONArray = if (online) {
            val a = JSONArray()
            drive.children(id).filter { !it.folder && it.mime.startsWith("image/") }.forEach { e ->
                // OneDrive hasn't read a date taken from it (yet; e.g. just changed): read it from the file.
                val taken = e.taken ?: runCatching { exifDate(drive.head(e.id, 128 * 1024))?.toString() }.getOrNull()
                a.put(JSONObject().put("id", e.id).put("name", e.name).put("mime", e.mime).put("taken", taken ?: "")
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
            val copy = file(item, o.getString("tag"), name)
            // The phone's copy's own date first (changed here, maybe not in OneDrive yet), then OneDrive's.
            val taken = (if (copy.exists()) runCatching { exifDate(copy.readBytes(128 * 1024)) }.getOrNull() else null)
                ?: wallTime(o.optString("taken"))
            Photo(cloudPhotoId(item), copy.path, name,
                taken?.atZone(ZoneId.systemDefault())?.toInstant()?.toEpochMilli() ?: 0L,
                modified, o.getString("mime"), cloudId = item)
        }.sortedByDescending { if (it.takenMillis > 0) it.takenMillis else it.modified * 1000 }
    }

    /** Where the phone keeps its copy: one per version of the file in OneDrive (a newer one is downloaded again,
     *  and changes made here stay in this one until they're uploaded). */
    private fun file(item: String, tag: String, name: String): File =
        File(dir, "photos/$item/${fnv(tag).toULong().toString(16)}.${name.substringAfterLast('.', "jpg").lowercase()}")

    private fun File.readBytes(n: Int): ByteArray = inputStream().use { it.readNBytesCompat(n) }

    private fun java.io.InputStream.readNBytesCompat(n: Int): ByteArray {
        val out = java.io.ByteArrayOutputStream()
        val buf = ByteArray(16 * 1024)
        while (out.size() < n) {
            val r = read(buf, 0, minOf(buf.size, n - out.size()))
            if (r < 0) break
            out.write(buf, 0, r)
        }
        return out.toByteArray()
    }

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

    /** Any small picture of this OneDrive file kept on the phone (for the Sync list). */
    fun anyThumbnail(item: String): Bitmap? =
        File(dir, "thumbs").listFiles { f -> f.name.startsWith("$item-") }?.maxByOrNull { it.lastModified() }
            ?.let { BitmapFactory.decodeFile(it.path) }

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
        /** The EXIF date taken in the start of a JPEG/PNG file. */
        fun exifDate(head: ByteArray): LocalDateTime? {
            val exif = androidx.exifinterface.media.ExifInterface(java.io.ByteArrayInputStream(head))
            val text = exif.getAttribute(androidx.exifinterface.media.ExifInterface.TAG_DATETIME_ORIGINAL)
                ?: exif.getAttribute(androidx.exifinterface.media.ExifInterface.TAG_DATETIME_DIGITIZED) ?: return null
            return runCatching { LocalDateTime.parse(text.trim(), EXIF_DATE) }.getOrNull()
        }

        fun wallTime(text: String?): LocalDateTime? = text?.takeIf { it.isNotEmpty() }?.let {
            runCatching { LocalDateTime.parse(it.removeSuffix("Z").substringBefore('+').take(19)) }.getOrNull()
        }
    }
}
