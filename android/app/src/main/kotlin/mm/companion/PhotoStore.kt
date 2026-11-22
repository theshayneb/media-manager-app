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
import mm.core.Png
import mm.core.XmpFields
import mm.core.readFields
import java.io.File
import java.io.RandomAccessFile
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import kotlin.coroutines.resume

/** A photo on the phone (from Android's media library), or in OneDrive's Camera Roll ([cloudId]: its OneDrive id;
 *  [path]: the phone's copy, there once it's downloaded). */
data class Photo(
    val id: Long,
    val path: String,
    val name: String,
    val takenMillis: Long,
    val modified: Long,
    val mime: String,
    val cloudId: String? = null,
) {
    val inCloud get() = cloudId != null
    val uri: Uri get() = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
    val isJpeg get() = mime == "image/jpeg" || name.lowercase().let { it.endsWith(".jpg") || it.endsWith(".jpeg") }
    val isPng get() = mime == "image/png" || name.lowercase().endsWith(".png")
    /** Tags, dates and edits work on JPGs and PNGs (screenshots). */
    val canChange get() = isJpeg || isPng
}

data class Folder(val id: String, val name: String, val count: Int, val path: String = "") {
    val inCloud get() = id.startsWith(CloudPhotos.CLOUD)
}

val EXIF_DATE: DateTimeFormatter = DateTimeFormatter.ofPattern("yyyy:MM:dd HH:mm:ss")

/** Photos on the device: listing, reading their tags, and changing the files. */
class PhotoStore(private val context: Context) {
    private val resolver get() = context.contentResolver

    fun folders(): List<Folder> {
        data class Count(val name: String, val path: String, var n: Int)
        val counts = linkedMapOf<String, Count>()
        resolver.query(
            MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
            arrayOf(MediaStore.Images.Media.BUCKET_ID, MediaStore.Images.Media.BUCKET_DISPLAY_NAME,
                MediaStore.Images.Media.DATA),
            null, null, "${MediaStore.Images.Media.DATE_TAKEN} DESC",
        )?.use { c ->
            while (c.moveToNext()) {
                val id = c.getString(0) ?: continue
                counts.getOrPut(id) { Count(c.getString(1) ?: "?", c.getString(2)?.let { File(it).parent } ?: "", 0) }.n++
            }
        }
        return counts.map { (id, v) -> Folder(id, v.name, v.n, v.path) }
    }

    /** A folder with no photos in it (yet): Android's media library doesn't list it, so it's made from its path.
     *  Its id is the one Android gives a folder (the lower-case path's hash), so photos put there later show. */
    fun emptyFolder(path: String) =
        Folder(path.lowercase(java.util.Locale.ROOT).hashCode().toString(), File(path).name, 0, path)

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
        if (!photo.canChange) return XmpFields()
        return try {
            // A PNG's tags can be after the picture (ExifTool can put them there): read all of it.
            if (photo.isPng) return readFields(File(photo.path).readBytes())
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

    /**
     * Replace the photo's contents, in place. (Not by writing a new file beside it and renaming it over the photo:
     * Android then treats it as a different photo, and OneDrive's camera backup waits forever for the old one.)
     * A copy is kept in the app's cache until it's written, so a failure puts the photo back as it was.
     */
    suspend fun write(photo: Photo, bytes: ByteArray) {
        val file = File(photo.path)
        val backup = File(context.cacheDir, "saving-${photo.id}")
        file.copyTo(backup, overwrite = true)
        try {
            java.io.FileOutputStream(file).use { it.write(bytes); it.fd.sync() }
        } catch (e: Exception) {
            runCatching { backup.copyTo(file, overwrite = true) }
            throw e
        } finally {
            backup.delete()
        }
        if (!photo.inCloud) scan(file.path)
    }

    fun dateTaken(photo: Photo): LocalDateTime? {
        val exif = try { ExifInterface(photo.path) } catch (e: Exception) { null }
        val text = exif?.getAttribute(ExifInterface.TAG_DATETIME_ORIGINAL)
            ?: exif?.getAttribute(ExifInterface.TAG_DATETIME_DIGITIZED)
        if (text == null && photo.inCloud && photo.takenMillis > 0 && !File(photo.path).exists()) {
            // Not downloaded yet: the date OneDrive read from it.
            return LocalDateTime.ofInstant(java.time.Instant.ofEpochMilli(photo.takenMillis), java.time.ZoneId.systemDefault())
        }
        return text?.let { runCatching { LocalDateTime.parse(it.trim(), EXIF_DATE) }.getOrNull() }
    }

    /** Set "date taken" (as the Windows app does: DateTimeOriginal, CreateDate and ModifyDate). */
    suspend fun setDateTaken(photo: Photo, exifDate: String) {
        setDateInFile(File(photo.path), exifDate)
        if (!photo.inCloud) scan(photo.path)
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
 * Set the EXIF dates in a JPEG or PNG file. Android's ExifInterface rewrites the file; the XMP and IPTC blocks
 * (keywords, labels…) are put back if it dropped them.
 */
fun setDateInFile(file: File, exifDate: String) {
    val before = file.readBytes()
    val exif = ExifInterface(file.path)
    exif.setAttribute(ExifInterface.TAG_DATETIME_ORIGINAL, exifDate)
    exif.setAttribute(ExifInterface.TAG_DATETIME_DIGITIZED, exifDate)
    exif.setAttribute(ExifInterface.TAG_DATETIME, exifDate)
    exif.saveAttributes()
    if (Png.isPng(before)) {
        val now = Png.parse(file.readBytes())
        val xmp = Png.parse(before).xmp
        if (now.xmp == null && xmp != null) { now.xmp = xmp; file.writeBytes(now.toBytes()) }
        return
    }
    if (!Jpeg.isJpeg(before)) return
    val old = Jpeg.parse(before)
    val now = Jpeg.parse(file.readBytes())
    var changed = false
    if (now.xmp == null && old.xmp != null) { now.xmp = old.xmp; changed = true }
    if (now.iptcKeywords.isEmpty() && old.iptcKeywords.isNotEmpty()) { now.setIptcKeywords(old.iptcKeywords); changed = true }
    if (changed) file.writeBytes(now.toBytes())
}
