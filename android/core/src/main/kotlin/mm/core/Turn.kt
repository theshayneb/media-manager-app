package mm.core

/**
 * Rotate and flip (as the Windows app's photo_edit.Turn): the picture mirrored left-right (if mirror), then
 * turned clockwise quarter × 90°. Every mix of ↻, Flip horizontal and Flip vertical is one of these eight;
 * so is every EXIF orientation.
 */
data class Turn(val quarter: Int = 0, val mirror: Boolean = false) {
    val unchanged get() = quarter.mod(4) == 0 && !mirror

    /** ↻: 90° clockwise more. */
    fun rotated() = Turn((quarter + 1).mod(4), mirror)

    /** The picture as it is now, mirrored left-right (or top-bottom). */
    fun flipped(vertical: Boolean = false) = Turn(((if (vertical) 2 else 0) - quarter).mod(4), !mirror)

    /** This, then [after]. */
    fun then(after: Turn) =
        if (after.mirror) Turn((after.quarter - quarter).mod(4), !mirror) else Turn((after.quarter + quarter).mod(4), mirror)

    fun inverse() = if (mirror) this else Turn((-quarter).mod(4), false)

    fun apply(p: Pixels): Pixels {
        var w = p.width; var h = p.height; var px = p.argb
        if (mirror) {
            val out = IntArray(px.size)
            for (y in 0 until h) for (x in 0 until w) out[y * w + x] = px[y * w + (w - 1 - x)]
            px = out
        }
        repeat(quarter.mod(4)) {  // 90° clockwise: (x, y) -> (h - 1 - y, x), w × h -> h × w
            val out = IntArray(px.size)
            for (y in 0 until h) for (x in 0 until w) out[x * h + (h - 1 - y)] = px[y * w + x]
            px = out
            val t = w; w = h; h = t
        }
        return Pixels(w, h, px)
    }

    /** A box (fractions left, top, right, bottom) on the turned picture -> the same part of the picture before. */
    fun boxBack(box: List<Double>): List<Double> {
        var corners = listOf(box[0] to box[1], box[2] to box[3])
        repeat(quarter.mod(4)) { corners = corners.map { (x, y) -> y to 1 - x } }
        if (mirror) corners = corners.map { (x, y) -> 1 - x to y }
        return listOf(corners.minOf { it.first }, corners.minOf { it.second }, corners.maxOf { it.first }, corners.maxOf { it.second })
    }

    fun toList() = listOf(quarter.mod(4), if (mirror) 1 else 0)

    companion object {
        fun fromList(list: List<Int>?) = if (list == null || list.size < 2) Turn() else Turn(list[0], list[1] != 0)

        /** What an EXIF orientation does to the file's pixels to show them upright. */
        fun ofOrientation(orientation: Int) = when (orientation) {
            2 -> Turn(0, true); 3 -> Turn(2, false); 4 -> Turn(2, true); 5 -> Turn(3, true)
            6 -> Turn(1, false); 7 -> Turn(1, true); 8 -> Turn(3, false)
            else -> Turn()
        }
    }
}
