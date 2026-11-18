package mm.core

import java.io.ByteArrayOutputStream

/**
 * A JPEG's header segments (before the image data): EXIF, XMP, IPTC, ICC colour profile…
 * Read and replaced here without touching the image itself.
 */
class Jpeg(val segments: MutableList<Segment>, val rest: ByteArray) {
    /** marker (0xE1 = APP1…), payload without the 2 length bytes. */
    class Segment(val marker: Int, val data: ByteArray) {
        fun startsWith(prefix: ByteArray) = data.size >= prefix.size && prefix.indices.all { data[it] == prefix[it] }
    }

    companion object {
        val XMP_ID = "http://ns.adobe.com/xap/1.0/\u0000".toByteArray(Charsets.ISO_8859_1)
        val EXIF_ID = "Exif\u0000\u0000".toByteArray(Charsets.ISO_8859_1)
        val PS_ID = "Photoshop 3.0\u0000".toByteArray(Charsets.ISO_8859_1)
        val ICC_ID = "ICC_PROFILE\u0000".toByteArray(Charsets.ISO_8859_1)
        const val APP1 = 0xE1
        const val APP2 = 0xE2
        const val APP13 = 0xED

        fun isJpeg(bytes: ByteArray) = bytes.size > 3 && bytes[0] == 0xFF.toByte() && bytes[1] == 0xD8.toByte()

        fun parse(bytes: ByteArray): Jpeg {
            require(isJpeg(bytes)) { "Not a JPEG" }
            val segments = mutableListOf<Segment>()
            var i = 2
            while (i + 4 <= bytes.size) {
                if (bytes[i] != 0xFF.toByte()) break
                val marker = bytes[i + 1].toInt() and 0xFF
                if (marker == 0xFF) { i++; continue }  // padding
                if (marker == 0xDA || marker == 0xD9) break  // image data starts
                val len = ((bytes[i + 2].toInt() and 0xFF) shl 8) or (bytes[i + 3].toInt() and 0xFF)
                if (len < 2 || i + 2 + len > bytes.size) break
                segments.add(Segment(marker, bytes.copyOfRange(i + 4, i + 2 + len)))
                i += 2 + len
            }
            return Jpeg(segments, bytes.copyOfRange(i, bytes.size))
        }
    }

    fun toBytes(): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(0xFF); out.write(0xD8)
        for (s in segments) {
            val len = s.data.size + 2
            require(len <= 0xFFFF) { "A header segment is too big" }
            out.write(0xFF); out.write(s.marker); out.write(len shr 8); out.write(len and 0xFF)
            out.write(s.data)
        }
        out.write(rest)
        return out.toByteArray()
    }

    // ------------------------------------------------------------------ XMP
    var xmp: String?
        get() = segments.firstOrNull { it.marker == APP1 && it.startsWith(XMP_ID) }
            ?.let { String(it.data, XMP_ID.size, it.data.size - XMP_ID.size, Charsets.UTF_8) }
        set(value) {
            val at = segments.indexOfFirst { it.marker == APP1 && it.startsWith(XMP_ID) }
            if (value == null) {
                if (at >= 0) segments.removeAt(at)
                return
            }
            val seg = Segment(APP1, XMP_ID + value.toByteArray(Charsets.UTF_8))
            if (at >= 0) segments[at] = seg
            else {
                // after APP0 (JFIF) and the EXIF block, as other apps put it
                val exif = segments.indexOfFirst { it.marker == APP1 && it.startsWith(EXIF_ID) }
                val app0 = segments.indexOfFirst { it.marker == 0xE0 }
                segments.add(maxOf(exif, app0) + 1, seg)
            }
        }

    // ------------------------------------------------------------------ IPTC keywords (APP13 / 8BIM 0x0404)
    private fun iptcBlock(): ByteArray? {
        val seg = segments.firstOrNull { it.marker == APP13 && it.startsWith(PS_ID) } ?: return null
        return irb(seg.data).firstOrNull { it.first == 0x0404 }?.second
    }

    val iptcKeywords: List<String>
        get() {
            val block = iptcBlock() ?: return emptyList()
            val charset = if (utf8()) Charsets.UTF_8 else Charsets.ISO_8859_1
            return iptcDatasets(block).filter { it.record == 2 && it.dataset == 25 }
                .map { String(it.value, charset).trim() }.filter { it.isNotEmpty() }
        }

    private fun utf8(): Boolean {
        val block = iptcBlock() ?: return true
        return iptcDatasets(block).any { it.record == 1 && it.dataset == 90 && it.value.contentEquals(UTF8_ESC) }
    }

    /** Replace the IPTC keywords (kept the same as XMP's, as the Windows app does); other IPTC kept. */
    fun setIptcKeywords(keywords: List<String>) {
        val segAt = segments.indexOfFirst { it.marker == APP13 && it.startsWith(PS_ID) }
        val resources = if (segAt >= 0) irb(segments[segAt].data).toMutableList() else mutableListOf()
        val old = resources.firstOrNull { it.first == 0x0404 }?.second
        if (old == null && keywords.isEmpty()) return
        val datasets = (old?.let { iptcDatasets(it) } ?: emptyList())
            .filterNot { (it.record == 2 && it.dataset == 25) || (it.record == 1 && it.dataset == 90) }
            .toMutableList()
        datasets.add(0, IptcDataset(1, 90, UTF8_ESC))
        val insertAt = datasets.indexOfFirst { it.record == 2 }.let { if (it < 0) datasets.size else it }
        datasets.addAll(insertAt, keywords.map { IptcDataset(2, 25, it.toByteArray(Charsets.UTF_8).take(64).toByteArray()) })
        val block = ByteArrayOutputStream().apply { datasets.forEach { write(it.encode()) } }.toByteArray()
        val i = resources.indexOfFirst { it.first == 0x0404 }
        if (i >= 0) resources[i] = 0x0404 to block else resources.add(0x0404 to block)
        val seg = Segment(APP13, PS_ID + encodeIrb(resources))
        if (segAt >= 0) segments[segAt] = seg
        else {
            val after = segments.indexOfLast { it.marker == APP1 || it.marker == 0xE0 }
            segments.add(after + 1, seg)
        }
    }

    // ------------------------------------------------------------------ edited copies
    /** Put this photo's information (EXIF, XMP, IPTC, colour profile) on a freshly encoded JPEG. */
    fun transplantInto(encoded: ByteArray): ByteArray {
        val target = parse(encoded)
        val keep = segments.filter {
            (it.marker == APP1 && (it.startsWith(EXIF_ID) || it.startsWith(XMP_ID))) ||
                (it.marker == APP2 && it.startsWith(ICC_ID)) || (it.marker == APP13 && it.startsWith(PS_ID))
        }
        target.segments.removeAll { it.marker in setOf(APP1, APP2, APP13) }
        val app0 = target.segments.indexOfFirst { it.marker == 0xE0 }
        target.segments.addAll(app0 + 1, keep)
        return target.toBytes()
    }
}

private val UTF8_ESC = byteArrayOf(0x1B, 0x25, 0x47)  // ESC % G: the IPTC text is UTF-8

private class IptcDataset(val record: Int, val dataset: Int, val value: ByteArray) {
    fun encode(): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(0x1C); out.write(record); out.write(dataset)
        out.write(value.size shr 8); out.write(value.size and 0xFF)
        out.write(value)
        return out.toByteArray()
    }
}

private fun iptcDatasets(block: ByteArray): List<IptcDataset> {
    val out = mutableListOf<IptcDataset>()
    var i = 0
    while (i + 5 <= block.size && block[i] == 0x1C.toByte()) {
        val record = block[i + 1].toInt() and 0xFF
        val dataset = block[i + 2].toInt() and 0xFF
        var len = ((block[i + 3].toInt() and 0xFF) shl 8) or (block[i + 4].toInt() and 0xFF)
        var start = i + 5
        if (len and 0x8000 != 0) {  // extended length
            val n = len and 0x7FFF
            len = 0
            for (k in 0 until n) len = (len shl 8) or (block[start + k].toInt() and 0xFF)
            start += n
        }
        if (start + len > block.size) break
        out.add(IptcDataset(record, dataset, block.copyOfRange(start, start + len)))
        i = start + len
    }
    return out
}

/** Photoshop image resources: "8BIM", id, Pascal name (padded to even), size, data (padded to even). */
private fun irb(data: ByteArray): List<Pair<Int, ByteArray>> {
    val out = mutableListOf<Pair<Int, ByteArray>>()
    var i = Jpeg.PS_ID.size
    while (i + 12 <= data.size && String(data, i, 4, Charsets.ISO_8859_1) == "8BIM") {
        val id = ((data[i + 4].toInt() and 0xFF) shl 8) or (data[i + 5].toInt() and 0xFF)
        val nameLen = data[i + 6].toInt() and 0xFF
        var p = i + 6 + 1 + nameLen
        if ((1 + nameLen) % 2 == 1) p++
        if (p + 4 > data.size) break
        val size = ((data[p].toInt() and 0xFF) shl 24) or ((data[p + 1].toInt() and 0xFF) shl 16) or
            ((data[p + 2].toInt() and 0xFF) shl 8) or (data[p + 3].toInt() and 0xFF)
        p += 4
        if (size < 0 || p + size > data.size) break
        out.add(id to data.copyOfRange(p, p + size))
        i = p + size + (size % 2)
    }
    return out
}

private fun encodeIrb(resources: List<Pair<Int, ByteArray>>): ByteArray {
    val out = ByteArrayOutputStream()
    for ((id, block) in resources) {
        out.write("8BIM".toByteArray(Charsets.ISO_8859_1))
        out.write(id shr 8); out.write(id and 0xFF)
        out.write(0); out.write(0)  // empty name, padded to even
        val n = block.size
        out.write(n ushr 24); out.write((n shr 16) and 0xFF); out.write((n shr 8) and 0xFF); out.write(n and 0xFF)
        out.write(block)
        if (n % 2 == 1) out.write(0)
    }
    return out.toByteArray()
}
