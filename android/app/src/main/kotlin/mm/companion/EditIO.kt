package mm.companion

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Matrix
import androidx.exifinterface.media.ExifInterface
import mm.core.Adjustments
import mm.core.Jpeg
import mm.core.Pixels
import mm.core.Png
import mm.core.Turn
import mm.core.applyEdit
import mm.core.markEdited
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import kotlin.math.roundToInt

fun orientationOf(bytes: ByteArray): Int = try {
    ExifInterface(ByteArrayInputStream(bytes)).getAttributeInt(ExifInterface.TAG_ORIENTATION, 1)
} catch (e: Exception) { 1 }

fun Bitmap.toPixels(): Pixels {
    val px = IntArray(width * height)
    getPixels(px, 0, width, 0, 0, width, height)
    return Pixels(width, height, px)
}

fun Pixels.toBitmap(): Bitmap = Bitmap.createBitmap(argb, width, height, Bitmap.Config.ARGB_8888)

/** The photo upright (its EXIF orientation applied) and no bigger than maxSide, for the screen. */
fun decodePreview(bytes: ByteArray, maxSide: Int = 2400): Bitmap? {
    val bounds = BitmapFactory.Options().apply { inJustDecodeBounds = true }
    BitmapFactory.decodeByteArray(bytes, 0, bytes.size, bounds)
    var sample = 1
    while (maxOf(bounds.outWidth, bounds.outHeight) / (sample * 2) >= maxSide) sample *= 2
    val raw = BitmapFactory.decodeByteArray(bytes, 0, bytes.size, BitmapFactory.Options().apply {
        inSampleSize = sample
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }) ?: return null
    val scaled = if (maxOf(raw.width, raw.height) > maxSide) {
        val f = maxSide.toFloat() / maxOf(raw.width, raw.height)
        Bitmap.createScaledBitmap(raw, (raw.width * f).roundToInt(), (raw.height * f).roundToInt(), true)
    } else raw
    return upright(scaled, orientationOf(bytes))
}

fun upright(bitmap: Bitmap, orientation: Int): Bitmap {
    val m = Matrix()
    when (orientation) {
        ExifInterface.ORIENTATION_ROTATE_90 -> m.postRotate(90f)
        ExifInterface.ORIENTATION_ROTATE_180 -> m.postRotate(180f)
        ExifInterface.ORIENTATION_ROTATE_270 -> m.postRotate(270f)
        ExifInterface.ORIENTATION_FLIP_HORIZONTAL -> m.postScale(-1f, 1f)
        ExifInterface.ORIENTATION_FLIP_VERTICAL -> m.postScale(1f, -1f)
        else -> return bitmap
    }
    return Bitmap.createBitmap(bitmap, 0, 0, bitmap.width, bitmap.height, m, true)
}

/** A crop chosen on the photo as it's shown (fractions left, top, right, bottom) in the file's own pixel order. */
fun cropToRaw(box: List<Double>, orientation: Int): List<Double> = Turn.ofOrientation(orientation).boxBack(box)

/**
 * The edit, done to a whole JPEG or PNG (kept as what it is): the same maths as the preview, then the crop (fractions of the file's own
 * pixels), re-encoded, with all the photo's information (EXIF, XMP, IPTC, colour profile) carried over and
 * the ✨ mark added. The picture keeps its orientation tag, so it shows the right way up everywhere.
 */
fun editImage(src: ByteArray, adjustments: Adjustments, rawCrop: List<Double>?, turn: Turn = Turn()): ByteArray {
    val bitmap = BitmapFactory.decodeByteArray(src, 0, src.size, BitmapFactory.Options().apply {
        inPreferredConfig = Bitmap.Config.ARGB_8888
    }) ?: throw IllegalStateException("Couldn't read the photo")
    var pixels = applyEdit(bitmap.toPixels(), adjustments)
    bitmap.recycle()
    if (!turn.unchanged) {
        // Turned as you see it (upright): in the file's own pixel order, so its orientation tag stays right.
        val o = Turn.ofOrientation(orientationOf(src))
        pixels = o.then(turn).then(o.inverse()).apply(pixels)
    }
    if (rawCrop != null) {
        val (l, t, r, b) = rawCrop
        pixels = pixels.crop((l * pixels.width).roundToInt(), (t * pixels.height).roundToInt(),
            (r * pixels.width).roundToInt(), (b * pixels.height).roundToInt())
    }
    val out = ByteArrayOutputStream()
    val png = Png.isPng(src)
    pixels.toBitmap().compress(if (png) Bitmap.CompressFormat.PNG else Bitmap.CompressFormat.JPEG, if (png) 100 else 95, out)
    val encoded = out.toByteArray()
    val withInfo = when {
        png -> Png.parse(src).transplantInto(encoded)
        Jpeg.isJpeg(src) -> Jpeg.parse(src).transplantInto(encoded)
        else -> encoded
    }
    return markEdited(withInfo)
}
