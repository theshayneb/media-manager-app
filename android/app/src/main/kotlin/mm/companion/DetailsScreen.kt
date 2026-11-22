package mm.companion

import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.graphics.Bitmap
import androidx.compose.foundation.layout.ExperimentalLayoutApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.FlowRow
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import mm.core.Change
import mm.core.LABELS
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter


@Composable
fun DetailsScreen(model: AppModel) {
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(Panel).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { model.screen = Screen.Grid }) {
                Text("←  ${model.selected.size} selected", color = Color.White, fontSize = 17.sp)
            }
        }
        LazyRow(Modifier.fillMaxWidth().padding(3.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
            items(model.selection, key = { it.id }) { p ->
                val bitmap by produceState<Bitmap?>(null, p.id) { value = model.thumbnail(p) }
                bitmap?.let { Image(it.asImageBitmap(), null, Modifier.size(110.dp, 82.dp), contentScale = ContentScale.Crop) }
            }
        }
        DetailsPanel(model)
    }
}

private val SHOWN_DAY = DateTimeFormatter.ofPattern("EEE, MMM d, yyyy, h:mm a")

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DetailsPanel(model: AppModel, showNote: Boolean = true) {
    val sel = model.selection
    // Every selected photo's tags are needed to show which keywords all / some / none of them have.
    LaunchedEffect(sel.map { it.id }) { sel.forEach { model.loadFields(it) } }
    val fields = sel.map { model.fields[it.id] }
    val reading = fields.any { it == null }
    Column(Modifier.fillMaxSize().background(Panel).verticalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 8.dp)) {
        if (showNote) Note(model)
        if (reading && sel.isNotEmpty()) Text("Reading the photos' tags…", color = Dim, fontSize = 12.sp)
        // ---------------------------------------------------------------- label, star, bookmark
        Section("Label")
        Row(verticalAlignment = Alignment.CenterVertically) {
            for (label in LABELS) {
                val n = fields.count { it?.label == label }
                val all = sel.isNotEmpty() && n == sel.size
                Box(Modifier.padding(end = 9.dp).size(34.dp)
                    .then(if (n > 0) Modifier.border(2.dp, if (all) Color.White else Dim, CircleShape) else Modifier)
                    .padding(3.dp).clip(CircleShape).background(LabelColours[label]!!)
                    .clickable { model.apply(Change.Label(if (all) "" else label)) },  // the chosen one again: no label
                    contentAlignment = Alignment.Center) {
                    if (all) LineIcon(Line.Check, "Chosen", Color.White, Modifier.size(16.dp))
                }
            }
            Spacer(Modifier.weight(1f))
            val starred = fields.isNotEmpty() && fields.all { it?.starred == true }
            val marked = fields.isNotEmpty() && fields.all { it?.bookmarked == true }
            Flag("⭐", starred) { model.apply(Change.Flag("Star", !starred)) }
            Flag("🔖", marked) { model.apply(Change.Flag("Bookmark", !marked)) }
        }
        // ---------------------------------------------------------------- keywords
        val sets = model.shared.keywordSets
        var setName by remember { mutableStateOf(model.shared.currentSet.ifEmpty { sets.keys.firstOrNull() ?: "" }) }
        var pickSet by remember { mutableStateOf(false) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Section("Keywords")
            if (sets.size > 1) Box {
                Text("$setName ▾", color = Dim, fontSize = 13.sp, modifier = Modifier.padding(start = 8.dp, top = 6.dp)
                    .clip(RoundedCornerShape(8.dp)).clickable { pickSet = true }.padding(horizontal = 6.dp, vertical = 2.dp))
                DropdownMenu(pickSet, { pickSet = false }) {
                    for (name in sets.keys) DropdownMenuItem(text = { Text(name) }, onClick = { setName = name; pickSet = false })
                }
            }
        }
        val have = fields.map { f -> f?.keywords?.map { it.lowercase() }?.toSet() ?: emptySet() }
        fun countOf(kw: String) = have.count { kw.lowercase() in it }
        // The photos' own keywords first (on all of them, then on some), then the rest of the set.
        val allKeywords = ((sets[setName] ?: emptyList()) + fields.flatMap { it?.keywords ?: emptyList() }).distinctBy { it.lowercase() }
        val ordered = allKeywords.withIndex().sortedWith(compareBy({ -(if (countOf(it.value) == sel.size) 2 else if (countOf(it.value) > 0) 1 else 0) }, { it.index })).map { it.value }
        var adding by remember { mutableStateOf(false) }
        FlowRow(horizontalArrangement = Arrangement.spacedBy(6.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
            for (kw in ordered) Chip(kw, countOf(kw), sel.size) {
                // On all of them: off all of them. On some or none: onto all of them.
                model.apply(if (countOf(kw) == sel.size) Change.Keywords(remove = listOf(kw)) else Change.Keywords(add = listOf(kw)))
            }
            if (!adding) Text("+ Add", fontSize = 13.sp, color = Dim, modifier = Modifier.clip(RoundedCornerShape(16.dp))
                .border(1.dp, Color(0xFF5A5F67), RoundedCornerShape(16.dp)).clickable { adding = true }
                .padding(horizontal = 11.dp, vertical = 5.dp))
        }
        if (adding) {
            var typed by remember { mutableStateOf("") }
            val focus = remember { FocusRequester() }
            LaunchedEffect(Unit) { focus.requestFocus() }
            OutlinedTextField(typed, { typed = it }, Modifier.fillMaxWidth().padding(top = 8.dp).focusRequester(focus),
                placeholder = { Text("New keyword (commas for more than one)") },
                singleLine = true, keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                keyboardActions = KeyboardActions(onDone = {
                    val words = typed.split(',').map { it.trim() }.filter { it.isNotEmpty() }
                    if (words.isNotEmpty()) model.apply(Change.Keywords(add = words))
                    typed = ""; adding = false
                }))
        }
        if (sets.isEmpty()) {
            Text("Your keyword sets come from the PC: open Media Manager there once while signed in to OneDrive, " +
                "then sign in here (Settings).", color = Dim, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
        }
        // ---------------------------------------------------------------- date taken
        Section("Date taken")
        val dates = remember(sel, model.message, model.changes) { sel.map { model.dateTaken(it) } }
        val known = dates.filterNotNull()
        val context = LocalContext.current
        var dateMenu by remember { mutableStateOf(false) }
        ValueRow(when {
            sel.isEmpty() -> ""
            known.isEmpty() -> "No date taken"
            known.distinct().size == 1 -> known[0].format(SHOWN_DAY) + if (known.size < sel.size) " (${sel.size - known.size} have none)" else ""
            else -> "Different dates"
        }) {
            Box {
                LineAction("Change") { dateMenu = true }
                DropdownMenu(dateMenu, { dateMenu = false }) {
                    DropdownMenuItem(text = { Text("Set date…") }, onClick = {
                        dateMenu = false
                        val start = known.firstOrNull() ?: LocalDateTime.now()
                        DatePickerDialog(context, { _, y, m, d ->
                            TimePickerDialog(context, { _, h, min ->
                                model.apply(Change.DateTaken(LocalDateTime.of(y, m + 1, d, h, min, 0).format(EXIF_DATE)))
                            }, start.hour, start.minute, false).show()
                        }, start.year, start.monthValue - 1, start.dayOfMonth).show()
                    })
                    DropdownMenuItem(text = { Text("From file name") }, onClick = { dateMenu = false; model.datesFromNames() })
                }
            }
        }
        // ---------------------------------------------------------------- name
        Section("Name")
        val plan = remember(sel, model.message, model.changes) { model.renamePreview() }
        val changing = plan.filter { it.second != null }
        ValueRow(if (sel.size == 1) sel[0].name else "${sel.size} photos") {
            LineAction(if (sel.size == 1) "Rename" else "Rename ${changing.size}", enabled = changing.isNotEmpty() && !model.busy) { model.rename() }
        }
        val hint = Modifier.padding(top = 6.dp)
        when {
            sel.size == 1 && changing.size == 1 -> Text(buildAnnotatedString {
                append("Rename makes it "); withStyle(SpanStyle(color = Color.White, fontWeight = FontWeight.SemiBold)) { append(changing[0].second!!) }
            }, fontSize = 12.5.sp, color = Dim, modifier = hint)
            changing.isNotEmpty() -> {
                for ((p, name) in changing.take(3)) Text("${p.name} → $name", fontSize = 12.5.sp, color = Dim, modifier = hint)
                if (changing.size > 3) Text("and ${changing.size - 3} more", fontSize = 12.5.sp, color = Dim)
            }
            sel.isNotEmpty() && known.size < sel.size -> Text("Photos without a date taken keep their names.", fontSize = 12.5.sp, color = Dim, modifier = hint)
            sel.isNotEmpty() -> Text("Already named by the pattern (${model.shared.renamePattern}).", fontSize = 12.5.sp, color = Dim, modifier = hint)
        }
        Spacer(Modifier.height(40.dp))
    }
}

/** What it is now on the left, its action on the right. */
@Composable
private fun ValueRow(text: String, action: @Composable () -> Unit) {
    Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Background).padding(start = 12.dp, end = 4.dp, top = 4.dp, bottom = 4.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Text(text, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, color = Color.White, maxLines = 1,
            overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
        action()
    }
}

@Composable
private fun LineAction(text: String, enabled: Boolean = true, onClick: () -> Unit) =
    TextButton(onClick = onClick, enabled = enabled) { Text(text, fontWeight = FontWeight.SemiBold, color = if (enabled) Color(0xFF9CC0FF) else Dim) }

@Composable
private fun Flag(text: String, on: Boolean, onClick: () -> Unit) {
    Box(Modifier.padding(start = 6.dp).size(width = 40.dp, height = 34.dp).clip(RoundedCornerShape(10.dp))
        .background(if (on) Color(0xFF3E434B) else ChipColour)
        .then(if (on) Modifier.border(1.5.dp, Color(0xFFE8C020), RoundedCornerShape(10.dp)) else Modifier)
        .clickable(onClick = onClick), contentAlignment = Alignment.Center) { Text(text, fontSize = 15.sp) }
}

@Composable
private fun Section(title: String) =
    Text(title, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFFC9CCD1), modifier = Modifier.padding(top = 16.dp, bottom = 8.dp))


/** A keyword: filled when every selected photo has it, outlined when only some do. */
@Composable
private fun Chip(text: String, count: Int, of: Int, onClick: () -> Unit) {
    val all = of > 0 && count == of
    val some = count in 1 until of
    Text(text, fontSize = 13.sp, color = Color.White, modifier = Modifier
        .clip(RoundedCornerShape(16.dp))
        .background(if (all) Accent else Color.Transparent)
        .border(if (some) 2.dp else 1.dp, if (all || some) Accent else Color(0xFF4A4E55), RoundedCornerShape(16.dp))
        .clickable(onClick = onClick).padding(horizontal = 11.dp, vertical = 5.dp))
}
