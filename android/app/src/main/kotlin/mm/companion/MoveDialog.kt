package mm.companion

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
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
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
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

/** "Move N photos to": Pictures › 2026 and 2027 and the folders inside them (▸ opens a folder's folders;
 *  only their names are read, nothing in them is downloaded); + New folder inside the one chosen. */
@Composable
fun MoveDialog(model: AppModel, request: MoveRequest) {
    var roots by remember { mutableStateOf<List<Folder>?>(null) }
    val inside = remember { mutableStateMapOf<String, List<Folder>>() }   // folders opened with ▸
    val opening = remember { mutableStateMapOf<String, Boolean>() }
    var chosen by remember { mutableStateOf<Folder?>(null) }
    var naming by remember { mutableStateOf(false) }
    var name by remember { mutableStateOf("") }
    var making by remember { mutableStateOf(false) }
    val scope = rememberCoroutineScope()
    val n = request.photos.size
    LaunchedEffect(Unit) { roots = model.moveRoots() }

    fun shown(): List<Folder> {
        val out = mutableListOf<Folder>()
        fun add(f: Folder) { out.add(f); inside[f.id]?.forEach { add(it) } }
        roots?.forEach { add(it) }
        return out
    }

    fun toggle(f: Folder) {
        if (f.id in inside) { inside.remove(f.id); return }
        opening[f.id] = true
        scope.launch {
            val subs = model.subfolders(f)
            if (subs == null) model.message = "Opening a folder needs a connection" else inside[f.id] = subs
            opening.remove(f.id)
        }
    }

    AlertDialog(
        onDismissRequest = { model.moving = null },
        title = { Text(if (n == 1) "Move to" else "Move $n photos to") },
        text = {
            Column {
                val list = shown()
                if (roots == null) Text("Reading your folders…", color = Dim)
                else if (list.isEmpty()) Text("No 2026 or 2027 folder in OneDrive's Pictures.", color = Dim)
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = 380.dp), rememberLazyListState()) {
                    items(list, key = { it.id }) { f ->
                        val on = chosen?.id == f.id
                        Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).background(if (on) Accent else Color.Transparent)
                            .clickable { chosen = f }.padding(start = (4 + f.depth * 16).dp, end = 10.dp),
                            verticalAlignment = Alignment.CenterVertically) {
                            Text(if (opening[f.id] == true) "…" else if (f.id in inside) "▾" else "▸", fontSize = 15.sp, color = Dim,
                                modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable { toggle(f) }.padding(horizontal = 8.dp, vertical = 8.dp))
                            Text(f.name, fontSize = 15.sp, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color.White,
                                fontWeight = if (on) FontWeight.SemiBold else FontWeight.Normal)
                        }
                    }
                }
                val parent = chosen
                if (naming && parent != null) {
                    OutlinedTextField(name, { name = it }, Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true,
                        label = { Text("New folder in ${parent.name}") })
                    TextButton(onClick = {
                        making = true
                        scope.launch {
                            model.newFolder(parent, name)?.let { made ->
                                inside[parent.id] = ((inside[parent.id] ?: model.subfolders(parent) ?: emptyList())
                                    .filterNot { it.id == made.id } + made).sortedBy { it.name.lowercase() }
                                chosen = made; naming = false; name = ""
                            }
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
