package mm.companion

import android.app.Activity
import android.content.pm.ActivityInfo
import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectTransformGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import mm.core.Change
import mm.core.LABELS
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.ceil
import kotlin.math.min
import kotlin.math.roundToInt

const val MAX_COMPARE = 4
private val WHEN = DateTimeFormatter.ofPattern("EEE, MMM d, h:mm a")

/**
 * Compare (as Photos' compare on the PC): 2–4 photos side by side, the phone turned sideways, each as big as the
 * screen allows (never cropped). Tap one to make it the active one: the bar acts on it. Pinch zooms them all to
 * the same spot; double-tap fits them again.
 */
@Composable
fun CompareScreen(model: AppModel) {
    val photos = model.comparing
    val context = LocalContext.current
    DisposableEffect(Unit) {  // sideways while comparing; as the phone is held again after
        val activity = context as? Activity
        activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        onDispose { activity?.requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_UNSPECIFIED }
    }
    BackHandler { model.leaveCompare() }
    androidx.compose.runtime.LaunchedEffect(photos.size) { if (photos.size < 2) model.leaveCompare() }
    if (photos.size < 2) return
    val active = photos.firstOrNull { it.id == model.compareActive } ?: photos[0]
    val images = remember { mutableStateMapOf<Long, ImageBitmap>() }
    for (p in photos) androidx.compose.runtime.key(p.id) {
        androidx.compose.runtime.LaunchedEffect(p.id) {
            model.loadFields(p)
            val bytes = runCatching { model.readForEdit(p) }.getOrNull() ?: return@LaunchedEffect
            withContext(Dispatchers.Default) { runCatching { decodePreview(bytes, 1600) }.getOrNull() }
                ?.let { images[p.id] = it.asImageBitmap() }
        }
    }
    // one zoom for all of them: scale, and where it's centred (a fraction of each photo)
    var scale by remember { mutableFloatStateOf(1f) }
    var centre by remember { mutableStateOf(Offset(0.5f, 0.5f)) }

    Column(Modifier.fillMaxSize().background(Background)) {
        // the bar: acts on the active photo
        val f = model.fields[active.id]
        Row(Modifier.fillMaxWidth().padding(horizontal = 4.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { model.leaveCompare() }) { LineIcon(Line.Back, "Back") }
            Text(active.name, fontWeight = FontWeight.SemiBold, fontSize = 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.weight(1f, fill = false))
            val taken = if (active.takenMillis > 0) Instant.ofEpochMilli(active.takenMillis).atZone(ZoneId.systemDefault()).format(WHEN) else ""
            Text("  $taken", color = Dim, fontSize = 13.sp, maxLines = 1)
            Spacer(Modifier.weight(1f).width(8.dp))
            for (label in LABELS) {
                val on = f?.label == label
                Box(Modifier.padding(horizontal = 3.dp).size(26.dp)
                    .then(if (on) Modifier.border(2.dp, Color.White, CircleShape) else Modifier)
                    .padding(3.dp).clip(CircleShape).background(LabelColours[label]!!)
                    .clickable { model.apply(Change.Label(if (on) "" else label), listOf(active)) })
            }
            val starred = f?.starred == true
            val marked = f?.bookmarked == true
            Text("⭐", fontSize = 17.sp, modifier = Modifier.padding(start = 8.dp).clip(RoundedCornerShape(8.dp))
                .background(if (starred) Color(0xFF3E434B) else Color.Transparent)
                .clickable { model.apply(Change.Flag("Star", !starred), listOf(active)) }.padding(6.dp))
            Text("🔖", fontSize = 17.sp, modifier = Modifier.clip(RoundedCornerShape(8.dp))
                .background(if (marked) Color(0xFF3E434B) else Color.Transparent)
                .clickable { model.apply(Change.Flag("Bookmark", !marked), listOf(active)) }.padding(6.dp))
            if (active.canChange) IconButton(onClick = {
                model.comparing = emptyList()
                model.editing = active; model.screen = Screen.Edit
            }) { LineIcon(Line.Pencil, "Edit") }
            IconButton(onClick = {
                model.delete(listOf(active)) {
                    model.comparing = model.comparing.filterNot { it.id == active.id }
                    if (model.comparing.size < 2) model.leaveCompare()
                }
            }) { LineIcon(Line.Delete, "Delete") }
        }
        if (model.message.isNotEmpty()) Note(model)
        // the photos, laid out to be as big as they can
        BoxWithConstraints(Modifier.fillMaxSize().padding(4.dp)) {
            val ratios = photos.map { p -> images[p.id]?.let { it.width.toFloat() / it.height } ?: 1.5f }
            val (rows, cols) = bestLayout(ratios, maxWidth.value, maxHeight.value)
            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                for (r in 0 until rows) {
                    Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        for (c in 0 until cols) {
                            val i = r * cols + c
                            if (i >= photos.size) { Spacer(Modifier.weight(1f)); continue }
                            val p = photos[i]
                            Pane(model, p, images[p.id], p.id == active.id, scale, centre, Modifier.weight(1f).fillMaxSize(),
                                onTap = { model.compareActive = p.id },
                                onFit = { scale = 1f; centre = Offset(0.5f, 0.5f) },
                                onZoom = zoom@{ zoom, pan, size ->
                                    if (size.width <= 0f || size.height <= 0f) return@zoom
                                    val s = (scale * zoom).coerceIn(1f, 8f)
                                    // a pan of `pan` pixels moves the shared centre by that much of the zoomed photo
                                    val nc = centre - Offset(pan.x / (size.width * s), pan.y / (size.height * s))
                                    scale = s
                                    centre = Offset(nc.x.coerceIn(0f, 1f), nc.y.coerceIn(0f, 1f))
                                })
                        }
                    }
                }
            }
        }
    }
}

/** Rows and columns that show the photos (these width/height ratios) biggest in a w × h area. */
private fun bestLayout(ratios: List<Float>, w: Float, h: Float): Pair<Int, Int> {
    val n = ratios.size
    var best = 1 to n
    var bestArea = -1f
    for (cols in 1..n) {
        val rows = ceil(n / cols.toFloat()).toInt()
        val cw = w / cols; val ch = h / rows
        val smallest = ratios.minOf { r -> val pw = min(cw, ch * r); pw * (pw / r) }  // the smallest photo's area
        if (smallest > bestArea) { bestArea = smallest; best = rows to cols }
    }
    return best
}

@Composable
private fun Pane(model: AppModel, p: Photo, image: ImageBitmap?, active: Boolean, scale: Float, centre: Offset,
                 modifier: Modifier, onTap: () -> Unit, onFit: () -> Unit,
                 onZoom: (Float, Offset, androidx.compose.ui.geometry.Size) -> Unit) {
    val f = model.fields[p.id]
    val paneSize = remember { arrayOf(androidx.compose.ui.geometry.Size.Zero) }  // the fitted photo's size (set when drawn)
    Box(modifier.clip(RoundedCornerShape(6.dp)).background(Color(0xFF17181B))
        .border(3.dp, if (active) Accent else Color.Transparent, RoundedCornerShape(6.dp))) {
        Canvas(Modifier.fillMaxSize().clipToBounds()
            .pointerInput(p.id) { detectTapGestures(onTap = { onTap() }, onDoubleTap = { onFit() }) }
            .pointerInput(p.id) { detectTransformGestures { _, pan, zoom, _ -> onZoom(zoom, pan, paneSize[0]) } }) {
            val img = image ?: return@Canvas
            val fit = min(size.width / img.width, size.height / img.height)
            val w = img.width * fit * scale; val h = img.height * fit * scale
            paneSize[0] = androidx.compose.ui.geometry.Size(img.width * fit, img.height * fit)
            // the shared centre (a fraction of the photo) in the middle of the pane, kept inside the photo
            var left = size.width / 2 - centre.x * w
            var top = size.height / 2 - centre.y * h
            left = if (w <= size.width) (size.width - w) / 2 else left.coerceIn(size.width - w, 0f)
            top = if (h <= size.height) (size.height - h) / 2 else top.coerceIn(size.height - h, 0f)
            drawImage(img, IntOffset.Zero, IntSize(img.width, img.height), IntOffset(left.roundToInt(), top.roundToInt()),
                IntSize(w.roundToInt(), h.roundToInt()))
        }
        LabelColours[f?.label]?.let { Box(Modifier.align(Alignment.BottomCenter).padding(bottom = 22.dp).fillMaxWidth().height(4.dp).background(it)) }
        if (f != null && (f.starred || f.bookmarked)) {
            Text((if (f.starred) "⭐" else "") + (if (f.bookmarked) "🔖" else ""), fontSize = 12.sp,
                modifier = Modifier.align(Alignment.TopStart).padding(6.dp))
        }
        if (image == null) Text("…", color = Dim, modifier = Modifier.align(Alignment.Center))
        Text(p.name, fontSize = 11.sp, color = Color(0xFFCFD2D6), maxLines = 1, overflow = TextOverflow.Ellipsis,
            modifier = Modifier.align(Alignment.BottomStart).fillMaxWidth().background(Color(0x66000000))
                .padding(horizontal = 6.dp, vertical = 3.dp))
    }
}
