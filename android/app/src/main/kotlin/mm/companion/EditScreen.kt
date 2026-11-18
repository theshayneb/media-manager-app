package mm.companion

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.setValue
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ImageBitmap
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.withContext
import mm.core.Adjustments
import mm.core.Pixels
import mm.core.applyEdit
import mm.core.auto
import mm.core.whiteBalanceAt
import kotlin.math.abs
import kotlin.math.max
import kotlin.math.min
import kotlin.math.roundToInt

private data class Row5(val key: String, val name: String, val left: String, val right: String, val colours: List<Color>)

private val LIGHT = listOf(
    Row5("yellow", "Blue ↔ Yellow", "Bluer", "Yellower", listOf(Color(0xFF3B78D8), Color(0xFF777777), Color(0xFFD8B83B))),
    Row5("red", "Green ↔ Red", "Greener", "Redder", listOf(Color(0xFF3BB85A), Color(0xFF777777), Color(0xFFD84A3B))),
    Row5("brightness", "Brightness", "Darker", "Brighter", listOf(Color(0xFF222222), Color(0xFFDDDDDD))),
    Row5("contrast", "Contrast", "Less", "More", listOf(Color(0xFF555555), Color(0xFF999999))),
    Row5("shadows", "Shadows", "Darker", "Lighter", listOf(Color(0xFF111111), Color(0xFF888888))),
    Row5("highlights", "Highlights", "Darker", "Brighter", listOf(Color(0xFF666666), Color(0xFFEEEEEE))),
)
private val DETAIL = listOf(
    Row5("sharpness", "Sharpness", "None", "More", listOf(Color(0xFF555555), Color(0xFFBBBBBB))),
    Row5("clarity", "Clarity", "Softer", "More punch", listOf(Color(0xFF666666), Color(0xFFCCCCCC))),
)
private val COLOUR = listOf("sat_all" to "All colours", "sat_red" to "Red", "sat_orange" to "Orange",
    "sat_yellow" to "Yellow", "sat_green" to "Green", "sat_aqua" to "Aqua", "sat_blue" to "Blue",
    "sat_purple" to "Purple", "sat_pink" to "Pink")
private val SAT_COLOURS = listOf(Color(0xFFC8C8C8), Color(0xFFE04040), Color(0xFFF08A30), Color(0xFFE8D040),
    Color(0xFF40B050), Color(0xFF30C0C0), Color(0xFF3B78D8), Color(0xFF9050D0), Color(0xFFE050A0))
private val RATIOS = listOf("Free" to null, "Original" to -1f, "6×4" to 1.5f, "4×6" to 2f / 3f, "4×3" to 4f / 3f,
    "3×4" to 3f / 4f, "Square" to 1f)

@Composable
fun EditScreen(model: AppModel, photo: Photo) {
    var preview by remember { mutableStateOf<Bitmap?>(null) }
    var pixels by remember { mutableStateOf<Pixels?>(null) }
    var after by remember { mutableStateOf<ImageBitmap?>(null) }
    val values = remember { mutableStateMapOf<String, Int>() }
    val on = remember { mutableStateMapOf<String, Boolean>() }
    var tab by remember { mutableStateOf(0) }
    var split by remember { mutableFloatStateOf(0f) }
    var holding by remember { mutableStateOf(false) }
    var picking by remember { mutableStateOf(false) }
    var cropping by remember { mutableStateOf(false) }
    var crop by remember { mutableStateOf<List<Double>?>(null) }
    var ratio by remember { mutableStateOf<Float?>(null) }
    var asking by remember { mutableStateOf(false) }
    var suggestions by remember { mutableStateOf<Map<String, Int>?>(null) }

    fun adjustments() = Adjustments.fromMap(values.filter { on[it.key] != false })
    fun changed() = !adjustments().unchanged || crop != null

    LaunchedEffect(photo.id) {
        val bmp = withContext(Dispatchers.IO) { runCatching { decodePreview(model.store.read(photo), 2048) }.getOrNull() }
        preview = bmp
        pixels = bmp?.toPixels()
        after = bmp?.asImageBitmap()
    }
    LaunchedEffect(Unit) {
        snapshotFlow { adjustments() to pixels }.collectLatest { (a, p) ->
            if (p == null) return@collectLatest
            val out = withContext(Dispatchers.Default) { applyEdit(p, a).toBitmap() }
            after = out.asImageBitmap()
        }
    }

    fun leave() { model.screen = Screen.Grid; model.editing = null }
    BackHandler { if (cropping) cropping = false else if (changed()) asking = true else leave() }
    if (asking) AlertDialog(onDismissRequest = { asking = false }, title = { Text("Save the edit?") },
        confirmButton = { TextButton(onClick = { asking = false; model.saveEdit(photo, adjustments(), crop) { leave() } }) { Text("Save") } },
        dismissButton = {
            Row {
                TextButton(onClick = { asking = false; leave() }) { Text("Don't save") }
                TextButton(onClick = { asking = false }) { Text("Keep editing") }
            }
        })

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(Panel).padding(6.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { if (changed()) asking = true else leave() }) { Text("←  Edit", color = Color.White, fontSize = 17.sp) }
            Box(Modifier.weight(1f))
            TextButton(onClick = {
                cropping = !cropping
                if (cropping && crop == null) crop = listOf(0.05, 0.05, 0.95, 0.95)
            }) { Text(if (cropping) "✓ Done" else "✂ Crop", color = Color.White) }
            Button(onClick = { model.saveEdit(photo, adjustments(), crop) { leave() } }, enabled = changed() && !model.busy) {
                if (model.busy) CircularProgressIndicator(Modifier.width(18.dp).height(18.dp), strokeWidth = 2.dp) else Text("Save")
            }
        }
        Note(model)
        val img = after
        val before = preview?.asImageBitmap()
        Box(Modifier.fillMaxWidth().weight(1f).background(Color(0xFF1B1C1F))) {
            if (img != null && before != null) PhotoView(img, before, split, holding, picking, cropping, crop, ratio,
                onSplit = { split = it }, onHold = { holding = it }, onCrop = { crop = it },
                onPick = { fx, fy ->
                    val p = pixels ?: return@PhotoView
                    val (y, r) = whiteBalanceAt(p, (fx * p.width).toInt(), (fy * p.height).toInt(), max(2, p.width / 300))
                    values["yellow"] = y; values["red"] = r; on["yellow"] = true; on["red"] = true
                    picking = false
                })
            else CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
        if (cropping) {
            Row(Modifier.fillMaxWidth().background(Panel).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                for ((name, r) in RATIOS) {
                    val chosen = ratio == r || (name == "Free" && ratio == null)
                    Text(name, fontSize = 12.sp, modifier = Modifier.clip(RoundedCornerShape(14.dp))
                        .background(if (chosen) Accent else Color(0xFF33363C)).clickable {
                            val pv = preview
                            ratio = if (r == -1f && pv != null) pv.width.toFloat() / pv.height else r
                            crop = fitRatio(crop ?: listOf(0.05, 0.05, 0.95, 0.95), ratio, pv)
                        }.padding(horizontal = 10.dp, vertical = 6.dp))
                }
            }
            TextButton(onClick = { crop = null; cropping = false }) { Text("No crop", color = Dim) }
            return@Column
        }
        Column(Modifier.fillMaxWidth().weight(1f).background(Panel).padding(horizontal = 12.dp)) {
            Row(Modifier.fillMaxWidth().padding(vertical = 6.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                for ((i, t) in listOf("Light", "Detail", "Colour").withIndex()) {
                    Text(t, fontSize = 13.sp, modifier = Modifier.weight(1f).clip(RoundedCornerShape(16.dp))
                        .background(if (tab == i) Accent else Color(0xFF33363C)).clickable { tab = i }
                        .padding(vertical = 7.dp), textAlign = androidx.compose.ui.text.style.TextAlign.Center)
                }
            }
            Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) {
                fun autoOne(key: String) {
                    val p = pixels ?: return
                    val s = suggestions ?: auto(smaller(p)).also { suggestions = it }
                    values[key] = s[key] ?: 0; on[key] = true
                }
                val rows = when (tab) { 0 -> LIGHT; 1 -> DETAIL; else -> emptyList() }
                for (r in rows) SliderRow(r.name, values[r.key] ?: 0, on[r.key] != false, r.colours,
                    if (r.key == "sharpness") 0f else -100f, { values[r.key] = it }, { on[r.key] = it }, { autoOne(r.key) })
                if (tab == 2) for ((i, kv) in COLOUR.withIndex()) {
                    SliderRow(kv.second, values[kv.first] ?: 0, on[kv.first] != false,
                        listOf(Color(0xFF777777), SAT_COLOURS[i]), -100f, { values[kv.first] = it }, { on[kv.first] = it }, null)
                }
                Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { picking = !picking }, Modifier.weight(1f)) {
                        Text(if (picking) "Tap something white…" else "Pick white", fontSize = 13.sp)
                    }
                    OutlinedButton(onClick = {
                        for ((k, v) in model.lastEdit) { values[k] = v; on[k] = true }
                    }, Modifier.weight(1f), enabled = model.lastEdit.isNotEmpty()) { Text("Same as last edit", fontSize = 13.sp) }
                }
            }
        }
    }
}

private fun smaller(p: Pixels): Pixels {
    val step = max(1, max(p.width, p.height) / 400)
    val w = p.width / step; val h = p.height / step
    return Pixels(w, h, IntArray(w * h) { i -> p.argb[(i / w) * step * p.width + (i % w) * step] })
}

/** A crop box with this shape (width / height of the upright photo), centred in the old one. */
private fun fitRatio(box: List<Double>, ratio: Float?, photo: Bitmap?): List<Double> {
    if (ratio == null || photo == null) return box
    val (l, t, r, b) = box
    var w = (r - l) * photo.width; var h = (b - t) * photo.height
    if (w / h > ratio) w = h * ratio else h = w / ratio
    val cx = (l + r) / 2 * photo.width; val cy = (t + b) / 2 * photo.height
    val fw = w / photo.width; val fh = h / photo.height
    val nl = (cx / photo.width - fw / 2).coerceIn(0.0, 1 - fw); val nt = (cy / photo.height - fh / 2).coerceIn(0.0, 1 - fh)
    return listOf(nl, nt, nl + fw, nt + fh)
}

@Composable
private fun SliderRow(name: String, value: Int, enabled: Boolean, colours: List<Color>, min: Float,
                      onValue: (Int) -> Unit, onEnabled: (Boolean) -> Unit, onAuto: (() -> Unit)?) {
    Column(Modifier.padding(vertical = 2.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Checkbox(enabled, onEnabled)
            Text(name, fontSize = 14.sp, color = if (enabled) Color.White else Dim, modifier = Modifier.weight(1f))
            Text(if (value == 0) "0" else "%+d".format(value), color = Dim, fontSize = 13.sp)
            TextButton(onClick = { onValue(0) }, enabled = value != 0 && enabled) { Text("↺") }
            if (onAuto != null) TextButton(onClick = onAuto, enabled = enabled) { Text("A") }
        }
        Box(Modifier.padding(start = 12.dp, end = 12.dp)) {
            Canvas(Modifier.fillMaxWidth().height(6.dp).align(Alignment.Center)) {
                drawRoundRect(androidx.compose.ui.graphics.Brush.horizontalGradient(if (enabled) colours else listOf(Color(0xFF44474D), Color(0xFF44474D))),
                    cornerRadius = androidx.compose.ui.geometry.CornerRadius(3.dp.toPx()))
            }
            Slider(value.toFloat(), { onValue(it.roundToInt()) }, enabled = enabled, valueRange = min..100f,
                colors = androidx.compose.material3.SliderDefaults.colors(activeTrackColor = Color.Transparent,
                    inactiveTrackColor = Color.Transparent, thumbColor = Color(0xFFE6E6E6)))
        }
    }
}

/**
 * The photo: the original left of the line, the edit right of it. Drag the line; press and hold anywhere
 * else for the whole original; pinch to zoom (then drag to look around). While picking white, a tap picks;
 * while cropping, drag the box or its corners.
 */
@Composable
private fun PhotoView(after: ImageBitmap, before: ImageBitmap, split: Float, holding: Boolean, picking: Boolean,
                      cropping: Boolean, crop: List<Double>?, ratio: Float?,
                      onSplit: (Float) -> Unit, onHold: (Boolean) -> Unit, onCrop: (List<Double>) -> Unit,
                      onPick: (Float, Float) -> Unit) {
    var scale by remember { mutableFloatStateOf(1f) }
    var offset by remember { mutableStateOf(Offset.Zero) }
    var area by remember { mutableStateOf(Size.Zero) }

    fun fitted(): Rect {
        if (area.width == 0f) return Rect.Zero
        val s = min(area.width / after.width, area.height / after.height)
        val w = after.width * s * scale; val h = after.height * s * scale
        return Rect(Offset((area.width - w) / 2 + offset.x, (area.height - h) / 2 + offset.y), Size(w, h))
    }

    // The crop box as it is now, read when a finger goes down. (It isn't a key of pointerInput: each change
    // restarted the gesture, so the box stopped after the first move.)
    val currentCrop by rememberUpdatedState(crop)
    Canvas(Modifier.fillMaxSize().pointerInput(picking, cropping, ratio) {
        awaitEachGesture {
            val down = awaitFirstDown()
            val crop = currentCrop
            val rect = fitted()
            if (picking) {
                if (rect.contains(down.position)) onPick((down.position.x - rect.left) / rect.width, (down.position.y - rect.top) / rect.height)
                return@awaitEachGesture
            }
            val lineX = rect.left + rect.width * split
            val onLine = !cropping && abs(down.position.x - max(lineX, rect.left)) < 40.dp.toPx()
            var corner = -1
            var startBox = crop
            if (cropping && crop != null) {
                val pts = listOf(Offset(crop[0].toFloat(), crop[1].toFloat()), Offset(crop[2].toFloat(), crop[1].toFloat()),
                    Offset(crop[0].toFloat(), crop[3].toFloat()), Offset(crop[2].toFloat(), crop[3].toFloat()))
                    .map { Offset(rect.left + it.x * rect.width, rect.top + it.y * rect.height) }
                corner = pts.indexOfFirst { (it - down.position).getDistance() < 36.dp.toPx() }
            }
            val startPos = down.position
            val startTime = System.currentTimeMillis()
            var moved = false
            var held = false
            while (true) {
                val event = awaitPointerEvent()
                val pressed = event.changes.filter { it.pressed }
                if (pressed.isEmpty()) break
                if (event.changes.size >= 2) {  // pinch
                    scale = (scale * event.calculateZoom()).coerceIn(0.25f, 6f)
                    offset += event.calculatePan()
                    moved = true
                    event.changes.forEach { it.consume() }
                    continue
                }
                val pos = pressed[0].position
                if ((pos - startPos).getDistance() > 8.dp.toPx()) moved = true
                when {
                    cropping && startBox != null -> {
                        val dx = ((pos.x - startPos.x) / rect.width).toDouble(); val dy = ((pos.y - startPos.y) / rect.height).toDouble()
                        val (l, t, r, b) = startBox!!
                        onCrop(when (corner) {
                            0 -> keepRatio(listOf((l + dx).coerceIn(0.0, r - 0.05), (t + dy).coerceIn(0.0, b - 0.05), r, b), ratio, rect, 0)
                            1 -> keepRatio(listOf(l, (t + dy).coerceIn(0.0, b - 0.05), (r + dx).coerceIn(l + 0.05, 1.0), b), ratio, rect, 1)
                            2 -> keepRatio(listOf((l + dx).coerceIn(0.0, r - 0.05), t, r, (b + dy).coerceIn(t + 0.05, 1.0)), ratio, rect, 2)
                            3 -> keepRatio(listOf(l, t, (r + dx).coerceIn(l + 0.05, 1.0), (b + dy).coerceIn(t + 0.05, 1.0)), ratio, rect, 3)
                            else -> {
                                val mx = dx.coerceIn(-l, 1 - r); val my = dy.coerceIn(-t, 1 - b)
                                listOf(l + mx, t + my, r + mx, b + my)
                            }
                        })
                    }
                    onLine -> onSplit(((pos.x - rect.left) / rect.width).coerceIn(0f, 1f))
                    moved && scale > 1f -> offset += pos - pressed[0].previousPosition
                    !moved && !held && System.currentTimeMillis() - startTime > 250 -> { held = true; onHold(true) }
                }
                pressed[0].consume()
            }
            if (held) onHold(false)
        }
    }) {
        area = size
        val rect = fitted()
        fun draw(image: ImageBitmap) = drawImage(image, IntOffset.Zero, IntSize(image.width, image.height),
            IntOffset(rect.left.roundToInt(), rect.top.roundToInt()), IntSize(rect.width.roundToInt(), rect.height.roundToInt()))
        if (holding) { draw(before); return@Canvas }
        draw(after)
        val x = rect.left + rect.width * split
        if (split > 0f) clipRect(rect.left, rect.top, x, rect.bottom) { draw(before) }
        if (!cropping && split < 1f) {
            val lx = max(x, rect.left + 1)
            drawLine(Color.White, Offset(lx, rect.top), Offset(lx, rect.bottom), 2.dp.toPx())
            drawCircle(Color.White, 13.dp.toPx(), Offset(lx.coerceIn(rect.left + 14.dp.toPx(), rect.right - 14.dp.toPx()), rect.center.y))
        }
        if (crop != null) {
            val box = Rect(rect.left + crop[0].toFloat() * rect.width, rect.top + crop[1].toFloat() * rect.height,
                rect.left + crop[2].toFloat() * rect.width, rect.top + crop[3].toFloat() * rect.height)
            val shade = Color(0x96000000)
            drawRect(shade, Offset(rect.left, rect.top), Size(rect.width, box.top - rect.top))
            drawRect(shade, Offset(rect.left, box.bottom), Size(rect.width, rect.bottom - box.bottom))
            drawRect(shade, Offset(rect.left, box.top), Size(box.left - rect.left, box.height))
            drawRect(shade, Offset(box.right, box.top), Size(rect.right - box.right, box.height))
            drawRect(Color.White, box.topLeft, box.size, style = Stroke(2.dp.toPx()))
            if (cropping) for (c in listOf(box.topLeft, box.topRight, box.bottomLeft, box.bottomRight)) drawCircle(Color.White, 8.dp.toPx(), c)
        }
    }
}

/** Keep a fixed crop shape while a corner is dragged (the opposite corner stays put). */
private fun keepRatio(box: List<Double>, ratio: Float?, rect: Rect, corner: Int): List<Double> {
    if (ratio == null || rect.width == 0f) return box
    var (l, t, r, b) = box
    val w = (r - l) * rect.width
    val hFrac = (w / ratio) / rect.height
    if (corner < 2) t = b - hFrac else b = t + hFrac
    if (t < 0 || b > 1) return box
    return listOf(l, t, r, b)
}
