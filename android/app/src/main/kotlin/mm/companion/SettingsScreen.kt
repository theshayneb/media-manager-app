package mm.companion

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import mm.core.Change

private val Good = Color(0xFF7FC79A)

/** What went wrong, in plain words (OneDrive's own text is shown when the row is tapped). */
private fun plain(error: String): String = when {
    error.isEmpty() -> ""
    "409" in error || "resourceModified" in error -> "OneDrive was still busy with it. Will try again."
    "Not in OneDrive yet" in error -> "Not in OneDrive yet. Waiting for the camera upload."
    "401" in error || "403" in error || "Not signed in" in error -> "OneDrive refused. Sign out and in again."
    "404" in error -> "Not found in OneDrive (moved or deleted there?)."
    "Unable to resolve host" in error || "timeout" in error.lowercase() || "connect" in error.lowercase() ->
        "No connection. Will try again."
    else -> "Couldn't be done. Will try again."
}

private fun kind(c: Change) = when (c) {
    is Change.Keywords -> "keyword"
    is Change.Label, is Change.Flag, Change.ClearLabels -> "label"
    is Change.DateTaken -> "date taken"
    is Change.Rename -> "rename"
    is Change.Edit -> "edit"
    Change.Delete -> "delete"
}

/** "5 keyword changes", or "Keywords, date taken, rename". */
private fun summary(changes: List<Change>): String {
    val kinds = changes.map { kind(it) }
    val distinct = kinds.distinct()
    if (distinct.size == 1) {
        val k = distinct[0]
        return if (kinds.size == 1) "${k.replaceFirstChar { it.uppercase() }}" else "${kinds.size} $k changes"
    }
    return distinct.joinToString(", ") { if (it == "keyword" || it == "label") it + "s" else it }.replaceFirstChar { it.uppercase() }
}

@Composable
fun SettingsScreen(model: AppModel) {
    val context = LocalContext.current
    val drive = model.drive
    val signedIn = model.signedIn
    var clientId by remember { mutableStateOf(drive.clientId) }
    val code = model.signInCode
    val problem = model.signInProblem
    var entries by remember { mutableStateOf(model.queue.all()) }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 4.dp, top = 4.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            IconButton(onClick = { model.screen = Screen.Grid }) { LineIcon(Line.Back, "Back") }
            Text("Settings", color = Color.White, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(bottom = 24.dp)) {
            // ---------------------------------------------------------------- sync, first: looked at most
            val byPhoto = entries.groupBy { it.photoId }
            Card {
                if (!signedIn) {
                    Text("Not signed in", fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
                    Text("Sign in to OneDrive below; then your changes go to your PC.", fontSize = 14.sp, color = Dim,
                        modifier = Modifier.padding(top = 4.dp))
                } else if (entries.isEmpty()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        LineIcon(Line.Check, "Synced", Good, Modifier.size(28.dp))
                        Text("Everything is synced", fontSize = 20.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.padding(start = 8.dp))
                    }
                } else {
                    Text("${entries.size}", fontSize = 34.sp, fontWeight = FontWeight.ExtraBold)
                    Text("change${if (entries.size == 1) "" else "s"} to ${byPhoto.size} photo${if (byPhoto.size == 1) "" else "s"} " +
                        "waiting for OneDrive", fontSize = 14.sp, modifier = Modifier.padding(top = 2.dp))
                    val busy = byPhoto.values.count { es -> es.any { "409" in it.error || "resourceModified" in it.error } }
                    val state = when {
                        !model.cloud.online() -> model.cloud.whyOffline() + ". They'll go when you're back online."
                        busy > 0 -> "OneDrive was still busy with $busy of them. Trying again soon."
                        else -> "They go in the background, or tap Sync now."
                    }
                    Row(Modifier.padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).clip(CircleShape).background(Waiting))
                        Text(state, fontSize = 13.5.sp, color = Color(0xFFC9CCD1), modifier = Modifier.padding(start = 8.dp))
                    }
                }
                if (signedIn) Row(Modifier.padding(top = 12.dp)) {
                    Button(onClick = { model.syncNow(); entries = model.queue.all() }) { Text("Sync now", fontWeight = FontWeight.Bold) }
                    if (entries.isNotEmpty()) {
                        var sure by remember { mutableStateOf(false) }
                        Spacer(Modifier.width(8.dp))
                        TextButton(onClick = { sure = true }) { Text("Clear the list", color = Color(0xFFD8DADD)) }
                        if (sure) AlertDialog(onDismissRequest = { sure = false },
                            title = { Text("Clear the list?") },
                            text = { Text("The ${entries.size} waiting change${if (entries.size == 1) "" else "s"} won't be made " +
                                "to OneDrive's copies. The photos on the phone keep them.") },
                            confirmButton = { TextButton(onClick = {
                                model.clearQueue(); entries = model.queue.all(); sure = false
                            }) { Text("Clear") } },
                            dismissButton = { TextButton(onClick = { sure = false }) { Text("Cancel") } })
                    }
                }
            }
            if (byPhoto.isNotEmpty()) Card(vertical = 4.dp) {
                byPhoto.entries.take(40).forEachIndexed { i, (photoId, es) ->
                    if (i > 0) Box(Modifier.fillMaxWidth().height(1.dp).background(LineColour))
                    QueuedPhoto(model, photoId, es)
                }
                if (byPhoto.size > 40) Text("and ${byPhoto.size - 40} more photos", color = Dim, fontSize = 12.5.sp,
                    modifier = Modifier.padding(vertical = 8.dp))
            }

            // ---------------------------------------------------------------- Steam screenshots (the PC imports them)
            if (signedIn) {
                androidx.compose.runtime.LaunchedEffect(Unit) { model.watchSteam() }
                Heading("Steam screenshots")
                Card { SteamCard(model) }
            }

            // ---------------------------------------------------------------- OneDrive
            Heading("OneDrive")
            Card {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("Wi-Fi only", fontWeight = FontWeight.SemiBold)
                        Text("Don't use mobile data for OneDrive. Changes wait until you're on Wi-Fi.", color = Dim, fontSize = 12.5.sp)
                    }
                    Switch(model.wifiOnly, { model.changeWifiOnly(it) })
                }
                Box(Modifier.padding(vertical = 12.dp).fillMaxWidth().height(1.dp).background(LineColour))
                if (signedIn) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Signed in", fontWeight = FontWeight.SemiBold)
                            if (drive.account.isNotEmpty()) Text(drive.account, color = Dim, fontSize = 12.5.sp)
                        }
                        TextButton(onClick = { model.signOut() }) { Text("Sign out", color = Color(0xFF9CC0FF), fontWeight = FontWeight.SemiBold) }
                    }
                } else {
                    val c = code
                    if (c == null) {
                        Text("Not signed in", fontWeight = FontWeight.SemiBold)
                        Button(onClick = { model.startSignIn() }, enabled = clientId.isNotBlank(), modifier = Modifier.padding(top = 8.dp)) { Text("Sign in to OneDrive") }
                    } else {
                        Text("On any device, go to ${c.verificationUri} and enter this code:", fontSize = 14.sp)
                        Text(c.userCode, fontSize = 30.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(vertical = 8.dp))
                        Button(onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                                .setPrimaryClip(ClipData.newPlainText("code", c.userCode))
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(c.verificationUri)))
                        }) { Text("Copy the code and open the page") }
                        Text("Waiting for you to sign in…", color = Dim, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
                    }
                }
                if (problem.isNotEmpty()) Text(problem, color = Waiting, fontSize = 13.sp, modifier = Modifier.padding(top = 6.dp))
            }

            // ---------------------------------------------------------------- rarely needed
            Heading("From your PC")
            Card {
                val sets = model.shared.keywordSets
                Text(if (sets.isEmpty()) "No keyword sets yet. Open Media Manager on the PC once (it puts them in " +
                    "OneDrive › Documents › Phone › Media Manager), then Sync now." else "Keyword sets: ${sets.keys.joinToString()}", fontSize = 13.5.sp)
                Text("Rename pattern: ${model.shared.renamePattern}", fontSize = 13.5.sp, modifier = Modifier.padding(top = 4.dp))
            }
            if (!signedIn) {
                Heading("Microsoft app ID")
                Card {
                    OutlinedTextField(clientId, { clientId = it; drive.clientId = it }, Modifier.fillMaxWidth(),
                        label = { Text("App ID") }, singleLine = true)
                }
            }
            Text("Media Manager companion ${BuildConfig.VERSION_NAME}", color = Dim, fontSize = 12.sp,
                modifier = Modifier.padding(start = 18.dp, top = 20.dp))
        }
    }
}

/** One photo's waiting changes: its picture, name, what's waiting and what's happening (tap: OneDrive's own text). */
@Composable
private fun QueuedPhoto(model: AppModel, photoId: Long, es: List<QueueEntry>) {
    var open by remember { mutableStateOf(false) }
    val bitmap by produceState<Bitmap?>(null, photoId) { value = model.queuedThumbnail(photoId) }
    val error = es.firstOrNull { it.error.isNotEmpty() }?.error ?: ""
    Row(Modifier.fillMaxWidth().clickable(enabled = error.isNotEmpty()) { open = !open }.padding(vertical = 10.dp)) {
        Box(Modifier.size(42.dp).clip(RoundedCornerShape(8.dp)).background(ChipColour)) {
            bitmap?.let { Image(it.asImageBitmap(), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop) }
        }
        Column(Modifier.padding(start = 10.dp).weight(1f)) {
            Text(es.last().name, fontSize = 13.5.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
            Text(summary(es.map { it.change }), fontSize = 12.5.sp, color = Dim)
            if (error.isEmpty()) Text("Next in line", fontSize = 12.5.sp, color = Good)
            else Text(plain(error), fontSize = 12.5.sp, color = Waiting)
            if (open) Text(error, fontSize = 11.sp, color = Dim, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun Card(vertical: androidx.compose.ui.unit.Dp = 14.dp, content: @Composable ColumnScope.() -> Unit) =
    Column(Modifier.padding(horizontal = 14.dp, vertical = 6.dp).fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(Panel)
        .padding(horizontal = 14.dp, vertical = vertical), content = content)

@Composable
private fun Heading(text: String) =
    Text(text, fontWeight = FontWeight.Bold, fontSize = 14.sp, color = Color(0xFFC9CCD1),
        modifier = Modifier.padding(start = 18.dp, top = 14.dp, bottom = 2.dp))

private val WHEN = java.time.format.DateTimeFormatter.ofPattern("h:mm a")
private val WHEN_DAY = java.time.format.DateTimeFormatter.ofPattern("MMM d, h:mm a")

private fun shown(t: java.time.LocalDateTime): String =
    if (t.toLocalDate() == java.time.LocalDate.now()) "today ${t.format(WHEN)}" else t.format(WHEN_DAY)

/** Import now: the PC (Media Manager, running) imports them, as its own Steam import does. */
@Composable
private fun SteamCard(model: AppModel) {
    val s = model.steam
    val r = s.result
    val answered = r != null && r.optString("id") == s.asked
    val state = if (answered) r!!.optString("state") else ""
    val waiting = s.asked.isNotEmpty() && (!answered || state == "running")
    Text("Your PC imports them into the Steam folder in OneDrive.", fontSize = 13.5.sp, color = Dim)
    // the last finished import
    val last = r?.takeIf { it.optString("state") == "done" }
    if (last != null) {
        val time = runCatching { java.time.LocalDateTime.parse(last.optString("time")) }.getOrNull()
        val n = last.optInt("imported")
        val games = last.optJSONObject("games")?.length() ?: 0
        Text("Last import: ${time?.let { shown(it) } ?: ""}", fontSize = 14.sp, fontWeight = FontWeight.SemiBold,
            modifier = Modifier.padding(top = 10.dp))
        Text(if (n == 0) "Nothing new" else "$n screenshot${if (n == 1) "" else "s"} from $games game${if (games == 1) "" else "s"}" +
            if (last.optInt("failed") > 0) ", ${last.optInt("failed")} couldn't be copied" else "", fontSize = 13.5.sp)
    }
    if (answered && state == "failed") Text("The PC couldn't import them: ${r!!.optString("problem")}", fontSize = 13.sp,
        color = Waiting, modifier = Modifier.padding(top = 8.dp))
    if (waiting) {
        val at = java.time.Instant.ofEpochMilli(s.askedAt).atZone(java.time.ZoneId.systemDefault()).toLocalDateTime()
        val text = if (state == "running") "Your PC is importing them…"
            else if (System.currentTimeMillis() - s.askedAt > 5 * 60_000) "Asked your PC at ${at.format(WHEN)}. No answer yet: is it on, with Media Manager running?"
            else "Asked your PC at ${at.format(WHEN)}. Waiting…"
        Row(Modifier.padding(top = 10.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).clip(CircleShape).background(Waiting))
            Text(text, fontSize = 13.5.sp, color = Color(0xFFC9CCD1), modifier = Modifier.padding(start = 8.dp))
        }
    }
    Button(onClick = { model.importSteam() }, enabled = !waiting || System.currentTimeMillis() - s.askedAt > 5 * 60_000,
        modifier = Modifier.padding(top = 12.dp)) { Text("Import now", fontWeight = FontWeight.Bold) }
}
