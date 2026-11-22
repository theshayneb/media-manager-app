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

private val SHOWN = DateTimeFormatter.ofPattern("MMM d, yyyy h:mm a")

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

@OptIn(ExperimentalLayoutApi::class)
@Composable
fun DetailsPanel(model: AppModel, showNote: Boolean = true) {
    val sel = model.selection
    val fields = sel.map { model.fields[it.id] }
    Column(Modifier.fillMaxSize().background(Panel).verticalScroll(rememberScrollState()).padding(12.dp)) {
        if (showNote) Note(model)
        // ---------------------------------------------------------------- labels
        Section("Labels")
        Row(verticalAlignment = Alignment.CenterVertically) {
            for (label in LABELS) {
                val all = fields.isNotEmpty() && fields.all { it?.label == label }
                Box(Modifier.padding(end = 6.dp).size(30.dp).clip(RoundedCornerShape(6.dp))
                    .background(LabelColours[label]!!)
                    .then(if (all) Modifier.border(2.dp, Color.White, RoundedCornerShape(6.dp)) else Modifier)
                    .clickable { model.apply(Change.Label(if (all) "" else label)) })
            }
            val starred = fields.isNotEmpty() && fields.all { it?.starred == true }
            val marked = fields.isNotEmpty() && fields.all { it?.bookmarked == true }
            Pill("⭐", starred) { model.apply(Change.Flag("Star", !starred)) }
            Pill("🔖", marked) { model.apply(Change.Flag("Bookmark", !marked)) }
            Pill("⊘", false) { model.apply(Change.ClearLabels) }
        }
        // ---------------------------------------------------------------- keywords
        val sets = model.shared.keywordSets
        var setName by remember { mutableStateOf(model.shared.currentSet.ifEmpty { sets.keys.firstOrNull() ?: "" }) }
        var pickSet by remember { mutableStateOf(false) }
        Row(verticalAlignment = Alignment.CenterVertically) {
            Section("Keywords")
            if (sets.isNotEmpty()) Box {
                TextButton(onClick = { pickSet = true }) { Text("· set: $setName ▾", color = Dim, fontSize = 13.sp) }
                DropdownMenu(pickSet, { pickSet = false }) {
                    for (name in sets.keys) DropdownMenuItem(text = { Text(name) }, onClick = { setName = name; pickSet = false })
                }
            }
        }
        var typed by remember { mutableStateOf("") }
        OutlinedTextField(typed, { typed = it }, Modifier.fillMaxWidth(), placeholder = { Text("Add a keyword…") },
            singleLine = true, keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = {
                val words = typed.split(',').map { it.trim() }.filter { it.isNotEmpty() }
                if (words.isNotEmpty()) model.apply(Change.Keywords(add = words))
                typed = ""
            }))
        val have = fields.map { f -> f?.keywords?.map { it.lowercase() }?.toSet() ?: emptySet() }
        fun countOf(kw: String) = have.count { kw.lowercase() in it }
        if (sets.isEmpty()) {
            Text("Your keyword sets come from the PC: open Media Manager there once while signed in to OneDrive, " +
                "then sign in here (⚙).", color = Dim, fontSize = 12.sp)
        }
        FlowRow(Modifier.padding(top = 6.dp)) {
            for (kw in sets[setName] ?: emptyList()) Chip(kw, countOf(kw), sel.size) {
                model.apply(if (countOf(kw) == sel.size) Change.Keywords(remove = listOf(kw)) else Change.Keywords(add = listOf(kw)))
            }
        }
        val inSet = (sets[setName] ?: emptyList()).map { it.lowercase() }.toSet()
        val others = fields.flatMap { it?.keywords ?: emptyList() }.distinctBy { it.lowercase() }.filter { it.lowercase() !in inSet }
        if (others.isNotEmpty()) {
            Text("Also on these photos (tap to remove):", color = Dim, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
            FlowRow { for (kw in others) Chip(kw, countOf(kw), sel.size) { model.apply(Change.Keywords(remove = listOf(kw))) } }
        }
        // ---------------------------------------------------------------- date taken
        Section("Date taken")
        val dates = remember(sel, model.message) { sel.map { model.dateTaken(it) } }
        val known = dates.filterNotNull()
        Text(when {
            sel.isEmpty() -> ""
            known.isEmpty() -> "No date taken"
            known.distinct().size == 1 -> known[0].format(SHOWN) + if (known.size < sel.size) "  (${sel.size - known.size} of ${sel.size} have none)" else ""
            else -> "Different dates"
        }, fontSize = 14.sp)
        val context = LocalContext.current
        Row(Modifier.padding(top = 6.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedButton(onClick = { model.datesFromNames() }) { Text("From file name") }
            OutlinedButton(onClick = {
                val start = known.firstOrNull() ?: LocalDateTime.now()
                DatePickerDialog(context, { _, y, m, d ->
                    TimePickerDialog(context, { _, h, min ->
                        model.apply(Change.DateTaken(LocalDateTime.of(y, m + 1, d, h, min, 0).format(EXIF_DATE)))
                    }, start.hour, start.minute, false).show()
                }, start.year, start.monthValue - 1, start.dayOfMonth).show()
            }) { Text("Set date…") }
        }
        // ---------------------------------------------------------------- rename
        Section("Rename")
        Text(model.shared.renamePattern, color = Dim, fontSize = 12.sp)
        val plan = remember(sel, model.message) { model.renamePreview() }
        val changing = plan.filter { it.second != null }
        for ((p, name) in changing.take(3)) Text("${p.name} → $name", fontSize = 12.sp)
        if (changing.size > 3) Text("… and ${changing.size - 3} more", fontSize = 12.sp, color = Dim)
        if (plan.any { it.second == null && model.dateTaken(it.first) == null }) {
            Text("Photos without a date taken are left as they are.", fontSize = 12.sp, color = Dim)
        }
        Button(onClick = { model.rename() }, enabled = changing.isNotEmpty() && !model.busy,
            modifier = Modifier.padding(top = 6.dp)) {
            Text(if (changing.isEmpty()) "Already named that way" else "Rename ${changing.size} photo${if (changing.size == 1) "" else "s"}")
        }
        Spacer(Modifier.height(40.dp))
    }
}

@Composable
private fun Section(title: String) =
    Text(title, fontWeight = FontWeight.Bold, fontSize = 15.sp, modifier = Modifier.padding(top = 14.dp, bottom = 6.dp))

@Composable
private fun Pill(text: String, on: Boolean, onClick: () -> Unit) {
    Text(text, fontSize = 16.sp, modifier = Modifier.padding(end = 6.dp).clip(RoundedCornerShape(6.dp))
        .background(if (on) Accent else Color(0xFF33363C)).clickable(onClick = onClick).padding(horizontal = 10.dp, vertical = 4.dp))
}

@Composable
private fun Chip(text: String, count: Int, of: Int, onClick: () -> Unit) {
    val all = of > 0 && count == of
    val some = count in 1 until of
    Text(text, fontSize = 13.sp, color = Color.White, modifier = Modifier.padding(end = 4.dp, bottom = 4.dp)
        .clip(RoundedCornerShape(14.dp))
        .background(if (all) Accent else Color.Transparent)
        .border(if (some) 2.dp else 1.dp, if (some) Accent else Color(0xFF4A4E55), RoundedCornerShape(14.dp))
        .clickable(onClick = onClick).padding(horizontal = 10.dp, vertical = 5.dp))
}
