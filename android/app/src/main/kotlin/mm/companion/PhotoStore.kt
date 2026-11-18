package mm.companion

import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.media.MediaScannerConnection
import android.net.Uri
import android.provider.MediaStore
import android.util.Size
import androidx.exifinterface.media.ExifInterface
import kotlinx.coroutines.suspendCancellableCoroutine
import mm.core.Jpeg
import mm.core.XmpFields
import mm.core.readFields
import java.io.File
import java.io.RandomAccessFile
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.coroutines.resume

/** A photo on the phone (from Android's media library). */
data class Photo(
    val id: Long,
    val path: String,
    val name: String,
    val takenMillis: Long,
    val modified: Long,
    val mime: String,
) {
    val uri: Uri get() = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
    val isJpeg get() = mime == "image/jpeg" || name.lowercase().let { it.endsWith(".jpg") || it.endsWith(".jpeg") }
}

data class Folder(val id: String, val name: String, val count: Int)

val EXIF_DATE: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy:MM:dd HH:mm:ss")

/** Photos on the device: listing, reading their tags, and changing the files. */
class PhotoStore(private val context: Context) {
    private val resolver get() = context.contentResolver

    fun folders(): List<Folder> {
        val counts = linkedMapOf<String, Pair<String, Int>>()
        resolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            arrayOf(MediaStore.Images.Media.BUCKET_ID, MediaStore.Images.Media.BUCKET_DISPLAY_NAME),
            null, null, "${MediaStore.Images.Media.DATE_TAKEN} DESC",
        )?.use { c ->
            while (c.moveToNext()) {
                val id = c.getString(0) ?: continue
                val name = c.getString(1) ?: "?"
                val (n, count) = counts[id] ?: (name to 0)
                counts[id] = n to count + 1
            }
        }
        return counts.map { (id, v) -> Folder(id, v.first, v.second) }
    }

    fun photos(folderId: String): List<Photo> {
        val out = mutableListOf<Photo>()
        resolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            arrayOf(
                MediaStore.Images.Media._ID, MediaStore.Images.Media.DATA, MediaStore.Images.Media.DISPLAY_NAME,
                MediaStore.Images.Media.DATE_TAKEN, MediaStore.Images.Media.DATE_MODIFIED,
                MediaStore.Images.Media.MIME_TYPE,
            ),
            "${MediaStore.Images.Media.BUCKET_ID} = ?", arrayOf(folderId),
            "${MediaStore.Images.Media.DATE_TAKEN} DESC",
        )?.use { c ->
            while (c.moveToNext()) {
                out.add(Photo(c.getLong(0), c.getString(1) ?: continue, c.getString(2) ?: "", c.getLong(3),
                    c.getLong(4), c.getString(5) ?: ""))
            }
        }
        return out
    }

    fun thumbnail(photo: Photo, size: Int = 256): Bitmap? =
        try { resolver.loadThumbnail(photo.uri, Size(size, size), null) } catch (e: Exception) { null }

    /** The tags (read from the start of the file: that's where they are). */
    fun fields(photo: Photo): XmpFields {
        if (!photo.isJpeg) return XmpFields()
        return try {
            val head = RandomAccessFile(photo.path, "r").use { f ->
                val n = minOf(f.length(), 512 * 1024L).toInt()
                ByteArray(n).also { f.readFully(it) }
            }
            readFields(head)
        } catch (e: Exception) {
            XmpFields()
        }
    }

    fun read(photo: Photo): ByteArray = File(photo.path).readBytes()

    /** Replace the photo's file (written beside it first, so a failure never leaves half a photo). */
    suspend fun write(photo: Photo, bytes: ByteArray) {
        val file = File(photo.path)
        val tmp = File(file.parentFile, ".${file.name}.saving")
        tmp.writeBytes(bytes)
        if (!tmp.renameTo(file)) {
            file.writeBytes(bytes)
            tmp.delete()
        }
        scan(file.path)
    }

    fun dateTaken(photo: Photo): LocalDateTime? {
        val exif = try { ExifInterface(photo.path) } catch (e: Exception) { null }
        val text = exif?.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL)
            ?: exif?.getAttribute(ExifInterface.TAG_DATETIME_DIGITIZED)
        return text?.let { runCatching { LocalDateTime.parse(it.trim(), EXIF_DATE) }.getOrNull() }
    }

    /** Set "date taken" (as the Windows app does: DateTimeOriginal, CreateDate and ModifyDate). */
    suspend fun setDateTaken(photo: Photo, exifDate: String) {
        setDateInFile(File(photo.path), exifDate)
        scan(photo.path)
    }

    suspend fun rename(photo: Photo, newName: String): String {
        val file = File(photo.path)
        val target = File(file.parentFile, newName)
        if (target.exists()) throw IllegalStateException("$newName already exists")
        if (!file.renameTo(target)) throw IllegalStateException("Couldn't rename ${photo.name}")
        scan(file.path)
        scan(target.path)
        return target.path
    }

    /** To Android's Trash (kept 30 days). */
    fun trash(photo: Photo): Boolean = try {
        resolver.update(photo.uri, ContentValues().apply { put(MediaStore.MediaColumns.IS_TRASHED, 1) }, null, null) > 0
    } catch (e: SecurityException) {
        false
    }

    /** Before an edit replaces a photo: a copy of the original, put straight in the Trash. */
    fun keepOriginalInTrash(photo: Photo, bytes: ByteArray) {
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, photo.name.substringBeforeLast('.') + " (original)." +
                photo.name.substringAfterLast('.', "jpg"))
            put(MediaStore.MediaColumns.MIME_TYPE, photo.mime.ifEmpty { "image/jpeg" })
            put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/Media Manager originals")
            put(MediaStore.MediaColumns.IS_PENDING, 1)
        }
        val uri = resolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: return
        resolver.openOutputStream(uri)?.use { it.write(bytes) }
        resolver.update(uri, ContentValues().apply {
            put(MediaStore.MediaColumns.IS_PENDING, 0)
            put(MediaStore.MediaColumns.IS_TRASHED, 1)
        }, null, null)
    }

    private suspend fun scan(path: String) = suspendCancellableCoroutine { cont ->
        MediaScannerConnection.scanFile(context, arrayOf(path), null) { _, _ -> if (cont.isActive) cont.resume(Unit) }
    }
}

/**
 * Set the EXIF dates in a JPEG file. Android's ExifInterface rewrites the file; the XMP and IPTC blocks
 * (keywords, labels…) are put back if it dropped them.
 */
fun setDateInFile(file: File, exifDate: String) {
    val before = file.readBytes()
    val exif = ExifInterface(file.path)
    exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, exifDate)
    exif.setAttribute(ExifInterface.TAG_DATETIME_DIGITIZED, exifDate)
    exif.setAttribute(ExifInterface.TAG_DATETIME, exifDate)
    exif.saveAttributes()
    if (!Jpeg.isJpeg(before)) return
    val old = Jpeg.parse(before)
    val now = Jpeg.parse(file.readBytes())
    var changed = false
    if (now.xmp == null && old.xmp != null) { now.xmp = old.xmp; changed = true }
    if (now.iptcKeywords.isEmpty() && old.iptcKeywords.isNotEmpty()) { now.setIptcKeywords(old.iptcKeywords); changed = true }
    if (changed) file.writeBytes(now.toBytes())
}
