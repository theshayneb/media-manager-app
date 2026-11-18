package mm.core

/**
 * What you did to a photo on the phone. Each is done to the phone's copy at once and kept in the sync queue
 * until it's been done to the same photo in OneDrive too (so the PC gets it, and work done on the PC stays).
 */
sealed class Change {
    data class Keywords(val add: List<String> = emptyList(), val remove: List<String> = emptyList()) : Change()
    data class Label(val label: String) : Change()                  // "" = no colour label
    data class Flag(val flag: String, val on: Boolean) : Change()   // "Star" or "Bookmark"
    object ClearLabels : Change()                                    // ⊘: colour, star and bookmark off
    data class DateTaken(val exif: String) : Change()               // "2024:06:14 18:32:05"
    data class Rename(val name: String) : Change()                  // new file name, with its extension
    // crop: fractions (left, top, right, bottom) of the file's own pixels, before its orientation is applied
    data class Edit(val adjustments: Map<String, Int>, val crop: List<Double>? = null) : Change()
    object Delete : Change()                                         // to the Trash / OneDrive's recycle bin

    /** Keywords, labels and flags: done to the photo's XMP/IPTC by [applyTags]. */
    val isTag get() = this is Keywords || this is Label || this is Flag || this is ClearLabels
}

/** The tags of a JPEG, as the Windows app reads them (XMP keywords and IPTC keywords together). */
fun readFields(bytes: ByteArray): XmpFields {
    if (!Jpeg.isJpeg(bytes)) return XmpFields()
    val jpeg = Jpeg.parse(bytes)
    val fields = Xmp.parse(jpeg.xmp).fields()
    val keywords = linkedMapOf<String, String>()
    (fields.keywords + jpeg.iptcKeywords).forEach { keywords.putIfAbsent(it.lowercase(), it) }
    return fields.copy(keywords = keywords.values.toList())
}

/** Apply a keyword / label / flag change to a JPEG's bytes (what ExifTool does on the PC). */
fun applyTags(bytes: ByteArray, change: Change): ByteArray {
    val jpeg = Jpeg.parse(bytes)
    val xmp = Xmp.parse(jpeg.xmp)
    when (change) {
        is Change.Keywords -> {
            val current = linkedMapOf<String, String>()
            (xmp.keywords + jpeg.iptcKeywords).forEach { current.putIfAbsent(it.lowercase(), it) }
            change.remove.forEach { current.remove(it.lowercase()) }
            change.add.map { it.trim() }.filter { it.isNotEmpty() }.forEach { current.putIfAbsent(it.lowercase(), it) }
            xmp.setKeywords(current.values.toList())
            jpeg.setIptcKeywords(current.values.toList())
        }
        is Change.Label -> xmp.label = change.label
        is Change.Flag -> if (change.flag == "Star") xmp.rating = if (change.on) 5 else 0
                          else xmp.bookmarked = change.on
        Change.ClearLabels -> { xmp.label = ""; xmp.rating = 0; xmp.bookmarked = false }
        else -> throw IllegalArgumentException("Not a tag change: $change")
    }
    jpeg.xmp = xmp.serialize()
    return jpeg.toBytes()
}

/** After an edit: the ✨ mark (the Windows app shows it on photos saved from an Edit view). */
fun markEdited(bytes: ByteArray): ByteArray {
    val jpeg = Jpeg.parse(bytes)
    val xmp = Xmp.parse(jpeg.xmp)
    xmp.history = EDITED_MARK
    jpeg.xmp = xmp.serialize()
    return jpeg.toBytes()
}
