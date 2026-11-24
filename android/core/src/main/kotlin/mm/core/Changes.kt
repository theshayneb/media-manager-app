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
    // turn: rotate/flip of the upright photo ([quarter turns clockwise, mirrored 0/1], see Turn), before the crop
    data class Edit(val adjustments: Map<String, Int>, val crop: List<Double>? = null, val turn: List<Int>? = null) : Change()
    object Delete : Change()                                         // to the Trash / OneDrive's recycle bin
    data class Move(val folderId: String, val folderName: String) : Change()  // to another OneDrive folder

    /** Keywords, labels and flags: done to the photo's XMP/IPTC by [applyTags]. */
    val isTag get() = this is Keywords || this is Label || this is Flag || this is ClearLabels
}

/** Photos whose tags can be changed here: JPEG (XMP + IPTC) and PNG, e.g. screenshots (XMP). */
fun canTag(bytes: ByteArray) = Jpeg.isJpeg(bytes) || Png.isPng(bytes)

/** The tags of a JPEG or PNG, as the Windows app reads them (XMP keywords and IPTC keywords together). */
fun readFields(bytes: ByteArray): XmpFields {
    if (Png.isPng(bytes)) return runCatching { Xmp.parse(Png.parse(bytes).xmp).fields() }.getOrDefault(XmpFields())
    if (!Jpeg.isJpeg(bytes)) return XmpFields()
    val jpeg = Jpeg.parse(bytes)
    val fields = Xmp.parse(jpeg.xmp).fields()
    val keywords = linkedMapOf<String, String>()
    (fields.keywords + jpeg.iptcKeywords).forEach { keywords.putIfAbsent(it.lowercase(), it) }
    return fields.copy(keywords = keywords.values.toList())
}

/** Apply a keyword / label / flag change to a JPEG's or PNG's bytes (what ExifTool does on the PC). */
fun applyTags(bytes: ByteArray, change: Change): ByteArray {
    if (Png.isPng(bytes)) {
        val png = Png.parse(bytes)
        val xmp = Xmp.parse(png.xmp)
        changeTags(xmp, emptyList(), change)
        png.xmp = xmp.serialize()
        return png.toBytes()
    }
    val jpeg = Jpeg.parse(bytes)
    val xmp = Xmp.parse(jpeg.xmp)
    changeTags(xmp, jpeg.iptcKeywords, change)?.let { jpeg.setIptcKeywords(it) }
    jpeg.xmp = xmp.serialize()
    return jpeg.toBytes()
}

/** Changes xmp; returns the new keyword list when keywords changed (for IPTC too). */
private fun changeTags(xmp: Xmp, iptcKeywords: List<String>, change: Change): List<String>? {
    when (change) {
        is Change.Keywords -> {
            val current = linkedMapOf<String, String>()
            (xmp.keywords + iptcKeywords).forEach { current.putIfAbsent(it.lowercase(), it) }
            change.remove.forEach { current.remove(it.lowercase()) }
            change.add.map { it.trim() }.filter { it.isNotEmpty() }.forEach { current.putIfAbsent(it.lowercase(), it) }
            xmp.setKeywords(current.values.toList())
            return current.values.toList()
        }
        is Change.Label -> xmp.label = change.label
        is Change.Flag -> if (change.flag == "Star") xmp.rating = if (change.on) 5 else 0
                          else xmp.bookmarked = change.on
        Change.ClearLabels -> { xmp.label = ""; xmp.rating = 0; xmp.bookmarked = false }
        else -> throw IllegalArgumentException("Not a tag change: $change")
    }
    return null
}

/** After an edit: the ✨ mark (the Windows app shows it on photos saved from an Edit view). */
fun markEdited(bytes: ByteArray): ByteArray {
    if (Png.isPng(bytes)) {
        val png = Png.parse(bytes)
        png.xmp = Xmp.parse(png.xmp).apply { history = EDITED_MARK }.serialize()
        return png.toBytes()
    }
    val jpeg = Jpeg.parse(bytes)
    val xmp = Xmp.parse(jpeg.xmp)
    xmp.history = EDITED_MARK
    jpeg.xmp = xmp.serialize()
    return jpeg.toBytes()
}

/** What a photo's tags will be after a change (for a OneDrive photo whose file isn't on the phone yet). */
fun XmpFields.applying(change: Change): XmpFields = when (change) {
    is Change.Keywords -> {
        val gone = change.remove.map { it.lowercase() }.toSet()
        val kept = keywords.filter { it.lowercase() !in gone }
        copy(keywords = kept + change.add.filter { a -> kept.none { it.equals(a, true) } }.distinctBy { it.lowercase() })
    }
    is Change.Label -> copy(label = change.label)
    is Change.Flag -> if (change.flag == "Star") copy(rating = if (change.on) 5 else 0) else copy(bookmarked = change.on)
    Change.ClearLabels -> copy(label = "", rating = 0, bookmarked = false)
    else -> this
}
