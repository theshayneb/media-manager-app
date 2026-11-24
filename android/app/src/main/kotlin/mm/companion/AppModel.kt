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
import mm.core.applying
import mm.core.matchAny
import mm.core.renamePlan
import java.io.File
import java.time.LocalDateTime

enum class Screen { Grid, Details, Edit, Settings }

const val STEAM_REQUEST = "Documents/Phone/Media Manager/steam-request.json"
const val STEAM_RESULT = "Documents/Phone/Media Manager/steam-result.json"

class AppModel(app: Application) : AndroidViewModel(app) {
    val store = PhotoStore(app)
    val queue = SyncQueue(app)
    val drive = OneDrive(app)
    val cloud = CloudPhotos(app, drive)
    var shared by mutableStateOf(Shared(app))

    var screen by mutableStateOf(Screen.Grid)
    var folders by mutableStateOf(listOf<Folder>())
    var folder by mutableStateOf<Folder?>(null)
    var photos by mutableStateOf(listOf<Photo>())
    val fields = mutableStateMapOf<Long, XmpFields>()
    val selected = mutableStateMapOf<Long, Boolean>()
    var editing by mutableStateOf<Photo?>(null)
    var editTab by mutableStateOf(0)
    var editFull by mutableStateOf(false)  // the Edit view full screen (no sliders): kept from photo to photo
    var message by mutableStateOf("")
    var pending by mutableStateOf(0)
    var busy by mutableStateOf(false)
    /** Goes up after every change, so what's shown from the files (date taken, Rename's new names) is read again. */
    var changes by mutableStateOf(0)
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

    // ---------------------------------------------------------------- 📱 Phone or ☁ OneDrive
    /** Browsing OneDrive's Camera Roll (not the phone's folders). */
    var inCloud by mutableStateOf(false)
    var wifiOnly by mutableStateOf(cloud.wifiOnly)
    private var phoneFolder: Folder? = null
    private var cloudFolder: Folder? = null

    fun useCloud(on: Boolean) {
        if (on == inCloud) return
        if (on && !signedIn) { message = "Sign in to OneDrive first (⚙)"; return }
        if (on) phoneFolder = folder else cloudFolder = folder
        inCloud = on
        folder = if (on) cloudFolder else phoneFolder
        photos = emptyList()
        reload()
    }

    fun changeWifiOnly(on: Boolean) {
        cloud.wifiOnly = on
        wifiOnly = on
        Sync.schedule(app())
    }

    fun reload() = viewModelScope.launch {
        if (inCloud) {
            val online = cloud.online()
            val list = withContext(Dispatchers.IO) { runCatching { cloud.folders(online) } }
            list.exceptionOrNull()?.let { message = "OneDrive: ${it.message}" }
            folders = list.getOrDefault(emptyList())
            val keep = folder?.let { f -> folders.firstOrNull { it.id == f.id } }
            open(keep ?: folders.firstOrNull { it.name.equals("Camera Roll", true) } ?: folders.firstOrNull { it.count > 0 }
                ?: folders.firstOrNull())
            return@launch
        }
        found = withContext(Dispatchers.IO) { store.folders() }
        val list = arrange(found)
        folders = list
        val keep = folder?.let { f -> list.firstOrNull { it.id == f.id } }
        open(keep ?: list.firstOrNull { it.name.equals("Camera", true) } ?: list.firstOrNull())
    }

    /** ⟳: the folders and photos read again (phone or OneDrive), with fresh thumbnails and tags, and a sync. */
    fun refresh() {
        thumbs.evictAll()
        fields.clear()
        message = if (inCloud && !cloud.online()) "OneDrive: ${cloud.whyOffline()} (showing what was last seen)" else ""
        reload()
        syncNow()
    }

    /** OneDrive's list, with what's still waiting to be done there: renamed, and deleted ones gone. */
    private fun withQueued(list: List<Photo>, folderId: String = ""): List<Photo> {
        val waiting = queue.all().groupBy { it.photoId }
        return list.mapNotNull { p ->
            val es = waiting[p.id] ?: return@mapNotNull p
            if (es.any { it.change == Change.Delete }) return@mapNotNull null
            // moved to another folder (not done in OneDrive yet): not here any more
            (es.lastOrNull { it.change is Change.Move }?.change as Change.Move?)?.let {
                if (CloudPhotos.CLOUD + it.folderId != folderId) return@mapNotNull null
            }
            var q = p
            (es.lastOrNull { it.change is Change.Rename }?.change as Change.Rename?)?.let { q = q.copy(name = it.name) }
            if (!cloud.isLocal(p)) {  // (a downloaded copy already has its new date)
                (es.lastOrNull { it.change is Change.DateTaken }?.change as Change.DateTaken?)?.let { d ->
                    runCatching { LocalDateTime.parse(d.exif, EXIF_DATE) }.getOrNull()?.let {
                        q = q.copy(takenMillis = it.atZone(java.time.ZoneId.systemDefault()).toInstant().toEpochMilli())
                    }
                }
            }
            q
        }.sortedByDescending { if (it.takenMillis > 0) it.takenMillis else it.modified * 1000 }
    }

    /** The folder's photos read again, keeping what's selected (a date changed: it may be in another week now). */
    private fun relist() {
        val f = folder ?: return
        viewModelScope.launch {
            val list = listPhotos(f, quiet = true)
            if (folder?.id != f.id) return@launch
            photos = list
            editing?.let { e -> list.firstOrNull { it.id == e.id }?.let { editing = it } }
        }
    }

    private suspend fun listPhotos(f: Folder, quiet: Boolean = false): List<Photo> = withContext(Dispatchers.IO) {
        if (!f.inCloud) return@withContext store.photos(f.id)
        val online = cloud.online() && !quiet  // (quiet: as last listed, with the changes made here)
        val listed = runCatching { cloud.photos(f, online) }
            .recoverCatching { if (online) cloud.photos(f, false) else throw it }  // (as last seen)
        if (!quiet) listed.exceptionOrNull()?.let { withContext(Dispatchers.Main) { message = "OneDrive: ${it.message}" } }
        withQueued(listed.getOrDefault(emptyList()), f.id)
    }

    fun open(f: Folder?) {
        folder = f
        selected.clear()
        viewModelScope.launch {
            photos = if (f == null) emptyList() else listPhotos(f)
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
        viewModelScope.launch { withContext(Dispatchers.IO) { readFields(p, always = true) } }
    }

    /** Its tags into [fields]. A OneDrive photo not downloaded: the start of the file (on Wi-Fi, or when it's
     *  opened or selected), so scrolling on mobile data doesn't use much. */
    private fun readFields(p: Photo, always: Boolean) {
        if (!p.inCloud || cloud.isLocal(p)) { fields[p.id] = store.fields(p); return }
        if (!cloud.online() || !(always || cloud.unmetered())) return
        runCatching { cloud.fields(p) }.getOrNull()?.let { fields[p.id] = it }
    }

    suspend fun thumbnail(p: Photo): Bitmap? {
        thumbs.get(p.id)?.let { return it }
        return reading.withPermit {
            withContext(Dispatchers.IO) {
                if (p.id !in fields) readFields(p, always = false)
                val bmp = if (p.inCloud) runCatching { cloud.thumbnail(p, cloud.online()) }.getOrNull() else store.thumbnail(p)
                bmp?.also { thumbs.put(p.id, it) }
            }
        }
    }

    /** Weeks folded shut in the grid ("2026-46"), remembered between opens. */
    var collapsed by mutableStateOf(
        app.getSharedPreferences("grid", 0).getStringSet("collapsed", emptySet())!!.toSet())

    fun toggleWeek(key: String) {
        collapsed = if (key in collapsed) collapsed - key else collapsed + key
        app().getSharedPreferences("grid", 0).edit().putStringSet("collapsed", collapsed).apply()
    }

    /** Photos with a change not in OneDrive yet (the yellow dot). */
    var waitingIds by mutableStateOf(emptySet<Long>())

    /** A small picture for the Sync list, by the queued photo id (a phone photo, or a OneDrive one). */
    suspend fun queuedThumbnail(photoId: Long): Bitmap? = withContext(Dispatchers.IO) {
        thumbs.get(photoId)?.let { return@withContext it }
        if (photoId >= 0) {
            runCatching { app().contentResolver.loadThumbnail(
                android.content.ContentUris.withAppendedId(android.provider.MediaStore.Images.Media.EXTERNAL_CONTENT_URI, photoId),
                android.util.Size(160, 160), null) }.getOrNull()
        } else {
            app().getSharedPreferences("onedrive-items", 0).getString(photoId.toString(), null)?.let { cloud.anyThumbnail(it) }
        }
    }

    fun refreshPending() {
        val all = queue.all()
        pending = all.size
        waitingIds = all.map { it.photoId }.toSet()
    }

    val selection: List<Photo> get() = photos.filter { selected[it.id] == true }

    // ---------------------------------------------------------------- changes (phone now, OneDrive queued)
    private fun record(p: Photo, change: Change, name: String = p.name,
                       taken: String = store.dateTaken(p)?.format(EXIF_DATE) ?: "") {
        p.cloudId?.let { app().getSharedPreferences("onedrive-items", 0).edit().putString(p.id.toString(), it).apply() }
        queue.add(p.id, name, originalName(p), taken, change)
    }

    /** A OneDrive photo onto the phone (if it isn't yet and OneDrive can be used now); true if it's here. */
    private fun local(p: Photo): Boolean {
        if (!p.inCloud || cloud.isLocal(p)) return true
        if (!cloud.online()) return false
        cloud.fetch(p)
        return true
    }

    /** The photo's bytes for the Edit screen (a OneDrive photo is downloaded first). */
    suspend fun readForEdit(p: Photo): ByteArray = withContext(Dispatchers.IO) {
        if (!local(p)) throw java.io.IOException("Not downloaded yet. ${cloud.whyOffline()}.")
        store.read(p)
    }

    private fun originalName(p: Photo): String =
        app().getSharedPreferences("original-names", 0).getString(p.id.toString(), null) ?: p.name

    fun apply(change: Change, targets: List<Photo> = selection) {
        if (targets.isEmpty()) return
        busy = true
        viewModelScope.launch {
            var done = 0
            var queuedOnly = 0
            val problems = mutableListOf<String>()
            withContext(Dispatchers.IO) {
                for (p in targets) {
                    try {
                        if (change.isTag && !p.canChange) { problems.add("${p.name}: only JPG and PNG photos can be tagged"); continue }
                        val taken = store.dateTaken(p)?.format(EXIF_DATE) ?: ""
                        if (!local(p)) {
                            // A OneDrive photo with no connection: done there once online.
                            record(p, change, taken = taken); queuedOnly++; done++
                            fields[p.id]?.let { fields[p.id] = it.applying(change) }  // shown at once
                            continue
                        }
                        if (change.isTag) {
                            store.write(p, applyTags(store.read(p), change))
                            fields[p.id] = store.fields(p)
                        } else if (change is Change.DateTaken) {
                            store.setDateTaken(p, change.exif)
                        }
                        record(p, change, taken = taken)
                        done++
                    } catch (e: Exception) {
                        problems.add("${p.name}: ${e.message}")
                    }
                }
            }
            finish(done, problems)
            if (change is Change.DateTaken) relist()
            if (queuedOnly > 0) message += " · $queuedOnly will be done in OneDrive once online"
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
                        if (local(p)) store.setDateTaken(p, exif)
                        record(p, Change.DateTaken(exif))
                    } catch (e: Exception) { problems.add("${p.name}: ${e.message}") }
                }
            }
            finish(found.size - problems.size, problems, skipped = targets.size - found.size)
            relist()
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
                        if (!p.inCloud) store.rename(p, newName)  // (OneDrive's: shown renamed until it's done there)
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

    /** Deleting OneDrive photos: asked here (Android's Trash isn't theirs); they go to OneDrive's recycle bin. */
    class CloudDelete(val photos: List<Photo>, val then: (() -> Unit)?)
    var cloudDelete by mutableStateOf<CloudDelete?>(null)

    fun confirmCloudDelete(ok: Boolean) {
        val r = cloudDelete ?: return
        cloudDelete = null
        if (!ok) { message = "Not deleted"; return }
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                r.photos.forEach { p ->
                    record(p, Change.Delete, taken = store.dateTaken(p)?.format(EXIF_DATE) ?: "")
                    cloud.forget(p)
                    thumbs.remove(p.id)
                }
            }
            val gone = r.photos.map { it.id }.toSet()
            photos = photos.filterNot { it.id in gone }
            gone.forEach { selected.remove(it) }
            message = "Deleted ${gone.size} from OneDrive" + if (cloud.online()) "" else " (once online)"
            refreshPending()
            Sync.schedule(app())
            r.then?.invoke()
        }
    }

    fun delete(targets: List<Photo> = selection, then: (() -> Unit)? = null) {
        if (targets.isEmpty()) return
        if (targets.any { it.inCloud }) { cloudDelete = CloudDelete(targets, then); return }
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

    /** The Move picker, while it's open. */
    var moving by mutableStateOf<MoveRequest?>(null)

    /** Move OneDrive photos into another Pictures folder: gone from this one now, moved in OneDrive by the sync. */
    fun move(targets: List<Photo>, to: Folder, then: (() -> Unit)? = null) {
        val moving = targets.filter { it.inCloud }
        if (moving.isEmpty() || to.id == folder?.id) return
        viewModelScope.launch {
            withContext(Dispatchers.IO) {
                moving.forEach { record(it, Change.Move(to.id.removePrefix(CloudPhotos.CLOUD), to.name)) }
            }
            val gone = moving.map { it.id }.toSet()
            photos = photos.filterNot { it.id in gone }
            gone.forEach { selected.remove(it) }
            message = "Moved ${moving.size} to ${to.name}" + if (cloud.online()) "" else " (in OneDrive once online)"
            refreshPending()
            Sync.schedule(app())
            then?.invoke()
        }
    }

    /** A new folder in OneDrive (needs a connection now); the folder list is read again. Returns it, or null. */
    suspend fun newFolder(parent: Folder, name: String): Folder? {
        if (!cloud.online()) { message = "A new folder needs a connection: ${cloud.whyOffline()}"; return null }
        val made = withContext(Dispatchers.IO) { runCatching { cloud.newFolder(parent, name.trim()) } }
        val id = made.getOrElse { message = "Couldn't make the folder: ${it.message}"; return null }
        val list = withContext(Dispatchers.IO) { runCatching { cloud.folders(true) }.getOrNull() }
        if (list != null) folders = list
        return folders.firstOrNull { it.id == CloudPhotos.CLOUD + id }
            ?: Folder(CloudPhotos.CLOUD + id, name.trim(), 0, "${parent.path}/${name.trim()}", parent.depth + 1)
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
                    if (!local(p)) throw java.io.IOException("Not downloaded yet. ${cloud.whyOffline()}.")
                    val bytes = store.read(p)
                    val rawCrop = uprightCrop?.let { cropToRaw(it, orientationOf(bytes)) }
                    val edited = editImage(bytes, adjustments, rawCrop, turn)
                    if (!p.inCloud) store.keepOriginalInTrash(p, bytes)  // (OneDrive keeps the earlier version)
                    store.write(p, edited)
                    fields[p.id] = store.fields(p)
                    thumbs.remove(p.id)
                    record(p, Change.Edit(adjustments.toMap(), rawCrop, if (turn.unchanged) null else turn.toList()))
                }
                if (!adjustments.unchanged) {  // "Same as last edit": the sliders (a rotate/flip is for this photo only)
                    lastEdit = adjustments.toMap()
                    app().getSharedPreferences("edit", 0).edit().putString("last", org.json.JSONObject(lastEdit as Map<*, *>).toString()).apply()
                }
                message = if (p.inCloud) "Saved. OneDrive keeps the earlier version." else "Saved. The original is in the Trash."
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
        changes++
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

    // ---------------------------------------------------------------- Steam screenshots, imported by the PC
    /** What the PC said about the last import asked from here (steam-result.json), and the request waiting. */
    data class SteamState(val asked: String = "", val askedAt: Long = 0, val result: org.json.JSONObject? = null)
    var steam by mutableStateOf(SteamState(
        app.getSharedPreferences("steam", 0).getString("asked", "") ?: "",
        app.getSharedPreferences("steam", 0).getLong("asked_at", 0)))
    private var steamJob: Job? = null

    /** Leave a request in OneDrive for the PC (Media Manager looks every minute), then watch for its answer. */
    fun importSteam() {
        val id = java.util.UUID.randomUUID().toString()
        viewModelScope.launch {
            val ok = withContext(Dispatchers.IO) {
                runCatching { drive.writeText(STEAM_REQUEST, org.json.JSONObject().put("id", id)
                    .put("asked", java.time.LocalDateTime.now().toString()).toString()) }
            }
            if (ok.isFailure) { message = "Couldn't ask your PC: ${ok.exceptionOrNull()?.message}"; return@launch }
            val now = System.currentTimeMillis()
            app().getSharedPreferences("steam", 0).edit().putString("asked", id).putLong("asked_at", now).apply()
            steam = steam.copy(asked = id, askedAt = now)
            watchSteam()
        }
    }

    /** Read the PC's answer now, and keep reading every 20 s while it's still to come (up to 15 minutes). */
    fun watchSteam() {
        steamJob?.cancel()
        steamJob = viewModelScope.launch {
            val until = System.currentTimeMillis() + 15 * 60_000
            while (true) {
                val o = withContext(Dispatchers.IO) {
                    runCatching { drive.readText(STEAM_RESULT)?.let { org.json.JSONObject(it) } }.getOrNull()
                }
                if (o != null) steam = steam.copy(result = o)
                val answered = o != null && o.optString("id") == steam.asked && o.optString("state") != "running"
                if (steam.asked.isEmpty() || answered || System.currentTimeMillis() > until) break
                delay(20_000)
            }
        }
    }

    private fun parseLast(text: String): Map<String, Int> = runCatching {
        val o = org.json.JSONObject(text)
        o.keys().asSequence().associateWith { o.getInt(it) }
    }.getOrDefault(emptyMap())

    fun dateTaken(p: Photo): LocalDateTime? = store.dateTaken(p)

    fun cacheFile(name: String) = File(app().cacheDir, name)
}
