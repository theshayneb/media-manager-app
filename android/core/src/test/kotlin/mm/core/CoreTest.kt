package mm.core

import java.awt.image.BufferedImage
import java.io.ByteArrayOutputStream
import java.time.LocalDateTime
import javax.imageio.ImageIO
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull
import kotlin.test.assertTrue

class CoreTest {
    private fun jpeg(w: Int = 40, h: Int = 30, rgb: Int = 0x787878): ByteArray {
        val img = BufferedImage(w, h, BufferedImage.TYPE_INT_RGB)
        for (y in 0 until h) for (x in 0 until w) img.setRGB(x, y, rgb)
        return ByteArrayOutputStream().also { ImageIO.write(img, "jpg", it) }.toByteArray()
    }

    @Test fun templatesMatchTheWindowsApp() {
        assertEquals(LocalDateTime.of(2024, 6, 14, 18, 32, 5),
            matchAny(DEFAULT_TEMPLATES.drop(1), "IMG_20240614_183205.jpg")!!.second)
        assertEquals(LocalDateTime.of(2026, 8, 15, 11, 42, 44),
            matchAny(DEFAULT_TEMPLATES, "08-15-2026 11-42-44 AM.jpg")!!.second)
        assertNull(matchAny(DEFAULT_TEMPLATES, "holiday.jpg"))
        val dt = LocalDateTime.of(2024, 6, 14, 18, 32, 5)
        assertEquals("06-14-2024 06-32-05 PM", formatPattern(DEFAULT_RENAME_PATTERN, dt))
        val names = renamePlan(listOf(Triple("a.jpg", dt, ""), Triple("b.jpg", dt, ""), Triple("c.jpg", null, "")),
            DEFAULT_RENAME_PATTERN, emptySet())
        assertEquals(listOf("06-14-2024 06-32-05 PM.jpg", "06-14-2024 06-32-05 PM_1.jpg", null), names)
    }

    @Test fun tagsGoWhereTheWindowsAppReadsThem() {
        var bytes = jpeg()
        bytes = applyTags(bytes, Change.Keywords(add = listOf("josh", "new york")))
        bytes = applyTags(bytes, Change.Label("Green"))
        bytes = applyTags(bytes, Change.Flag("Star", true))
        bytes = applyTags(bytes, Change.Flag("Bookmark", true))
        var f = readFields(bytes)
        assertEquals(listOf("josh", "new york"), f.keywords)
        assertEquals("Green", f.label); assertTrue(f.starred); assertTrue(f.bookmarked)
        val jpeg = Jpeg.parse(bytes)
        assertEquals(listOf("josh", "new york"), jpeg.iptcKeywords)
        val xmp = jpeg.xmp!!
        assertTrue("dc:subject" in xmp && "xmp:Label" in xmp && "xmp:Rating" in xmp && "xmpDM:good" in xmp)
        bytes = applyTags(bytes, Change.Keywords(add = listOf("Josh", "queens"), remove = listOf("new york")))
        f = readFields(bytes)
        assertEquals(listOf("josh", "queens"), f.keywords)  // no duplicate "Josh"
        assertEquals(listOf("josh", "queens"), Jpeg.parse(bytes).iptcKeywords)
        bytes = applyTags(bytes, Change.ClearLabels)
        f = readFields(bytes)
        assertEquals("", f.label); assertEquals(false, f.starred); assertEquals(false, f.bookmarked)
        assertEquals(listOf("josh", "queens"), f.keywords)
        assertTrue(markEdited(bytes).let { readFields(it).edited })
        // the picture itself is untouched
        assertTrue(ImageIO.read(bytes.inputStream()).width == 40)
    }

    @Test fun xmpWrittenByExifToolIsKept() {
        val exiftoolStyle = """<?xpacket begin='' id='W5M0MpCehiHzreSzNTczkc9d'?>
<x:xmpmeta xmlns:x='adobe:ns:meta/' x:xmptk='Image::ExifTool 13.00'>
<rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>
 <rdf:Description rdf:about='' xmlns:xmp='http://ns.adobe.com/xap/1.0/'>
  <xmp:Label>Red</xmp:Label>
  <xmp:Rating>5</xmp:Rating>
 </rdf:Description>
 <rdf:Description rdf:about='' xmlns:dc='http://purl.org/dc/elements/1.1/'>
  <dc:subject><rdf:Bag><rdf:li>me</rdf:li></rdf:Bag></dc:subject>
 </rdf:Description>
 <rdf:Description rdf:about='' xmlns:exif='http://ns.adobe.com/exif/1.0/'><exif:Other>keep me</exif:Other></rdf:Description>
</rdf:RDF></x:xmpmeta><?xpacket end='w'?>"""
        val jpeg = Jpeg.parse(jpeg())
        jpeg.xmp = exiftoolStyle
        var bytes = jpeg.toBytes()
        assertEquals(XmpFields(listOf("me"), "Red", 5, false, ""), readFields(bytes))
        bytes = applyTags(bytes, Change.Label("Blue"))
        val f = readFields(bytes)
        assertEquals("Blue", f.label); assertEquals(5, f.rating); assertEquals(listOf("me"), f.keywords)
        assertTrue("keep me" in Jpeg.parse(bytes).xmp!!)
    }

    @Test fun pngTagsRoundTripWithExifTool() {
        // Tagged on the PC (ExifTool, as Photo Manager does): the phone reads it and changes it, keeping the rest.
        var bytes = javaClass.getResourceAsStream("/pc-tagged.png")!!.readBytes()
        assertTrue(canTag(bytes))
        assertEquals(XmpFields(listOf("me", "Paris trip"), "Red", 5, false, ""), readFields(bytes))
        bytes = applyTags(bytes, Change.Keywords(add = listOf("café"), remove = listOf("me")))
        bytes = applyTags(bytes, Change.Flag("Bookmark", true))
        bytes = markEdited(bytes)
        val f = readFields(bytes)
        assertEquals(listOf("Paris trip", "café"), f.keywords)
        assertEquals("Red", f.label); assertTrue(f.bookmarked); assertTrue(f.edited)
        val png = Png.parse(bytes)
        assertEquals(1, png.chunks.count { it.type == "iTXt" })
        assertTrue(png.chunks.any { it.type == "eXIf" })  // the dates are untouched
        assertTrue(png.chunks.indexOfFirst { it.type == "iTXt" } < png.chunks.indexOfFirst { it.type == "IDAT" })
        assertEquals(png.chunks.size, Png.parse(png.toBytes()).chunks.size)  // CRCs and lengths right

        // An untagged screenshot.
        val img = BufferedImage(20, 10, BufferedImage.TYPE_INT_RGB)
        val plain = ByteArrayOutputStream().also { ImageIO.write(img, "png", it) }.toByteArray()
        assertEquals(XmpFields(), readFields(plain))
        assertEquals(listOf("me"), readFields(applyTags(plain, Change.Keywords(add = listOf("me")))).keywords)
        // Re-encoded after an edit: the information comes along.
        val again = Png.parse(bytes).transplantInto(plain)
        assertEquals(f, readFields(again))
        assertTrue(Png.parse(again).chunks.any { it.type == "eXIf" })
    }

    @Test fun editedCopyKeepsTheInformation() {
        var original = applyTags(jpeg(), Change.Keywords(add = listOf("museum")))
        original = applyTags(original, Change.Label("Purple"))
        val reEncoded = jpeg(20, 15, 0x336699)
        val out = Jpeg.parse(original).transplantInto(reEncoded)
        val f = readFields(out)
        assertEquals(listOf("museum"), f.keywords); assertEquals("Purple", f.label)
        assertEquals(20, ImageIO.read(out.inputStream()).width)
    }

    @Test fun editMathsMatchesTheWindowsApp() {
        assertEquals((0..255).toList(), lookupTable(Adjustments())[0].toList())
        val grey = Pixels(1, 1, intArrayOf(0xFF808080.toInt()))
        fun rgb(a: Adjustments) = applyEdit(grey, a).argb[0].let { Triple((it shr 16) and 255, (it shr 8) and 255, it and 255) }
        assertTrue(rgb(Adjustments(yellow = 60)).let { it.third < 128 && it.first > 128 })
        assertTrue(rgb(Adjustments(red = 60)).let { it.first > 128 && it.second < 128 })
        assertTrue(rgb(Adjustments(brightness = 60)).first > 128)
        assertEquals(Triple(128, 128, 128), rgb(Adjustments(satAll = 100)))  // grey stays grey
        val blue = Pixels(1, 1, intArrayOf(0xFF325AC8.toInt()))
        val out = applyEdit(blue, Adjustments(satBlue = -100)).argb[0]
        val spread = maxOf((out shr 16) and 255, (out shr 8) and 255, out and 255) - minOf((out shr 16) and 255, (out shr 8) and 255, out and 255)
        assertTrue(spread < 30, "blue saturation gone: $spread")
        // white balance: an orange patch becomes grey
        val (y, r) = neutral(170.0, 140.0, 100.0)
        val g = channelGains(y / 100.0, r / 100.0)
        val res = listOf(170 * g[0], 140 * g[1], 100 * g[2])
        assertTrue(res.max() - res.min() < 4)
    }

    @Test fun sharpnessIsVisible() {
        val w = 3000; val h = 60
        val px = IntArray(w * h) { if (it % w < 1500) 0xFF3C3C3C.toInt() else 0xFFBEBEBE.toInt() }
        val soft = gaussianBlur(Pixels(w, h, px), 2.0)
        val sharp = applyEdit(soft, Adjustments(sharpness = 100))
        fun at(p: Pixels, x: Int) = (p.argb[30 * w + x] shr 16) and 255
        assertTrue(at(sharp, 1501) - at(sharp, 1498) > at(soft, 1501) - at(soft, 1498))
    }
}

class InteropFile {
    /** Writes build/interop.jpg and .png for the Windows app's reader to check (tests/shell/test_android_interop.py). */
    @Test fun writeForTheWindowsApp() {
        val img = BufferedImage(40, 30, BufferedImage.TYPE_INT_RGB)
        var bytes = ByteArrayOutputStream().also { ImageIO.write(img, "jpg", it) }.toByteArray()
        bytes = applyTags(bytes, Change.Keywords(add = listOf("josh", "new york", "café")))
        bytes = applyTags(bytes, Change.Label("Green"))
        bytes = applyTags(bytes, Change.Flag("Star", true))
        bytes = applyTags(bytes, Change.Flag("Bookmark", true))
        bytes = markEdited(bytes)
        java.io.File("build/interop.jpg").writeBytes(bytes)

        var png = ByteArrayOutputStream().also { ImageIO.write(img, "png", it) }.toByteArray()
        png = applyTags(png, Change.Keywords(add = listOf("josh", "new york", "café")))
        png = applyTags(png, Change.Label("Green"))
        png = applyTags(png, Change.Flag("Star", true))
        png = applyTags(png, Change.Flag("Bookmark", true))
        png = markEdited(png)
        java.io.File("build/interop.png").writeBytes(png)
    }
}
