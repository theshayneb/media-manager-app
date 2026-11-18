package mm.core

import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.ln
import kotlin.math.log2
import kotlin.math.max
import kotlin.math.min
import kotlin.math.pow
import kotlin.math.roundToInt
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * The Windows app's photo edits (media_manager/photo_edit.py), on ARGB pixels (Android's Bitmap.getPixels),
 * so the same slider values give the same look on the phone and on the PC.
 */
data class Adjustments(
    val yellow: Int = 0, val red: Int = 0, val brightness: Int = 0, val contrast: Int = 0,
    val shadows: Int = 0, val highlights: Int = 0,
    val sharpness: Int = 0, val clarity: Int = 0,
    val satAll: Int = 0, val satRed: Int = 0, val satOrange: Int = 0, val satYellow: Int = 0,
    val satGreen: Int = 0, val satAqua: Int = 0, val satBlue: Int = 0, val satPurple: Int = 0, val satPink: Int = 0,
) {
    fun toMap(): Map<String, Int> = mapOf(
        "yellow" to yellow, "red" to red, "brightness" to brightness, "contrast" to contrast,
        "shadows" to shadows, "highlights" to highlights, "sharpness" to sharpness, "clarity" to clarity,
        "sat_all" to satAll, "sat_red" to satRed, "sat_orange" to satOrange, "sat_yellow" to satYellow,
        "sat_green" to satGreen, "sat_aqua" to satAqua, "sat_blue" to satBlue, "sat_purple" to satPurple,
        "sat_pink" to satPink,
    )

    val tonesUnchanged get() = listOf(yellow, red, brightness, contrast, shadows, highlights).all { it == 0 }
    val saturationUnchanged get() = listOf(satAll, satRed, satOrange, satYellow, satGreen, satAqua, satBlue,
        satPurple, satPink).all { it == 0 }
    val detailUnchanged get() = sharpness == 0 && clarity == 0
    val unchanged get() = tonesUnchanged && saturationUnchanged && detailUnchanged

    companion object {
        /** The Windows app's names (settings.json "last_edit" and the sync queue use them). */
        fun fromMap(m: Map<String, Int>) = Adjustments(
            m["yellow"] ?: 0, m["red"] ?: 0, m["brightness"] ?: 0, m["contrast"] ?: 0, m["shadows"] ?: 0,
            m["highlights"] ?: 0, m["sharpness"] ?: 0, m["clarity"] ?: 0, m["sat_all"] ?: 0, m["sat_red"] ?: 0,
            m["sat_orange"] ?: 0, m["sat_yellow"] ?: 0, m["sat_green"] ?: 0, m["sat_aqua"] ?: 0,
            m["sat_blue"] ?: 0, m["sat_purple"] ?: 0, m["sat_pink"] ?: 0,
        )
    }
}

private val WARM = doubleArrayOf(0.20, 0.12, -0.40)
private val TINT = doubleArrayOf(0.30, -0.24, 0.0)
private const val CONTRAST_UP = 1.2
private const val CONTRAST_DOWN = 0.8
private const val LIFT = 0.7
private const val BRIGHTNESS = 0.8

/** (field, hue in degrees, reach either side) as in photo_edit.SATURATION. */
private val HUES = listOf(0.0 to 25.0, 30.0 to 20.0, 55.0 to 25.0, 120.0 to 45.0, 180.0 to 30.0, 220.0 to 35.0,
    275.0 to 30.0, 320.0 to 30.0)

fun channelGains(yellow: Double, red: Double) = DoubleArray(3) { 1 + WARM[it] * yellow + TINT[it] * red }

/** 3 × 256 curves (red, green, blue). */
fun lookupTable(a: Adjustments): Array<IntArray> {
    val gains = channelGains(a.yellow / 100.0, a.red / 100.0)
    val c = a.contrast / 100.0
    val contrast = 1 + (if (c >= 0) CONTRAST_UP else CONTRAST_DOWN) * c
    val shadows = LIFT * a.shadows / 100.0
    val highlights = LIFT * a.highlights / 100.0
    return Array(3) { ch ->
        IntArray(256) { v ->
            var x = min(1.0, v / 255.0 * gains[ch])
            if (a.brightness != 0) x = x.pow(2.0.pow(-BRIGHTNESS * a.brightness / 100.0))
            x += shadows * (1 - x).pow(2) * (1 - (1 - x).pow(6))
            x += highlights * x.pow(2) * (1 - x.pow(6))
            x = (x - 0.5) * contrast + 0.5
            (x * 255).roundToInt().coerceIn(0, 255)
        }
    }
}

/** How much to multiply saturation by, for each of 256 hues (Pillow's HSV hue scale). */
fun saturationGains(a: Adjustments): DoubleArray {
    val amounts = intArrayOf(a.satRed, a.satOrange, a.satYellow, a.satGreen, a.satAqua, a.satBlue, a.satPurple,
        a.satPink)
    return DoubleArray(256) { h ->
        val degrees = h / 256.0 * 360
        var gain = 1 + a.satAll / 100.0
        for ((i, hr) in HUES.withIndex()) {
            val amount = amounts[i] / 100.0
            if (amount == 0.0) continue
            val (centre, reach) = hr
            val distance = min(abs(degrees - centre), 360 - abs(degrees - centre))
            if (distance < reach) gain += amount * (0.5 + 0.5 * cos(PI * distance / reach))
        }
        gain.coerceIn(0.0, 2.0)
    }
}

/** A photo's pixels being edited (ARGB, row by row). */
class Pixels(val width: Int, val height: Int, val argb: IntArray) {
    fun copy() = Pixels(width, height, argb.copyOf())

    fun crop(left: Int, top: Int, right: Int, bottom: Int): Pixels {
        val l = left.coerceIn(0, width - 1); val t = top.coerceIn(0, height - 1)
        val r = right.coerceIn(l + 1, width); val b = bottom.coerceIn(t + 1, height)
        val out = IntArray((r - l) * (b - t))
        for (y in t until b) System.arraycopy(argb, y * width + l, out, (y - t) * (r - l), r - l)
        return Pixels(r - l, b - t, out)
    }
}

/** The whole edit, as photo_edit.apply: curves, then saturation, then clarity and sharpness. */
fun applyEdit(src: Pixels, a: Adjustments): Pixels {
    if (a.unchanged) return src
    var p = src.copy()
    if (!a.tonesUnchanged) {
        val lut = lookupTable(a)
        val px = p.argb
        for (i in px.indices) {
            val c = px[i]
            px[i] = (c and -0x1000000) or (lut[0][(c shr 16) and 0xFF] shl 16) or
                (lut[1][(c shr 8) and 0xFF] shl 8) or lut[2][c and 0xFF]
        }
    }
    if (!a.saturationUnchanged) saturate(p, saturationGains(a))
    if (!a.detailUnchanged) p = detail(p, a)
    return p
}

/** Pillow's RGB -> HSV -> RGB (all 0..255), with saturation multiplied by the gain for its hue. */
private fun saturate(p: Pixels, gains: DoubleArray) {
    val px = p.argb
    for (i in px.indices) {
        val c = px[i]
        val r = (c shr 16) and 0xFF; val g = (c shr 8) and 0xFF; val b = c and 0xFF
        val mx = max(r, max(g, b)); val mn = min(r, min(g, b))
        if (mx == mn) continue  // grey stays grey
        val v = mx
        val s = (mx - mn).toDouble() / mx
        val cr = (mx - r).toDouble() / (mx - mn); val cg = (mx - g).toDouble() / (mx - mn)
        val cb = (mx - b).toDouble() / (mx - mn)
        var h = when (mx) { r -> cb - cg; g -> 2.0 + cr - cb; else -> 4.0 + cg - cr }
        h = (h / 6.0).let { if (it < 0) it + 1.0 else it }
        val hByte = (h * 255).roundToInt().coerceIn(0, 255)
        val s2 = min(1.0, (s * 255).roundToInt() * gains[hByte] / 255.0)
        // HSV -> RGB
        val hh = hByte / 255.0 * 6.0
        val sector = hh.toInt() % 6
        val f = hh - hh.toInt()
        val vv = v.toDouble()
        val pp = vv * (1 - s2); val q = vv * (1 - s2 * f); val t = vv * (1 - s2 * (1 - f))
        val (nr, ng, nb) = when (sector) {
            0 -> Triple(vv, t, pp); 1 -> Triple(q, vv, pp); 2 -> Triple(pp, vv, t)
            3 -> Triple(pp, q, vv); 4 -> Triple(t, pp, vv); else -> Triple(vv, pp, q)
        }
        px[i] = (c and -0x1000000) or (nr.roundToInt().coerceIn(0, 255) shl 16) or
            (ng.roundToInt().coerceIn(0, 255) shl 8) or nb.roundToInt().coerceIn(0, 255)
    }
}

/** Clarity and Sharpness; their sizes follow the picture's (so a preview looks like the saved photo). */
fun detail(p: Pixels, a: Adjustments): Pixels {
    var out = p
    val longSide = max(p.width, p.height)
    if (a.clarity != 0) {
        val blur = gaussianBlur(out, max(4.0, longSide / 60.0))
        val amount = a.clarity / 100.0 * (if (a.clarity > 0) 0.6 else 0.5)
        val px = out.argb; val bl = blur.argb
        val res = IntArray(px.size)
        for (i in px.indices) {
            val c = px[i]; val d = bl[i]
            val r = (c shr 16) and 0xFF; val g = (c shr 8) and 0xFF; val b = c and 0xFF
            val lum = (r * 299 + g * 587 + b * 114) / 1000
            val mask = sin(PI * lum / 255)  // the mid-tones only
            fun mix(o: Int, bv: Int): Int {
                val moved = if (amount > 0) bv + (o - bv) * (1 + amount) else o + (bv - o) * -amount
                return (moved * mask + o * (1 - mask)).roundToInt().coerceIn(0, 255)
            }
            res[i] = (c and -0x1000000) or (mix(r, (d shr 16) and 0xFF) shl 16) or
                (mix(g, (d shr 8) and 0xFF) shl 8) or mix(b, d and 0xFF)
        }
        out = Pixels(p.width, p.height, res)
    }
    if (a.sharpness != 0) {
        val radius = max(0.8, longSide / 1000.0)
        val percent = a.sharpness * 4
        val blur = gaussianBlur(out, radius)
        val px = out.argb; val bl = blur.argb
        val res = IntArray(px.size)
        for (i in px.indices) {
            val c = px[i]; val d = bl[i]
            fun sharpen(shift: Int): Int {
                val o = (c shr shift) and 0xFF
                val diff = o - ((d shr shift) and 0xFF)
                return if (abs(diff) >= 1) (o + diff * percent / 100.0).roundToInt().coerceIn(0, 255) else o
            }
            res[i] = (c and -0x1000000) or (sharpen(16) shl 16) or (sharpen(8) shl 8) or sharpen(0)
        }
        out = Pixels(p.width, p.height, res)
    }
    return out
}

/** A Gaussian blur (radius = standard deviation, as Pillow's) made of three box blurs. */
fun gaussianBlur(p: Pixels, sigma: Double): Pixels {
    val n = 3
    val wIdeal = sqrt(12 * sigma * sigma / n + 1)
    var wl = wIdeal.toInt(); if (wl % 2 == 0) wl--
    val wu = wl + 2
    val mIdeal = (12 * sigma * sigma - n * wl * wl - 4 * n * wl - 3 * n) / (-4 * wl - 4)
    val m = mIdeal.roundToInt()
    var cur = p
    for (k in 0 until n) {
        val r = ((if (k < m) wl else wu) - 1) / 2
        cur = boxBlur(cur, r)
    }
    return cur
}

private fun boxBlur(p: Pixels, r: Int): Pixels {
    if (r <= 0) return p
    val w = p.width; val h = p.height
    val tmp = IntArray(w * h)
    val out = IntArray(w * h)
    for (pass in 0..1) {
        val src = if (pass == 0) p.argb else tmp
        val dst = if (pass == 0) tmp else out
        val lines = if (pass == 0) h else w
        val len = if (pass == 0) w else h
        for (line in 0 until lines) {
            fun idx(j: Int) = if (pass == 0) line * w + j else j * w + line
            var sr = 0; var sg = 0; var sb = 0
            val win = 2 * r + 1
            for (j in -r..r) {
                val c = src[idx(j.coerceIn(0, len - 1))]
                sr += (c shr 16) and 0xFF; sg += (c shr 8) and 0xFF; sb += c and 0xFF
            }
            for (j in 0 until len) {
                val a = src[idx(j)] and -0x1000000
                dst[idx(j)] = a or ((sr / win) shl 16) or ((sg / win) shl 8) or (sb / win)
                val add = src[idx((j + r + 1).coerceAtMost(len - 1))]
                val sub = src[idx((j - r).coerceAtLeast(0))]
                sr += ((add shr 16) and 0xFF) - ((sub shr 16) and 0xFF)
                sg += ((add shr 8) and 0xFF) - ((sub shr 8) and 0xFF)
                sb += (add and 0xFF) - (sub and 0xFF)
            }
        }
    }
    return Pixels(w, h, out)
}

// ------------------------------------------------------------------ auto and white balance
private fun slider(v: Double) = (v * 100).roundToInt().coerceIn(-100, 100)

/** The Blue/Yellow and Green/Red values that make the colour (r, g, b) grey. */
fun neutral(r: Double, g: Double, b: Double): Pair<Int, Int> {
    if (min(r, min(g, b)) <= 0) return 0 to 0
    val a1 = WARM[0] * r - WARM[1] * g; val b1 = TINT[0] * r - TINT[1] * g; val c1 = g - r
    val a2 = WARM[1] * g - WARM[2] * b; val b2 = TINT[1] * g - TINT[2] * b; val c2 = b - g
    val det = a1 * b2 - a2 * b1
    if (abs(det) < 1e-9) return 0 to 0
    return slider((c1 * b2 - c2 * b1) / det) to slider((a1 * c2 - a2 * c1) / det)
}

/** White balance from the spot around (x, y). */
fun whiteBalanceAt(p: Pixels, x: Int, y: Int, radius: Int = 3): Pair<Int, Int> {
    var r = 0.0; var g = 0.0; var b = 0.0; var n = 0
    for (yy in max(0, y - radius)..min(p.height - 1, y + radius))
        for (xx in max(0, x - radius)..min(p.width - 1, x + radius)) {
            val c = p.argb[yy * p.width + xx]
            r += (c shr 16) and 0xFF; g += (c shr 8) and 0xFF; b += c and 0xFF; n++
        }
    return if (n == 0) 0 to 0 else neutral(r / n, g / n, b / n)
}

private fun percentile(hist: IntArray, fraction: Double): Int {
    val total = hist.sum(); var running = 0
    for (v in 0..255) { running += hist[v]; if (running >= total * fraction) return v }
    return 255
}

/** A suggestion for each slider, as photo_edit.auto (pass a small copy, ~400 px). */
fun auto(p: Pixels): Map<String, Int> {
    val px = p.argb
    val lum = IntArray(px.size) { val c = px[it]; (((c shr 16) and 0xFF) * 299 + ((c shr 8) and 0xFF) * 587 + (c and 0xFF) * 114) / 1000 }
    var r = 0.0; var g = 0.0; var b = 0.0; var n = 0
    for (i in px.indices) if (lum[i] in 30..225) {
        val c = px[i]; r += (c shr 16) and 0xFF; g += (c shr 8) and 0xFF; b += c and 0xFF; n++
    }
    if (n == 0) for (c in px) { r += (c shr 16) and 0xFF; g += (c shr 8) and 0xFF; b += c and 0xFF; n++ }
    val (yellow, red) = neutral(r / n, g / n, b / n)
    val out = linkedMapOf("yellow" to (yellow * 0.8).roundToInt(), "red" to (red * 0.8).roundToInt())
    val hist = IntArray(256).also { h -> lum.forEach { h[it]++ } }
    val low = percentile(hist, 0.01); val high = percentile(hist, 0.99)
    val spread = high - low
    val factor = if (spread >= 30) (235.0 / spread).coerceIn(0.7, 1.5) else 1.0
    out["contrast"] = slider((factor - 1) / (if (factor >= 1) CONTRAST_UP else CONTRAST_DOWN))
    val middle = percentile(hist, 0.5) / 255.0
    out["brightness"] = if (spread >= 30 && middle > 0.02 && middle < 0.98)
        slider(-log2(ln(0.45) / ln(middle)) / BRIGHTNESS * 0.7).coerceIn(-60, 60) else 0
    var x = percentile(hist, 0.10) / 255.0
    var shape = LIFT * (1 - x).pow(2) * (1 - (1 - x).pow(6))
    out["shadows"] = if (x < 0.18 && shape > 0.01) max(0, slider((0.18 - x) / shape)) else 0
    x = percentile(hist, 0.90) / 255.0
    shape = LIFT * x.pow(2) * (1 - x.pow(6))
    out["highlights"] = when {
        x > 0.86 && shape > 0.01 -> min(0, slider((0.82 - x) / shape))
        x < 0.62 && shape > 0.01 && spread >= 30 -> slider((0.70 - x) / shape).coerceIn(0, 40)
        else -> 0
    }
    // Detail, gently: a soft photo gets more sharpening; a flat one a little more clarity.
    var edges = 0.0
    for (yy in 1 until p.height - 1) for (xx in 1 until p.width - 1) {
        val i = yy * p.width + xx
        edges += abs(8 * lum[i] - lum[i - 1] - lum[i + 1] - lum[i - p.width] - lum[i + p.width] -
            lum[i - p.width - 1] - lum[i - p.width + 1] - lum[i + p.width - 1] - lum[i + p.width + 1]).coerceAtMost(255)
    }
    edges /= max(1, (p.width - 2) * (p.height - 2))
    out["sharpness"] = (45 - 2 * edges).roundToInt().coerceIn(10, 40)
    val mids = lum.filter { it in 40..215 }
    val std = if (mids.isEmpty()) 0.0 else mids.average().let { avg -> sqrt(mids.sumOf { (it - avg) * (it - avg) } / mids.size) }
    out["clarity"] = if (std < 35) 25 else 12
    if (spread < 30) { out["sharpness"] = 0; out["clarity"] = 0 }
    return out
}
