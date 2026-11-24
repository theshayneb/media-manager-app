package mm.companion

import android.graphics.Bitmap
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.border
import androidx.compose.ui.draw.shadow
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
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
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
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
import mm.core.Turn
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
    Row5("contrast", "Contrast", "Less", "More", listOf(Color(0xFF555555), Color(0xFF999999))),
    Row5("brightness", "Brightness", "Darker", "Brighter", listOf(Color(0xFF222222), Color(0xFFDDDDDD))),  // under Contrast
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
    var failed by remember { mutableStateOf("") }
    var pixels by remember { mutableStateOf<Pixels?>(null) }
    var after by remember { mutableStateOf<ImageBitmap?>(null) }
    val values = remember { mutableStateMapOf<String, Int>() }
    val on = remember { mutableStateMapOf<String, Boolean>() }
    var tab by model::editTab  // (kept when swiping to the next photo)
    var split by remember { mutableFloatStateOf(0f) }
    var holding by remember { mutableStateOf(false) }
    var picking by remember { mutableStateOf(false) }
    var cropping by remember { mutableStateOf(false) }
    var crop by remember { mutableStateOf<List<Double>?>(null) }
    var ratio by remember { mutableStateOf<Float?>(null) }
    var asking by remember { mutableStateOf(false) }
    var suggestions by remember { mutableStateOf<Map<String, Int>?>(null) }
    var turn by remember { mutableStateOf(Turn()) }
    var flipMenu by remember { mutableStateOf(false) }
    var turnedBefore by remember { mutableStateOf<ImageBitmap?>(null) }  // the original, turned as the edit is
    var full by model::editFull  // the photo full screen, no sliders (kept when swiping to the next photo)
    var pending by remember { mutableStateOf<Photo?>(null) }  // the photo to go to once asked about saving

    fun adjustments() = Adjustments.fromMap(values.filter { on[it.key] != false })
    fun changed() = !adjustments().unchanged || crop != null || !turn.unchanged
    fun setTurn(t: Turn) { turn = t; crop = null; cropping = false }  // a crop box drawn before no longer fits

    LaunchedEffect(photo.id) {
        // (a OneDrive photo is downloaded first; with no connection, one that hasn't been can't be opened)
        val bytes = runCatching { model.readForEdit(photo) }.onFailure { failed = it.message ?: "Couldn't open it" }.getOrNull()
        val bmp = bytes?.let { withContext(Dispatchers.IO) { runCatching { decodePreview(it, 2048) }.getOrNull() } }
        preview = bmp
        pixels = bmp?.toPixels()
        after = bmp?.asImageBitmap()
    }
    LaunchedEffect(Unit) {
        snapshotFlow { Triple(adjustments(), pixels, turn) }.collectLatest { (a, p, t) ->
            if (p == null) return@collectLatest
            val (out, orig) = withContext(Dispatchers.Default) {
                t.apply(applyEdit(p, a)).toBitmap() to (if (t.unchanged) null else t.apply(p).toBitmap())
            }
            after = out.asImageBitmap()
            turnedBefore = orig?.asImageBitmap() ?: preview?.asImageBitmap()
        }
    }

    fun leave() {
        model.screen = Screen.Grid; model.editing = null; model.selected.clear()
        model.editFull = false  // next time Edit opens, with its sliders
    }
    // The Tags tab works on this photo: it's the selection while the tab is open.
    LaunchedEffect(tab, photo.id) {
        if (tab == 3) {
            model.selected.clear()
            model.selected[photo.id] = true
            model.loadFields(photo)
        }
    }
    fun moveOn() { pending?.let { model.editing = it } ?: leave(); pending = null }  // next photo, or the grid
    /** Swipe: the next (1) or previous (-1) photo in the folder, asking first if this one was changed. */
    fun go(delta: Int) {
        val target = model.neighbour(photo, delta) ?: run {
            model.message = if (delta > 0) "That's the last photo" else "That's the first photo"; return
        }
        if (changed()) { pending = target; asking = true } else model.editing = target
    }
    BackHandler { if (full) full = false else if (cropping) cropping = false else if (changed()) asking = true else leave() }
    if (asking) AlertDialog(onDismissRequest = { asking = false; pending = null }, title = { Text("Save the edit?") },
        confirmButton = { TextButton(onClick = { asking = false; model.saveEdit(photo, adjustments(), crop, turn) { moveOn() } }) { Text("Save") } },
        dismissButton = {
            Row {
                TextButton(onClick = { asking = false; moveOn() }) { Text("Don't save") }
                TextButton(onClick = { asking = false; pending = null }) { Text("Keep editing") }
            }
        })

    Column(Modifier.fillMaxSize()) {
        // Back | crop, rotate, flip, full screen, delete | Save  (line icons; long-press one for its name)
        Row(Modifier.fillMaxWidth().background(Background).padding(horizontal = 4.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Tool(Line.Back, "Back") { if (changed()) asking = true else leave() }
            Spacer(Modifier.weight(1f))
            if (cropping) {
                TextButton(onClick = { cropping = false }) { Text("Done", color = Color.White, fontWeight = FontWeight.SemiBold) }
            } else {
                Tool(Line.Crop, "Crop") { cropping = true; if (crop == null) crop = listOf(0.05, 0.05, 0.95, 0.95) }
                Tool(Line.Rotate, "Rotate") { setTurn(turn.rotated()) }
                Box {
                    Tool(Line.Flip, "Flip") { flipMenu = true }
                    DropdownMenu(flipMenu, { flipMenu = false }) {
                        DropdownMenuItem(text = { Text("Flip horizontal") }, onClick = { flipMenu = false; setTurn(turn.flipped()) })
                        DropdownMenuItem(text = { Text("Flip vertical") }, onClick = { flipMenu = false; setTurn(turn.flipped(vertical = true)) })
                    }
                }
                Tool(if (full) Line.ExitFullScreen else Line.FullScreen, if (full) "Show the sliders" else "Full screen") { full = !full }
                if (photo.inCloud) Tool(Line.Folder, "Move") {  // to another Pictures folder; then the next photo
                    val next = model.neighbour(photo, 1) ?: model.neighbour(photo, -1)
                    model.moving = MoveRequest(listOf(photo)) { if (next != null) model.editing = next else leave() }
                }
                // Delete: then the next photo (or the one before), else the grid.
                Tool(Line.Delete, "Delete") {
                    val next = model.neighbour(photo, 1) ?: model.neighbour(photo, -1)
                    model.delete(listOf(photo)) { if (next != null) model.editing = next else leave() }
                }
            }
            Spacer(Modifier.weight(1f))
            val canSave = changed() && !model.busy
            Text(if (model.busy) "Saving…" else "Save", fontSize = 14.sp, fontWeight = FontWeight.Bold,
                color = if (canSave) Color.White else Color(0xFF7D8188),
                modifier = Modifier.padding(end = 4.dp).clip(RoundedCornerShape(18.dp))
                    .background(if (canSave) Accent else ChipColour)
                    .clickable(enabled = canSave) { model.saveEdit(photo, adjustments(), crop, turn) { leave() } }
                    .padding(horizontal = 18.dp, vertical = 8.dp))
        }
        if (!full) Note(model)
        val img = after
        val before = turnedBefore ?: preview?.asImageBitmap()
        Box(Modifier.fillMaxWidth().weight(1f).background(Color(0xFF1B1C1F))) {
            if (img != null && before != null) PhotoView(img, before, split, holding, picking, cropping, crop, ratio,
                onSplit = { split = it }, onHold = { holding = it }, onCrop = { crop = it },
                onPick = { fx, fy ->
                    val p = pixels?.let { turn.apply(it) } ?: return@PhotoView  // tapped on the photo as it's shown
                    val (y, r) = whiteBalanceAt(p, (fx * p.width).toInt(), (fy * p.height).toInt(), max(2, p.width / 300))
                    values["yellow"] = y; values["red"] = r; on["yellow"] = true; on["red"] = true
                    picking = false
                }, onSwipe = { go(it) })
            else if (failed.isNotEmpty()) Text(failed, color = Dim, modifier = Modifier.align(Alignment.Center).padding(24.dp))
            else CircularProgressIndicator(Modifier.align(Alignment.Center))
        }
        if (full) return@Column  // full screen: the photo only (⊟ or Back brings the sliders back)
        if (cropping) {
            Row(Modifier.fillMaxWidth().background(Panel).padding(6.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                for ((name, r) in RATIOS) {
                    val chosen = ratio == r || (name == "Free" && ratio == null)
                    Text(name, fontSize = 12.sp, modifier = Modifier.clip(RoundedCornerShape(14.dp))
                        .background(if (chosen) Accent else Color(0xFF33363C)).clickable {
                            val pv = after  // the photo as it's shown (turned)
                            ratio = if (r == -1f && pv != null) pv.width.toFloat() / pv.height else r
                            crop = fitRatio(crop ?: listOf(0.05, 0.05, 0.95, 0.95), ratio, pv)
                        }.padding(horizontal = 10.dp, vertical = 6.dp))
                }
            }
            TextButton(onClick = { crop = null; cropping = false }) { Text("No crop", color = Dim) }
            return@Column
        }
        Column(Modifier.fillMaxWidth().weight(1f).background(Panel).padding(horizontal = 12.dp)) {
            // the tabs: text, the chosen one underlined
            Row(Modifier.fillMaxWidth()) {
                for ((i, t) in listOf("Light", "Detail", "Colour", "Tags").withIndex()) {
                    Column(Modifier.weight(1f).clickable { tab = i }, horizontalAlignment = Alignment.CenterHorizontally) {
                        Text(t, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = if (tab == i) Color.White else Color(0xFF8F939A),
                            modifier = Modifier.padding(top = 11.dp, bottom = 8.dp))
                        Box(Modifier.fillMaxWidth().height(2.5.dp).background(if (tab == i) Accent else Color.Transparent))
                    }
                }
            }
            Box(Modifier.fillMaxWidth().height(1.dp).background(LineColour))
            if (tab == 3) {  // Tags: label, keywords, date taken, rename (for this photo, done at once)
                Box(Modifier.weight(1f)) { DetailsPanel(model, showNote = false) }
                return@Column
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
private fun fitRatio(box: List<Double>, ratio: Float?, photo: ImageBitmap?): List<Double> {
    if (ratio == null || photo == null) return box
    val (l, t, r, b) = box
    var w = (r - l) * photo.width; var h = (b - t) * photo.height
    if (w / h > ratio) w = h * ratio else h = w / ratio
    val cx = (l + r) / 2 * photo.width; val cy = (t + b) / 2 * photo.height
    val fw = w / photo.width; val fh = h / photo.height
    val nl = (cx / photo.width - fw / 2).coerceIn(0.0, 1 - fw); val nt = (cy / photo.height - fh / 2).coerceIn(0.0, 1 - fh)
    return listOf(nl, nt, nl + fw, nt + fh)
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
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
                    inactiveTrackColor = Color.Transparent, thumbColor = Color(0xFFE6E6E6)),
                // the handle: a round dot (touching anywhere on the line still moves it there)
                thumb = {
                    Box(Modifier.size(22.dp).shadow(2.dp, CircleShape).clip(CircleShape)
                        .background(if (enabled) Color(0xFFF1F1F1) else Color(0xFF6A6E75))
                        .border(1.5.dp, Color(0x40000000), CircleShape))
                })
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
                      onPick: (Float, Float) -> Unit, onSwipe: (Int) -> Unit = {}) {
    var scale by remember { mutableFloatStateOf(1f) }
    val swipe by rememberUpdatedState(onSwipe)
    var offset by remember { mutableStateOf(Offset.Zero) }
    var area by remember { mutableStateOf(Size.Zero) }
    var lastTap by remember { mutableStateOf(0L) }  // (a second tap soon after: double tap)

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
            var pinched = false
            var last = startPos
            val startOffset = offset
            while (true) {
                // A finger kept still sends no events: after ¼ s with none, it's a hold (the original is shown).
                val wait = 250 - (System.currentTimeMillis() - startTime)
                val canHold = !cropping && !onLine && !moved && !held && !pinched
                val event = if (canHold && wait > 0) withTimeoutOrNull(wait) { awaitPointerEvent() } else awaitPointerEvent()
                if (event == null) { held = true; onHold(true); continue }
                val pressed = event.changes.filter { it.pressed }
                if (pressed.isEmpty()) break
                if (event.changes.size >= 2) {  // pinch
                    scale = (scale * event.calculateZoom()).coerceIn(0.25f, 6f)
                    offset += event.calculatePan()
                    moved = true
                    pinched = true
                    event.changes.forEach { it.consume() }
                    continue
                }
                val pos = pressed[0].position
                last = pos
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
                    !cropping && !moved && !held && System.currentTimeMillis() - startTime > 250 -> { held = true; onHold(true) }
                }
                pressed[0].consume()
            }
            if (held) onHold(false)
            // A double tap: the whole photo again (zoom back to fit).
            val now = System.currentTimeMillis()
            if (!moved && !held && !pinched && !cropping && !onLine && now - startTime < 250) {
                if (now - lastTap < 350) { scale = 1f; offset = Offset.Zero; lastTap = 0L } else lastTap = now
            }
            // A quick sideways swipe (not zoomed in, not on the line, not cropping): the next or previous photo.
            val dx = last.x - startPos.x
            val dy = last.y - startPos.y
            // Zoomed in, a slow drag looks round the photo; a quick flick (under ⅓ s) still changes photos.
            val quick = System.currentTimeMillis() - startTime < 330
            if (!cropping && !onLine && !pinched && !held && (scale <= 1.01f || quick) &&
                abs(dx) > 70.dp.toPx() && abs(dx) > 1.5f * abs(dy)) {
                offset = startOffset  // (the flick doesn't move the view)
                swipe(if (dx < 0) 1 else -1)
            }
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

/** A toolbar icon; long-press shows its name. */
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun Tool(icon: androidx.compose.ui.graphics.vector.ImageVector, name: String, onClick: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    Box(Modifier.size(42.dp).clip(CircleShape)
        .combinedClickable(onClick = onClick,
            onLongClick = { android.widget.Toast.makeText(context, name, android.widget.Toast.LENGTH_SHORT).show() }),
        contentAlignment = Alignment.Center) { LineIcon(icon, name) }
}
