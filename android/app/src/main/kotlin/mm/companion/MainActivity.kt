package mm.companion

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.os.Environment
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.TextButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

val Background = Color(0xFF1E2023)
val Panel = Color(0xFF26282C)
val Accent = Color(0xFF3B6FC4)
val Dim = Color(0xFF9AA0A8)
val Waiting = Color(0xFFE2B04A)   // a change not in OneDrive yet
val ChipColour = Color(0xFF2E3238)
val LineColour = Color(0xFF34383F)
val LabelColours = mapOf("Red" to Color(0xFFE04848), "Yellow" to Color(0xFFE8C020), "Green" to Color(0xFF30A050),
    "Blue" to Color(0xFF3B78D8), "Purple" to Color(0xFF9050D0))

class MainActivity : ComponentActivity() {
    private val model: AppModel by viewModels()
    private var allowed by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme(colorScheme = darkColorScheme(primary = Accent, background = Background, surface = Panel)) {
                // Android 15 draws apps under the status and navigation bars: keep everything clear of them
                // (and of the keyboard).
                Surface(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing), color = Background) {
                    if (!allowed) AskForAccess { askForAccess() } else App(model)
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        val was = allowed
        allowed = Environment.isExternalStorageManager()
        if (allowed && !was) model.start()
        model.checkSignIn()  // back from the browser after entering the OneDrive code
    }

    private fun askForAccess() {
        startActivity(Intent(Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION, Uri.parse("package:$packageName")))
    }
}

@Composable
fun AskForAccess(onAsk: () -> Unit) {
    Column(Modifier.fillMaxSize().padding(24.dp), verticalArrangement = Arrangement.Center) {
        Text("Media Manager", fontSize = 24.sp)
        Text("\nTo add keywords, labels and dates to your photos, rename them and save edits, this app needs " +
            "\"All files access\". It only changes the photos you pick.\n", color = Dim)
        Button(onClick = onAsk) { Text("Allow access") }
    }
}

@Composable
fun App(model: AppModel) {
    BackHandler(enabled = model.screen != Screen.Grid || model.selected.isNotEmpty()) {
        when {
            model.screen == Screen.Edit -> model.screen = Screen.Grid  // EditScreen asks first if changed
            model.screen == Screen.Compare -> model.leaveCompare()
            model.screen != Screen.Grid -> model.screen = Screen.Grid
            else -> model.selected.clear()
        }
    }
    // Deleting: Android asks "Move to Trash?" itself.
    val trash = rememberLauncherForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) {
        model.trashed(it.resultCode == android.app.Activity.RESULT_OK)
    }
    LaunchedEffect(model.trashRequest) {
        model.trashRequest?.let { trash.launch(IntentSenderRequest.Builder(it.sender).build()) }
    }
    model.moving?.let { MoveDialog(model, it) }
    // Deleting OneDrive photos: asked here (they go to OneDrive's recycle bin).
    model.cloudDelete?.let { d ->
        val n = d.photos.size
        AlertDialog(onDismissRequest = { model.confirmCloudDelete(false) },
            title = { Text(if (n == 1) "Delete ${d.photos[0].name} from OneDrive?" else "Delete $n photos from OneDrive?") },
            text = { Text("They go to OneDrive's recycle bin, where they can be restored.") },
            confirmButton = { TextButton(onClick = { model.confirmCloudDelete(true) }) { Text("Delete") } },
            dismissButton = { TextButton(onClick = { model.confirmCloudDelete(false) }) { Text("Cancel") } })
    }
    when (model.screen) {
        Screen.Grid -> GridScreen(model)
        Screen.Details -> DetailsScreen(model)
        // (key: another photo, swiped to, starts afresh: its own sliders, crop and turn)
        Screen.Edit -> model.editing?.let { key(it.id) { EditScreen(model, it) } } ?: run { model.screen = Screen.Grid }
        Screen.Settings -> SettingsScreen(model)
        Screen.Compare -> CompareScreen(model)
        Screen.Video -> model.playing?.let { key(it.id) { VideoScreen(model, it) } } ?: run { model.screen = Screen.Grid }
    }
}

@Composable
fun Note(model: AppModel) {
    if (model.message.isNotEmpty()) {
        Text(model.message, color = Color.White, modifier = Modifier.background(Panel).padding(10.dp))
    }
}
