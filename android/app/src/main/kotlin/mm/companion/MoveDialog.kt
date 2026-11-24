package mm.companion

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch

/** Photos to move, and what to do after (the Edit screen: on to the next photo). */
class MoveRequest(val photos: List<Photo>, val then: (() -> Unit)? = null)

/** "Move N photos to": the Pictures folders as a tree; + New folder inside the one chosen. */
@Composable
fun MoveDialog(model: AppModel, request: MoveRequest) {
    var chosen by remember { mutableStateOf<Folder?>(null) }
    var naming by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var making by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val n = request.photos.size
    val here = model.folder?.id
    AlertDialog(
        onDismissRequest = { model.moving = null },
        title = { Text(if (n == 1) "Move to" else "Move $n photos to") },
        text = {
            Column {
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = 380.dp), rememberLazyListState()) {
                    items(model.folders.filter { it.inCloud }, key = { it.id }) { f ->
                        val on = chosen?.id == f.id
                        val isHere = f.id == here
                        Text(f.name + if (isHere) "  (here)" else "", fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis,
                            color = if (isHere) Dim else Color.White, fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal,
                            modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp))
                                .background(if (on) Accent else Color.Transparent)
                                .clickable(enabled = !isHere) { chosen = f }
                                .padding(start = (10 + f.depth * 16).dp, end = 10.dp, top = 8.dp, bottom = 8.dp))
                    }
                }
                val parent = chosen
                if (naming && parent != null) {
                    OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true,
                        label = { Text("New folder in ${parent.name}") })
                    TextButton(onClick = {
                        making = true
                        scope.launch {
                            model.newFolder(parent, name)?.let { chosen = it; naming = false; name = "" }
                            making = false
                        }
                    }, enabled = name.isNotBlank() && !making) { Text(if (making) "Making it…" else "Make the folder") }
                } else {
                    TextButton(onClick = { naming = true }, enabled = parent != null) {
                        Text(if (parent == null) "+ New folder (choose where first)" else "+ New folder in ${parent.name}")
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = {
                val to = chosen ?: return@TextButton
                model.moving = null
                model.move(request.photos, to, request.then)
            }, enabled = chosen != null) { Text("Move") }
        },
        dismissButton = { TextButton(onClick = { model.moving = null }) { Text("Cancel") } },
    )
}
