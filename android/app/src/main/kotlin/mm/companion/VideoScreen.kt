package mm.companion

import android.widget.VideoView
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.IconButton
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import kotlinx.coroutines.delay
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

private val WHEN = DateTimeFormatter.ofPattern("EEE, MMM d, h:mm a")

private fun clock(ms: Long): String {
    val s = (ms / 1000).toInt()
    return if (s >= 3600) "%d:%02d:%02d".format(s / 3600, s / 60 % 60, s % 60) else "%d:%02d".format(s / 60, s % 60)
}

/** A video: play it (OneDrive's stream), rename, move, delete; swipe for the next or previous photo or video. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VideoScreen(model: AppModel, video: Photo) {
    var view by remember { mutableStateOf<VideoView?>(null) }
    var ready by remember { mutableStateOf(false) }
    var playingNow by remember { mutableStateOf(false) }
    var position by remember { mutableFloatStateOf(0f) }   // ms
    var length by remember { mutableFloatStateOf(video.durationMs.toFloat()) }
    var dragging by remember { mutableStateOf(false) }
    var renaming by remember { mutableStateOf<String?>(null) }
    var failed by remember { mutableStateOf("") }

    fun leave() { view?.stopPlayback(); model.playing = null; model.screen = Screen.Grid }
    fun go(delta: Int) {
        val next = model.neighbour(video, delta) ?: run {
            model.message = if (delta > 0) "That's the last one" else "That's the first one"; return
        }
        view?.stopPlayback()
        model.openItem(next)
    }
    BackHandler { leave() }

    LaunchedEffect(video.id, view) {
        val v = view ?: return@LaunchedEffect
        val source = model.videoSource(video) ?: run { failed = model.message.ifEmpty { "Can't play it now" }; return@LaunchedEffect }
        v.setOnPreparedListener { mp -> ready = true; length = mp.duration.toFloat(); v.start(); playingNow = true }
        v.setOnCompletionListener { playingNow = false }
        v.setOnErrorListener { _, _, _ -> failed = "This video can't be played here"; true }
        v.setVideoURI(source)
    }
    LaunchedEffect(video.id) {  // the timeline follows the video
        while (true) {
            view?.let { v -> if (!dragging && ready) position = v.currentPosition.toFloat(); playingNow = v.isPlaying }
            delay(200)
        }
    }
    DisposableEffect(video.id) { onDispose { view?.stopPlayback() } }

    Column(Modifier.fillMaxSize().background(Background)) {
        Row(Modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { leave() }) { LineIcon(Line.Back, "Back") }
            Column(Modifier.weight(1f)) {
                Text(video.name, fontSize = 14.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
                if (video.takenMillis > 0) Text(Instant.ofEpochMilli(video.takenMillis).atZone(ZoneId.systemDefault()).format(WHEN),
                    fontSize = 12.sp, color = Dim)
            }
            IconButton(onClick = {  // Rename: with the rename pattern, as photos are
                val plan = model.renamePreview(listOf(video)).firstOrNull()?.second
                if (plan == null) model.message = if (model.dateTaken(video) == null) "This video has no date to name it by"
                    else "Already named by the pattern" else renaming = plan
            }) { LineIcon(Line.Pencil, "Rename") }
            if (video.inCloud) IconButton(onClick = {
                val next = model.neighbour(video, 1) ?: model.neighbour(video, -1)
                model.moving = MoveRequest(listOf(video)) { view?.stopPlayback(); if (next != null) model.openItem(next) else leave() }
            }) { LineIcon(Line.Folder, "Move") }
            IconButton(onClick = {
                val next = model.neighbour(video, 1) ?: model.neighbour(video, -1)
                model.delete(listOf(video)) { view?.stopPlayback(); if (next != null) model.openItem(next) else leave() }
            }) { LineIcon(Line.Delete, "Delete") }
        }
        Note(model)
        // the video (swipe sideways: the next or previous photo or video)
        val swipe = with(LocalDensity.current) { 80.dp.toPx() }
        Box(Modifier.fillMaxWidth().weight(1f).background(Color(0xFF111214)).pointerInput(video.id) {
            var dx = 0f
            detectHorizontalDragGestures(onDragStart = { dx = 0f }, onDragEnd = {
                if (dx < -swipe) go(1) else if (dx > swipe) go(-1)
            }) { _, d -> dx += d }
        }, contentAlignment = Alignment.Center) {
            AndroidView({ VideoView(it).also { v -> view = v } }, Modifier.fillMaxWidth())
            if (failed.isNotEmpty()) Text(failed, color = Dim, modifier = Modifier.padding(24.dp))
            else if (!ready) CircularProgressIndicator()
        }
        // the controls
        Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp)) {
            Slider(position, { dragging = true; position = it }, valueRange = 0f..maxOf(1f, length),
                onValueChangeFinished = { view?.seekTo(position.toInt()); dragging = false },
                colors = SliderDefaults.colors(activeTrackColor = Color.White, inactiveTrackColor = Color(0xFF3A3D44)),
                thumb = { Box(Modifier.size(20.dp).shadow(2.dp, CircleShape).clip(CircleShape).background(Color(0xFFF1F1F1))) })
            Row(Modifier.fillMaxWidth()) {
                Text(clock(position.toLong()), fontSize = 12.sp, color = Dim)
                Spacer(Modifier.weight(1f))
                Text(clock(length.toLong()), fontSize = 12.sp, color = Dim)
            }
            Row(Modifier.fillMaxWidth().padding(top = 4.dp), horizontalArrangement = Arrangement.Center,
                verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { view?.let { it.seekTo(maxOf(0, it.currentPosition - 10_000)) } }) { Text("−10 s", color = Color.White) }
                Spacer(Modifier.width(18.dp))
                Box(Modifier.size(56.dp).clip(CircleShape).background(Color.White).clickable(enabled = ready) {
                    view?.let { if (it.isPlaying) it.pause() else it.start(); playingNow = it.isPlaying }
                }, contentAlignment = Alignment.Center) {
                    Text(if (playingNow) "❚❚" else "▶", color = Background, fontSize = 20.sp, fontWeight = FontWeight.Bold)
                }
                Spacer(Modifier.width(18.dp))
                TextButton(onClick = { view?.let { it.seekTo(minOf(it.duration, it.currentPosition + 10_000)) } }) { Text("+10 s", color = Color.White) }
            }
        }
    }
    renaming?.let { newName ->
        AlertDialog(onDismissRequest = { renaming = null }, title = { Text("Rename?") },
            text = { Text("${video.name}\n→ $newName") },
            confirmButton = { TextButton(onClick = { renaming = null; model.rename(listOf(video)) }) { Text("Rename") } },
            dismissButton = { TextButton(onClick = { renaming = null }) { Text("Cancel") } })
    }
}
