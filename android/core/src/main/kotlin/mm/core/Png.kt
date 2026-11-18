package mm.core

import java.io.ByteArrayOutputStream
import java.util.zip.CRC32
import java.util.zip.InflaterInputStream

/**
 * A PNG's chunks. Screenshots are PNGs: their keywords, label, ⭐/🔖 and ✨ go in an XMP iTXt chunk
 * ("XML:com.adobe.xmp"), where ExifTool (and so the Windows app) reads and writes them. PNG has no IPTC,
 * so on the PC too its keywords are XMP only. The picture itself isn't touched.
 */
class Png(val chunks: MutableList<Chunk>) {
    class Chunk(val type: String, val data: ByteArray)

    companion object {
        private val SIGNATURE = byteArrayOf(0x89.toByte(), 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A)
        private const val XMP_KEY = "XML:com.adobe.xmp"
        /** Chunks about the photo (not the picture) carried over when a PNG is re-encoded after an edit. */
        private val INFO = setOf("eXIf", "iTXt", "tEXt", "zTXt", "tIME")

        fun isPng(bytes: ByteArray) = bytes.size >= 8 && SIGNATURE.indices.all { bytes[it] == SIGNATURE[it] }

        fun parse(bytes: ByteArray): Png {
            require(isPng(bytes)) { "Not a PNG" }
            val chunks = mutableListOf<Chunk>()
            var i = 8
            while (i + 12 <= bytes.size) {
                val len = ((bytes[i].toInt() and 0xFF) shl 24) or ((bytes[i + 1].toInt() and 0xFF) shl 16) or
                    ((bytes[i + 2].toInt() and 0xFF) shl 8) or (bytes[i + 3].toInt() and 0xFF)
                if (len < 0 || i + 12 + len > bytes.size) break
                val type = String(bytes, i + 4, 4, Charsets.ISO_8859_1)
                chunks.add(Chunk(type, bytes.copyOfRange(i + 8, i + 8 + len)))
                i += 12 + len
                if (type == "IEND") break
            }
            require(chunks.firstOrNull()?.type == "IHDR") { "A damaged PNG" }
            return Png(chunks)
        }
    }

    fun toBytes(): ByteArray {
        val out = ByteArrayOutputStream()
        out.write(SIGNATURE)
        for (c in chunks) {
            val n = c.data.size
            out.write(byteArrayOf((n ushr 24).toByte(), (n ushr 16).toByte(), (n ushr 8).toByte(), n.toByte()))
            val type = c.type.toByteArray(Charsets.ISO_8859_1)
            out.write(type)
            out.write(c.data)
            val crc = CRC32().apply { update(type); update(c.data) }.value
            out.write(byteArrayOf((crc ushr 24).toByte(), (crc ushr 16).toByte(), (crc ushr 8).toByte(), crc.toByte()))
        }
        return out.toByteArray()
    }

    private fun isXmp(c: Chunk) = c.type == "iTXt" && c.data.size > XMP_KEY.length &&
        String(c.data, 0, XMP_KEY.length, Charsets.ISO_8859_1) == XMP_KEY && c.data[XMP_KEY.length] == 0.toByte()

    /** iTXt: keyword \0, compressed?, method, language \0, translated keyword \0, text (UTF-8). */
    var xmp: String?
        get() {
            val c = chunks.firstOrNull { isXmp(it) } ?: return null
            val d = c.data
            var i = XMP_KEY.length + 1
            val compressed = d[i] == 1.toByte()
            i += 2
            repeat(2) { while (i < d.size && d[i] != 0.toByte()) i++; i++ }  // language, translated keyword
            if (i > d.size) return null
            val text = d.copyOfRange(i, d.size)
            return String(if (compressed) InflaterInputStream(text.inputStream()).readBytes() else text, Charsets.UTF_8)
        }
        set(value) {
            val at = chunks.indexOfFirst { isXmp(it) }
            chunks.removeAll { isXmp(it) }
            if (value == null) return
            val data = ByteArrayOutputStream().apply {
                write(XMP_KEY.toByteArray(Charsets.ISO_8859_1))
                write(byteArrayOf(0, 0, 0, 0, 0))  // \0, not compressed, method 0, no language \0, no translation \0
                write(value.toByteArray(Charsets.UTF_8))
            }.toByteArray()
            // Where it was, else before the picture data (where Android and other apps look first).
            val idat = chunks.indexOfFirst { it.type == "IDAT" }.takeIf { it > 0 } ?: (chunks.size - 1)
            chunks.add(if (at in 1..chunks.size) at else idat, Chunk("iTXt", data))
        }

    /** Put this photo's information (EXIF, XMP, text) on a freshly encoded PNG of it. */
    fun transplantInto(encoded: ByteArray): ByteArray {
        val target = parse(encoded)
        target.chunks.removeAll { it.type in INFO }
        val idat = target.chunks.indexOfFirst { it.type == "IDAT" }.takeIf { it > 0 } ?: 1
        target.chunks.addAll(idat, chunks.filter { it.type in INFO })
        return target.toBytes()
    }
}
