package mm.companion

import android.app.Application
import android.graphics.Bitmap
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import mm.core.Adjustments
import mm.core.Change
import mm.core.XmpFields
import mm.core.applyTags
import mm.core.matchAny
import mm.core.renamePlan
import java.io.File
import java.time.LocalDateTime

enum class Screen { Grid, Details, Edit, Settings }

class AppModel(app: Application) : AndroidViewModel(app) {
    val store = PhotoStore(app)
    val queue = SyncQueue(app)
    val drive = OneDrive(app)
    var shared by mutableStateOf(Shared(app))

    var screen by mutableStateOf(Screen.Grid)
    var folders by mutableStateOf(listOf<Folder>())
    var folder by mutableStateOf<Folder?>(null)
    var photos by mutableStateOf(listOf<Photo>())
    val fields = mutableStateMapOf<Long, XmpFields>()
    val selected = mutableStateMapOf<Long, Boolean>()
    var editing by mutableStateOf<Photo?>(null)
    var editTab by mutableStateOf(0)  // the Edit screen's tab: Light, Detail, Colour, Tags (kept when swiping)
    var message by mutableStateOf("")
    var pending by mutableStateOf(0)
    var busy by mutableStateOf(false)
    var lastEdit by mutableStateOf<Map<String, Int>>(emptyMap())

    private val thumbs = object : android.util.LruCache<Long, Bitmap>(64 * 1024 * 1024) {
        override fun sizeOf(key: Long, value: Bitmap) = value.byteCount
    }
    private val reading = Semaphore(4)

    fun start() {
        lastEdit = app().getSharedPreferences("edit", 0).getString("last", null)?.let { parseLast(it) }
            ?: shared.lastEdit
        reload()
        Sync.schedule(app())
        refreshPending()
    }

    private fun app() = getApplication<Application>()

    // ---------------------------------------------------------------- OneDrive sign-in
    // Here (not in the Settings screen) so it keeps waiting while you're in the browser entering the code,
    // even if Android rebuilds the screen meanwhile; and checked again the moment you come back.
    var signedIn by mutableStateOf(drive.signedIn)
    var signInCode by mutableStateOf(drive.pendingSignIn())
    var signInProblem by mutableStateOf("")
    private var signInJob: Job? = null

    init { if (signInCode != null) checkSignIn() }

    fun startSignIn() {
        signInProblem = ""
        viewModelScope.launch {
            try {
                signInCode = withContext(Dispatchers.IO) { drive.startSignIn() }
                checkSignIn()
            } catch (e: OneDrive.GraphError) {
                signInProblem = e.message ?: "Couldn't start sign-in"
            } catch (e: Exception) {
                signInProblem = "Couldn't reach Microsoft (is the phone online?): ${e.message}"
            }
        }
    }

    /** Ask Microsoft now whether the code has been entered, then keep asking until it has (or runs out). */
    fun checkSignIn() {
        val c = signInCode ?: return
        signInJob?.cancel()
        signInJob = viewModelScope.launch {
            while (System.currentTimeMillis() < c.expiresAt) {
                val done = withContext(Dispatchers.IO) { runCatching { drive.finishSignIn(c) } }
                val error = done.exceptionOrNull()
                if (error != null && error !is OneDrive.GraphError) {
                    // No connection for a moment (Android often cuts it off while the app is in the background,
                    // e.g. while you're in the browser): keep waiting and try again.
                    signInProblem = "No internet connection right now; still waiting…"
                    delay(c.interval * 1000L)
                    continue
                }
                signInProblem = ""
                if (done.isFailure) {
                    signInProblem = done.exceptionOrNull()?.message ?: "Sign-in failed"
                    signInCode = null
                    return@launch
                }
                if (done.getOrDefault(false)) {
                    signedIn = true
                    signInCode = null
                    syncNow()
                    return@launch
                }
                delay(c.interval * 1000L)
            }
            drive.cancelSignIn()
            signInCode = null
            signInProblem = "The code ran out; try again."
        }
    }

    fun signOut() {
        drive.signOut()
        signedIn = false
    }

    // ---------------------------------------------------------------- folders (favourites first)
    /** Favourite folders' paths, in the order they were made favourites. */
    var favorites by mutableStateOf(loadFavorites())
    private var found = listOf<Folder>()

    private fun loadFavorites(): List<String> = runCatching {
        val a = org.json.JSONArray(app().getSharedPreferences("folders", 0).getString("favorites", "[]"))
        (0 until a.length()).map { a.getString(it) }
    }.getOrDefault(emptyList())

    fun isFavorite(f: Folder) = favorites.any { it.equals(f.path, ignoreCase = true) }

    fun toggleFavorite(f: Folder) {
        if (f.path.isEmpty()) return
        favorites = if (isFavorite(f)) favorites.filterNot { it.equals(f.path, ignoreCase = true) } else favorites + f.path
        app().getSharedPreferences("folders", 0).edit()
            .putString("favorites", org.json.JSONArray(favorites).toString()).apply()
        folders = arrange(found)
    }

    /** Favourites at the top (also when empty), then the rest as Android lists them (most recent first). */
    private fun arrange(list: List<Folder>): List<Folder> {
        val favs = favorites.map { path -> list.firstOrNull { it.path.equals(path, true) } ?: store.emptyFolder(path) }
        return favs + list.filterNot { f -> favorites.any { it.equals(f.path, true) } }
    }

    fun reload() = viewModelScope.launch {
        found = withContext(Dispatchers.IO) { store.folders() }
        val list = arrange(found)
        folders = list
        val keep = folder?.let { f -> list.firstOrNull { it.id == f.id } }
        open(keep ?: list.firstOrNull { it.name.equals("Camera", true) } ?: list.firstOrNull())
    }

    fun open(f: Folder?) {
        folder = f
        selected.clear()
        viewModelScope.launch {
            photos = if (f == null) emptyList() else withContext(Dispatchers.IO) { store.photos(f.id) }
            // Editing a photo that was just renamed (its Tags tab): the same photo, its new name and path.
            val e = editing
            if (screen == Screen.Edit && e != null) {
                photos.firstOrNull { it.id == e.id }?.let { editing = it; if (editTab == 3) selected[it.id] = true }
            }
        }
    }

    /** A photo's tags read now (if the grid hasn't yet). */
    fun loadFields(p: Photo) {
        if (p.id in fields) return
        viewModelScope.launch { fields[p.id] = withContext(Dispatchers.IO) { store.fields(p) } }
    }

    suspend fun thumbnail(p: Photo): Bitmap? {
        thumbs.get(p.id)?.let { return it }
        return reading.withPermit {
            withContext(Dispatchers.IO) {
                if (p.id !in fields) fields[p.id] = store.fields(p)
                store.thumbnail(p)?.also { thumbs.put(p.id, it) }
            }
        }
    }

    fun refreshPending() { pending = queue.all().size }

    val selection: List<Photo> get() = photos.filter { selected[it.id] == true }

    // ---------------------------------------------------------------- changes (phone now, OneDrive queued)
    private fun record(p: Photo, change: Change, name: String = p.name,
                       taken: String = store.dateTaken(p)?.format(EXIF_DATE) ?: "") {
        queue.add(p.id, name, originalName(p), taken, change)
    }

    private fun originalName(p: Photo): String =
        app().getSharedPreferences("original-names", 0).getString(p.id.toString(), null) ?: p.name

    fun apply(change: Change, targets: List<Photo> = selection) {
        if (targets.isEmpty()) return
        busy = true
        viewModelScope.launch {
            var done = 0
            val problems = mutableListOf<String>()
            withContext(Dispatchers.IO) {
                for (p in targets) {
                    try {
                        if (change.isTag) {
                            if (!p.canChange) { problems.add("${p.name}: only JPG and PNG photos can be tagged"); continue }
                            store.write(p, applyTags(store.read(p), change))
                            fields[p.id] = store.fields(p)
                        } else if (change is Change.DateTaken) {
                            store.setDateTaken(p, change.exif)
                        }
                        record(p, change)
                        done++
                    } catch (e: Exception) {
                        problems.add("${p.name}: ${e.message}")
                    }
                }
            }
            finish(done, problems)
        }
    }

    /** Date taken from each photo's file name (the Windows app's "From filename: Auto"). */
    fun datesFromNames(targets: List<Photo> = selection) {
        val templates = shared.templates
        val found = targets.mapNotNull { p -> matchAny(templates, p.name)?.let { p to it.second } }
        if (found.isEmpty()) { message = "No date found in those file names"; return }
        busy = true
        viewModelScope.launch {
            val problems = mutableListOf<String>()
            withContext(Dispatchers.IO) {
                for ((p, dt) in found) {
                    try {
                        val exif = dt.format(EXIF_DATE)
                        store.setDateTaken(p, exif)
                        record(p, Change.DateTaken(exif))
                    } catch (e: Exception) { problems.add("${p.name}: ${e.message}") }
                }
            }
            finish(found.size - problems.size, problems, skipped = targets.size - found.size)
        }
    }

    fun renamePreview(targets: List<Photo> = selection): List<Pair<Photo, String?>> {
        val items = targets.map { Triple(it.name, store.dateTaken(it), "") }
        val others = photos.filter { selected[it.id] != true }.map { it.name }.toSet()
        return targets.zip(renamePlan(items, shared.renamePattern, others))
    }

    fun rename(targets: List<Photo> = selection) {
        busy = true
        viewModelScope.launch {
            val problems = mutableListOf<String>()
            var done = 0
            withContext(Dispatchers.IO) {
                for ((p, newName) in renamePreview(targets)) {
                    if (newName == null) continue
                    try {
                        val prefs = app().getSharedPreferences("original-names", 0)
                        if (!prefs.contains(p.id.toString())) prefs.edit().putString(p.id.toString(), p.name).apply()
                        record(p, Change.Rename(newName))  // queued with the old name (to find it in OneDrive)
                        store.rename(p, newName)
                        done++
                    } catch (e: Exception) { problems.add("${p.name}: ${e.message}") }
                }
            }
            open(folder)
            finish(done, problems)
        }
    }

    /** Delete asks Android (its own "Move to Trash?" question), so it works on every phone and the photos can
     *  be restored from the Trash for 30 days. */
    class TrashRequest(val sender: android.content.IntentSender, val photos: List<Photo>, val taken: List<String>)
    var trashRequest by mutableStateOf<TrashRequest?>(null)

    /** After a delete Android said yes to (the Edit screen: on to the next photo). */
    private var afterTrash: (() -> Unit)? = null

    /** The photo delta places on in the folder (that can be edited), or null at either end. */
    fun neighbour(p: Photo, delta: Int): Photo? {
        val list = photos.filter { it.canChange }
        val i = list.indexOfFirst { it.id == p.id }
        return if (i < 0) null else list.getOrNull(i + delta)
    }

    fun delete(targets: List<Photo> = selection, then: (() -> Unit)? = null) {
        if (targets.isEmpty()) return
        afterTrash = then
        try {
            val request = android.provider.MediaStore.createTrashRequest(app().contentResolver, targets.map { it.uri }, true)
            trashRequest = TrashRequest(request.intentSender, targets,
                targets.map { store.dateTaken(it)?.format(EXIF_DATE) ?: "" })
        } catch (e: Exception) {
            message = "Couldn't delete: ${e.message}"
        }
    }

    /** Android's answer to the Trash question. */
    fun trashed(ok: Boolean) {
        val r = trashRequest ?: return
        trashRequest = null
        if (!ok) { message = "Not deleted"; afterTrash = null; return }
        viewModelScope.launch {
            val gone = withContext(Dispatchers.IO) {
                r.photos.indices.filter { !File(r.photos[it].path).exists() }.onEach { i ->
                    record(r.photos[i], Change.Delete, taken = r.taken[i])  // the OneDrive copy too, if it's there
                }
            }
            message = if (gone.size == r.photos.size) "Sent ${gone.size} to the Trash"
                else "Sent ${gone.size} of ${r.photos.size} to the Trash"
            open(folder)
            refreshPending()
            Sync.schedule(app())
            if (gone.isNotEmpty()) afterTrash?.invoke()
            afterTrash = null
        }
    }

    /** Forget every change still waiting for OneDrive (the phone's photos keep them). */
    fun clearQueue() {
        Sync.stop(app())  // a sync running now mustn't write them back
        queue.clear()
        refreshPending()
        message = "The list is cleared."
    }

    /** Save an edit: the phone's photo now (its original to the Trash), the OneDrive copy queued. */
    fun saveEdit(p: Photo, adjustments: Adjustments, uprightCrop: List<Double>?, turn: mm.core.Turn = mm.core.Turn(),
                 then: () -> Unit) {
        busy = true
        viewModelScope.launch {
            try {
                withContext(Dispatchers.Default) {
                    val bytes = store.read(p)
                    val rawCrop = uprightCrop?.let { cropToRaw(it, orientationOf(bytes)) }
                    val edited = editImage(bytes, adjustments, rawCrop, turn)
                    store.keepOriginalInTrash(p, bytes)
                    store.write(p, edited)
                    fields[p.id] = store.fields(p)
                    thumbs.remove(p.id)
                    record(p, Change.Edit(adjustments.toMap(), rawCrop, if (turn.unchanged) null else turn.toList()))
                }
                if (!adjustments.unchanged) {  // "Same as last edit": the sliders (a rotate/flip is for this photo only)
                    lastEdit = adjustments.toMap()
                    app().getSharedPreferences("edit", 0).edit().putString("last", org.json.JSONObject(lastEdit as Map<*, *>).toString()).apply()
                }
                message = "Saved. The original is in the Trash."
                then()
            } catch (e: OutOfMemoryError) {
                message = "This photo is too big to edit on this phone"
            } catch (e: Exception) {
                message = "Not saved: ${e.message}"
            } finally {
                busy = false
                refreshPending()
                Sync.schedule(app())
            }
        }
    }

    private fun finish(done: Int, problems: List<String>, skipped: Int = 0) {
        busy = false
        refreshPending()
        Sync.schedule(app())
        message = buildString {
            append("Done: $done photo${if (done == 1) "" else "s"}")
            if (skipped > 0) append(" · $skipped without a date in the name")
            if (problems.isNotEmpty()) append(" · ${problems.size} not changed (${problems.first()})")
        }
    }

    fun syncNow() {
        viewModelScope.launch {
            withContext(Dispatchers.IO) { runCatching { drive.companion()?.let { Shared(app()).save(it) } } }
            shared = Shared(app())
            Sync.schedule(app())
            refreshPending()
        }
    }

    private fun parseLast(text: String): Map<String, Int> = runCatching {
        val o = org.json.JSONObject(text)
        o.keys().asSequence().associateWith { o.getInt(it) }
    }.getOrDefault(emptyMap())

    fun dateTaken(p: Photo): LocalDateTime? = store.dateTaken(p)

    fun cacheFile(name: String) = File(app().cacheDir, name)
}
