package mm.companion

import android.graphics.Bitmap
import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.GridItemSpan
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import java.time.DayOfWeek
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.TemporalAdjusters

private val WEEK = DateTimeFormatter.ofPattern("MMM d, yyyy")

@OptIn(ExperimentalFoundationApi::class)
@Composable
fun GridScreen(model: AppModel) {
    val wide = LocalConfiguration.current.screenWidthDp >= 840  // a tablet held sideways
    Row(Modifier.fillMaxSize()) {
        if (wide && model.selected.isNotEmpty()) {
            Box(Modifier.size(width = 340.dp, height = LocalConfiguration.current.screenHeightDp.dp)) { DetailsPanel(model) }
        }
        Column(Modifier.weight(1f)) {
            TopBar(model)
            Note(model)
            val groups = remember(model.photos) {
                model.photos.groupBy {
                    Instant.ofEpochMilli(if (it.takenMillis > 0) it.takenMillis else it.modified * 1000)
                        .atZone(ZoneId.systemDefault()).toLocalDate()
                        .with(TemporalAdjusters.previousOrSame(DayOfWeek.SUNDAY))
                }
            }
            LazyVerticalGrid(GridCells.Adaptive(110.dp), Modifier.weight(1f).padding(2.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                for ((week, group) in groups) {
                    item(span = { GridItemSpan(maxLineSpan) }) {
                        Text("Week of ${week.format(WEEK)} · ${group.size}", color = Dim, fontSize = 13.sp,
                            modifier = Modifier.padding(6.dp, 10.dp, 6.dp, 4.dp))
                    }
                    items(group, key = { it.id }) { p -> Tile(model, p) }
                }
            }
            if (model.selected.isNotEmpty() && !wide) BottomBar(model)
        }
    }
}

@Composable
private fun TopBar(model: AppModel) {
    var open by remember { mutableStateOf(false) }
    Row(Modifier.fillMaxWidth().background(Panel).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
        if (model.selected.isNotEmpty()) {
            TextButton(onClick = { model.selected.clear() }) { Text("✕  ${model.selected.size} selected", color = Color.White) }
        } else {
            Box {
                TextButton(onClick = { open = true }) { Text("📂 ${model.folder?.name ?: "No photos"} ▾", color = Color.White, fontSize = 17.sp) }
                DropdownMenu(open, { open = false }) {
                    val favs = model.folders.count { model.isFavorite(it) }
                    if (favs > 0) Text("★ FAVOURITES", color = Dim, fontSize = 12.sp,
                        modifier = Modifier.padding(start = 12.dp, top = 6.dp, bottom = 2.dp))
                    model.folders.forEachIndexed { i, f ->
                        if (favs > 0 && i == favs) HorizontalDivider(Modifier.padding(vertical = 4.dp))
                        val fav = model.isFavorite(f)
                        DropdownMenuItem(
                            text = { Text("${f.name}  (${"%,d".format(f.count)})") },
                            onClick = { open = false; model.open(f) },
                            trailingIcon = {
                                Text(if (fav) "★" else "☆", fontSize = 22.sp, color = if (fav) Color(0xFFE8C020) else Dim,
                                    modifier = Modifier.clip(CircleShape).clickable { model.toggleFavorite(f) }
                                        .padding(horizontal = 10.dp, vertical = 4.dp))
                            },
                        )
                    }
                }
            }
        }
        Spacer(Modifier.weight(1f))
        if (model.pending > 0) Text("⟳ ${model.pending} to sync", color = Dim, fontSize = 12.sp)
        TextButton(onClick = { model.screen = Screen.Settings }) { Text("⚙", color = Color.White, fontSize = 18.sp) }
    }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun Tile(model: AppModel, p: Photo) {
    val bitmap by produceState<Bitmap?>(null, p.id, p.modified) { value = model.thumbnail(p) }
    val f = model.fields[p.id]
    val sel = model.selected[p.id] == true
    Box(Modifier.aspectRatio(1f).background(Color(0xFF333333))
        .combinedClickable(
            onClick = {
                if (model.selected.isNotEmpty()) { if (sel) model.selected.remove(p.id) else model.selected[p.id] = true }
                else if (p.canChange) { model.editing = p; model.screen = Screen.Edit }
                else model.selected[p.id] = true
            },
            onLongClick = { model.selected[p.id] = true },
        )) {
        bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
        LabelColours[f?.label]?.let { Box(Modifier.fillMaxSize().border(3.dp, it)) }
        if (f != null && (f.starred || f.bookmarked)) {
            Text((if (f.starred) "⭐" else "") + (if (f.bookmarked) "🔖" else ""), fontSize = 11.sp,
                modifier = Modifier.align(Alignment.TopStart).padding(3.dp).clip(RoundedCornerShape(10.dp))
                    .background(Color(0x8C000000)).padding(horizontal = 4.dp, vertical = 1.dp))
        }
        if (f?.edited == true) {
            Text("✨", fontSize = 10.sp, modifier = Modifier.align(Alignment.BottomEnd).padding(3.dp).clip(CircleShape)
                .background(Color(0x8C000000)).padding(3.dp))
        }
        if (sel) {
            Box(Modifier.fillMaxSize().border(3.dp, Accent))
            Text("✓", color = Color.White, fontSize = 11.sp, modifier = Modifier.align(Alignment.TopEnd).padding(4.dp)
                .clip(CircleShape).background(Accent).padding(horizontal = 5.dp, vertical = 1.dp))
        }
    }
}

@Composable
private fun BottomBar(model: AppModel) {
    Row(Modifier.fillMaxWidth().background(Panel).padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceAround) {
        for ((icon, label) in listOf("🏷" to "Label", "#" to "Keywords", "📅" to "Date", "✏️" to "Rename")) {
            BarButton(icon, label) { model.screen = Screen.Details }
        }
        BarButton("🗑", "Delete") { model.delete() }  // Android asks "Move to Trash?" itself
    }
}

@Composable
private fun BarButton(icon: String, label: String, onClick: () -> Unit) {
    Column(Modifier.clickable(onClick = onClick).padding(horizontal = 8.dp, vertical = 2.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        Text(icon, fontSize = 20.sp)
        Text(label, fontSize = 11.sp, color = Color.White)
    }
}
