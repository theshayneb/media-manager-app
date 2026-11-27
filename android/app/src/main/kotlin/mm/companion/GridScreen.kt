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
import androidx.compose.foundation.layout.height
import androidx.compose.material3.IconButton
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.PlatformTextStyle
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.style.LineHeightStyle
import mm.core.AlbumWeek
import mm.core.albumWeek
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
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter


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
            // The album's weeks, numbered as on the PC (Week 1 starts January 1).
            val groups = remember(model.photos) {
                model.photos.groupBy {
                    albumWeek(Instant.ofEpochMilli(if (it.takenMillis > 0) it.takenMillis else it.modified * 1000)
                        .atZone(ZoneId.systemDefault()).toLocalDate())
                }
            }
            LazyVerticalGrid(GridCells.Adaptive(110.dp), Modifier.weight(1f).padding(2.dp),
                horizontalArrangement = Arrangement.spacedBy(3.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
                for ((week, group) in groups) {
                    val key = "${week.year}-${week.number}"
                    val shut = key in model.collapsed
                    item(span = { GridItemSpan(maxLineSpan) }, key = "w$key") {
                        WeekHeader(week, group.size, shut) { model.toggleWeek(key) }  // tap: fold the week shut / open
                    }
                    if (!shut) items(group, key = { it.id }) { p -> Tile(model, p) }
                }
            }
            if (model.selected.isNotEmpty() && !wide) BottomBar(model)
        }
    }
}

private val DAY = DateTimeFormatter.ofPattern("MMM d")

@Composable
private fun WeekHeader(week: AlbumWeek, count: Int, shut: Boolean, onToggle: () -> Unit) {
    val sameMonth = week.first.month == week.last.month
    val dates = week.first.format(DAY) + " – " + (if (sameMonth) week.last.dayOfMonth.toString() else week.last.format(DAY)) +
        if (week.year != java.time.LocalDate.now().year) ", ${week.year}" else ""
    Row(Modifier.fillMaxWidth().clickable(onClick = onToggle).padding(start = 14.dp, end = 14.dp, top = 16.dp, bottom = 8.dp),
        verticalAlignment = Alignment.Bottom) {
        Text("Week ${week.number}", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = Color.White)
        Text(dates, fontSize = 13.sp, color = Dim, modifier = Modifier.padding(start = 10.dp, bottom = 3.dp))
        Spacer(Modifier.weight(1f))
        Text("$count", fontSize = 12.sp, color = Dim, modifier = Modifier.padding(bottom = 3.dp))
        Text(if (shut) "▸" else "▾", fontSize = 14.sp, color = Dim, modifier = Modifier.padding(start = 10.dp, bottom = 2.dp))
    }
}

@Composable
private fun TopBar(model: AppModel) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().background(Background)) {
        Row(Modifier.fillMaxWidth().padding(start = 6.dp, end = 4.dp, top = 6.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            if (model.selected.isNotEmpty()) {
                TextButton(onClick = { model.selected.clear() }) { Text("✕  ${model.selected.size} selected", color = Color.White, fontSize = 18.sp) }
            } else {
                Box {
                    Column(Modifier.clip(RoundedCornerShape(10.dp)).clickable { open = true }.padding(horizontal = 10.dp, vertical = 4.dp)) {
                        Text("${model.folder?.name?.removePrefix("Camera Roll › ") ?: "No photos"} ▾", color = Color.White,
                            fontSize = 20.sp, fontWeight = FontWeight.Bold)
                        Row {
                            val n = model.photos.size
                            Text("${if (model.inCloud) "OneDrive" else "Phone"}, ${"%,d".format(n)} photo${if (n == 1) "" else "s"}",
                                color = Dim, fontSize = 12.5.sp)
                            if (model.pending > 0) Text(", ${model.pending} change${if (model.pending == 1) "" else "s"} to sync",
                                color = Waiting, fontSize = 12.5.sp)
                        }
                    }
                    DropdownMenu(open, { open = false }) {
                        val favs = model.folders.count { model.isFavorite(it) }
                        if (favs > 0) Text("Favourites", color = Dim, fontSize = 12.sp,
                            modifier = Modifier.padding(start = 12.dp, top = 6.dp, bottom = 2.dp))
                        model.folders.forEachIndexed { i, f ->
                            if (favs > 0 && i == favs) HorizontalDivider(Modifier.padding(vertical = 4.dp))
                            val fav = model.isFavorite(f)
                            DropdownMenuItem(
                                text = { Text("${f.name}  (${"%,d".format(f.count)})", modifier = Modifier.padding(start = (f.depth * 14).dp)) },
                                onClick = { open = false; model.open(f) },
                                trailingIcon = if (f.inCloud) null else { {
                                    Text(if (fav) "★" else "☆", fontSize = 22.sp, color = if (fav) Color(0xFFE8C020) else Dim,
                                        modifier = Modifier.clip(CircleShape).clickable { model.toggleFavorite(f) }
                                            .padding(horizontal = 10.dp, vertical = 4.dp))
                                } },
                            )
                        }
                    }
                }
            }
            Spacer(Modifier.weight(1f))
            IconButton(onClick = { model.refresh() }) { LineIcon(Line.Refresh, "Refresh") }
            IconButton(onClick = { model.screen = Screen.Settings }) { LineIcon(Line.Settings, "Settings") }
        }
        // 📱 the phone's folders, or ☁ OneDrive's Camera Roll: always in sight
        if (model.selected.isEmpty()) Row(Modifier.fillMaxWidth().padding(start = 14.dp, end = 14.dp, bottom = 6.dp)
            .clip(RoundedCornerShape(10.dp)).background(ChipColour).padding(3.dp)) {
            for ((cloud, text) in listOf(false to "Phone", true to "OneDrive")) {
                val on = model.inCloud == cloud
                Text(text, color = if (on) Color.White else Dim, fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
                    textAlign = TextAlign.Center,
                    modifier = Modifier.weight(1f).clip(RoundedCornerShape(8.dp))
                        .background(if (on) Color(0xFF3E434B) else Color.Transparent)
                        .clickable { model.useCloud(cloud) }.padding(vertical = 7.dp))
            }
        }
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
        // a label: a strip along the bottom edge (covers less of the photo than a frame)
        LabelColours[f?.label]?.let { Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(4.dp).background(it)) }
        if (f != null && (f.starred || f.bookmarked)) {
            Text((if (f.starred) "⭐" else "") + (if (f.bookmarked) "🔖" else ""), fontSize = 10.sp,
                modifier = Modifier.align(Alignment.TopStart).padding(3.dp))
        }
        if (f?.edited == true) {
            Box(Modifier.align(Alignment.BottomEnd).padding(end = 4.dp, bottom = 7.dp).size(17.dp).clip(CircleShape)
                .background(Color(0x8C000000)), contentAlignment = Alignment.Center) {
                // (no font padding, the line exactly the glyph's height: the ✨ sits in the middle of its circle)
                Text("✨", fontSize = 9.sp, lineHeight = 9.sp, textAlign = TextAlign.Center, style = TextStyle(
                    platformStyle = PlatformTextStyle(includeFontPadding = false),
                    lineHeightStyle = LineHeightStyle(LineHeightStyle.Alignment.Center, LineHeightStyle.Trim.Both)))
            }
        }
        if (p.id in model.waitingIds && !sel) {  // a change not in OneDrive yet
            Box(Modifier.align(Alignment.TopEnd).padding(4.dp).size(11.dp).clip(CircleShape).background(Color(0x73000000))
                .padding(1.5.dp).clip(CircleShape).background(Waiting))
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
    // line icons, as on the photo's own screen
    Row(Modifier.fillMaxWidth().background(Panel).padding(vertical = 6.dp), horizontalArrangement = Arrangement.SpaceAround) {
        for ((icon, label) in listOf(Line.Tag to "Label", Line.Hash to "Keywords", Line.Calendar to "Date", Line.Pencil to "Rename")) {
            BarButton(icon, label) { model.screen = Screen.Details }
        }
        if (model.selected.size >= 2) BarButton(Line.Compare, "Compare") { model.startCompare() }  // sideways, side by side
        if (model.inCloud) BarButton(Line.Folder, "Move") { model.moving = MoveRequest(model.selection) }
        BarButton(Line.Delete, "Delete") { model.delete() }  // Android asks "Move to Trash?" itself
    }
}

@Composable
private fun BarButton(icon: androidx.compose.ui.graphics.vector.ImageVector, label: String, onClick: () -> Unit) {
    Column(Modifier.clip(RoundedCornerShape(10.dp)).clickable(onClick = onClick).padding(horizontal = 8.dp, vertical = 4.dp),
        horizontalAlignment = Alignment.CenterHorizontally) {
        LineIcon(icon, label, modifier = Modifier.size(24.dp))
        Text(label, fontSize = 11.sp, color = Color.White, modifier = Modifier.padding(top = 2.dp))
    }
}
