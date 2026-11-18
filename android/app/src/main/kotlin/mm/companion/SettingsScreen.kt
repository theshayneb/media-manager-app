package mm.companion

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.net.Uri
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

@Composable
fun SettingsScreen(model: AppModel) {
    val context = LocalContext.current
    val drive = model.drive
    var signedIn by remember { mutableStateOf(drive.signedIn) }
    var clientId by remember { mutableStateOf(drive.clientId) }
    var code by remember { mutableStateOf<OneDrive.DeviceCode?>(null) }
    var problem by remember { mutableStateOf("") }
    var entries by remember { mutableStateOf(model.queue.all()) }

    LaunchedEffect(code) {
        val c = code ?: return@LaunchedEffect
        while (System.currentTimeMillis() < c.expiresAt) {
            delay(c.interval * 1000L)
            val done = withContext(Dispatchers.IO) { runCatching { drive.finishSignIn(c) } }
            if (done.isFailure) { problem = done.exceptionOrNull()?.message ?: "Sign-in failed"; code = null; return@LaunchedEffect }
            if (done.getOrDefault(false)) {
                signedIn = true; code = null
                model.syncNow()
                return@LaunchedEffect
            }
        }
        code = null
        problem = "The code ran out; try again."
    }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().background(Panel).padding(8.dp), verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { model.screen = Screen.Grid }) { Text("←  Settings", color = Color.White, fontSize = 17.sp) }
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            Title("OneDrive")
            Text("What you do here (keywords, labels, dates, names, edits, deletes) is done to the same photo in your " +
                "OneDrive Camera Roll too, so your PC gets it.", color = Dim, fontSize = 13.sp)
            Spacer(Modifier.height(10.dp))
            if (signedIn) {
                Text("Signed in" + drive.account.let { if (it.isNotEmpty()) " as $it" else "" })
                OutlinedButton(onClick = { drive.signOut(); signedIn = false }) { Text("Sign out") }
            } else {
                OutlinedTextField(clientId, { clientId = it; drive.clientId = it }, Modifier.fillMaxWidth(),
                    label = { Text("Microsoft app ID") }, singleLine = true)
                val c = code
                if (c == null) {
                    Button(onClick = {
                        problem = ""
                        Thread {
                            try { code = drive.startSignIn() } catch (e: Exception) { problem = e.message ?: "Couldn't start sign-in" }
                        }.start()
                    }, enabled = clientId.isNotBlank(), modifier = Modifier.padding(top = 8.dp)) { Text("Sign in to OneDrive") }
                } else {
                    Text("\nOn any device, go to ${c.verificationUri} and enter this code:", fontSize = 14.sp)
                    Text(c.userCode, fontSize = 30.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(8.dp))
                    Row {
                        Button(onClick = {
                            (context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager)
                                .setPrimaryClip(ClipData.newPlainText("code", c.userCode))
                            context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(c.verificationUri)))
                        }) { Text("Copy the code and open the page") }
                    }
                    Text("Waiting for you to sign in…", color = Dim, fontSize = 13.sp)
                }
            }
            if (problem.isNotEmpty()) Text(problem, color = Color(0xFFE0A040), fontSize = 13.sp)

            Title("Sync")
            Text(if (entries.isEmpty()) "Everything is synced." else "${entries.size} change${if (entries.size == 1) "" else "s"} waiting:")
            for (e in entries.take(30)) {
                Text("• ${e.name}: ${e.change::class.simpleName}" + if (e.error.isNotEmpty()) " — ${e.error}" else "",
                    fontSize = 12.sp, color = Dim)
            }
            OutlinedButton(onClick = { model.syncNow(); entries = model.queue.all() }, enabled = signedIn,
                modifier = Modifier.padding(top = 6.dp)) { Text("Sync now") }

            Title("From your PC")
            val sets = model.shared.keywordSets
            Text(if (sets.isEmpty()) "No keyword sets yet. Open Media Manager on the PC once (it puts them in " +
                "OneDrive › Documents › Phone › Media Manager), then Sync now." else "Keyword sets: ${sets.keys.joinToString()}", fontSize = 13.sp)
            Text("Rename pattern: ${model.shared.renamePattern}", fontSize = 13.sp)
            Spacer(Modifier.height(30.dp))
            Text("Media Manager companion ${BuildConfig.VERSION_NAME}", color = Dim, fontSize = 12.sp)
        }
    }
}

@Composable
private fun Title(text: String) =
    Text(text, fontWeight = FontWeight.Bold, fontSize = 17.sp, modifier = Modifier.padding(top = 18.dp, bottom = 4.dp))
