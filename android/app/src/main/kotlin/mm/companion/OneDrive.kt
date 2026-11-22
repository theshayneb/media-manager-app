package mm.companion

import android.content.Context
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.LocalDateTime

/**
 * OneDrive through Microsoft Graph: sign-in with a code (no password in this app), finding the same photo as on
 * the phone in Pictures › Camera Roll, and changing it there so the PC gets the change through OneDrive.
 */
class OneDrive(private val context: Context) {
    private val prefs = context.getSharedPreferences("onedrive", Context.MODE_PRIVATE)

    var clientId: String
        get() = prefs.getString("client_id", null)?.takeIf { it.isNotBlank() } ?: BuildConfig.ONEDRIVE_CLIENT_ID
        set(value) = prefs.edit().putString("client_id", value.trim()).apply()

    val signedIn get() = prefs.getString("refresh", null) != null
    val account get() = prefs.getString("account", "") ?: ""

    fun signOut() = prefs.edit().remove("refresh").remove("access").remove("expires").remove("account").apply()

    // ---------------------------------------------------------------- sign-in (device code)
    data class DeviceCode(val userCode: String, val verificationUri: String, val deviceCode: String,
                          val interval: Int, val expiresAt: Long, val message: String)

    fun startSignIn(): DeviceCode {
        require(clientId.isNotBlank()) { "Enter the Microsoft app ID first (see Settings)." }
        val o = postForm("$LOGIN/devicecode", mapOf("client_id" to clientId, "scope" to SCOPE))
        val code = DeviceCode(o.getString("user_code"), o.getString("verification_uri"), o.getString("device_code"),
            o.optInt("interval", 5), System.currentTimeMillis() + o.optInt("expires_in", 900) * 1000L,
            o.optString("message"))
        // Kept, so the app still finishes signing in if Android closed it while you were in the browser.
        prefs.edit().putString("pending", JSONObject().put("user", code.userCode).put("uri", code.verificationUri)
            .put("device", code.deviceCode).put("interval", code.interval).put("expires", code.expiresAt).toString())
            .apply()
        return code
    }

    /** The sign-in code still waiting for you to enter it (if any). */
    fun pendingSignIn(): DeviceCode? = runCatching {
        val o = JSONObject(prefs.getString("pending", null) ?: return null)
        DeviceCode(o.getString("user"), o.getString("uri"), o.getString("device"), o.getInt("interval"),
            o.getLong("expires"), "")
    }.getOrNull()?.takeIf { System.currentTimeMillis() < it.expiresAt }

    fun cancelSignIn() = prefs.edit().remove("pending").apply()

    /** True once signed in; false while still waiting for you to enter the code. */
    fun finishSignIn(code: DeviceCode): Boolean {
        val o = try {
            postForm("$LOGIN/token", mapOf("grant_type" to "urn:ietf:params:oauth:grant-type:device_code",
                "client_id" to clientId, "device_code" to code.deviceCode))
        } catch (e: GraphError) {
            if (e.body.contains("authorization_pending") || e.body.contains("slow_down")) return false
            cancelSignIn()
            throw e
        }
        storeTokens(o)
        cancelSignIn()
        runCatching {
            val me = get("/me/drive")
            prefs.edit().putString("account", me.optJSONObject("owner")?.optJSONObject("user")?.optString("displayName") ?: "").apply()
        }
        return true
    }

    private fun storeTokens(o: JSONObject) {
        prefs.edit()
            .putString("access", o.getString("access_token"))
            .putString("refresh", o.optString("refresh_token", prefs.getString("refresh", null)))
            .putLong("expires", System.currentTimeMillis() + (o.optInt("expires_in", 3600) - 120) * 1000L)
            .apply()
    }

    private fun token(): String {
        val access = prefs.getString("access", null)
        if (access != null && System.currentTimeMillis() < prefs.getLong("expires", 0)) return access
        val refresh = prefs.getString("refresh", null) ?: throw IOException("Not signed in to OneDrive")
        storeTokens(postForm("$LOGIN/token", mapOf("grant_type" to "refresh_token", "client_id" to clientId,
            "refresh_token" to refresh, "scope" to SCOPE)))
        return prefs.getString("access", null)!!
    }

    // ---------------------------------------------------------------- finding the photo
    data class Item(val id: String, val name: String, val taken: String?, val size: Long)

    private fun item(o: JSONObject) = Item(o.getString("id"), o.getString("name"),
        o.optJSONObject("photo")?.optString("takenDateTime")?.takeIf { it.isNotEmpty() }, o.optLong("size"))

    fun itemById(id: String): Item? = try { item(get("/me/drive/items/$id?select=id,name,photo,size")) } catch (e: GraphError) {
        if (e.code == 404) null else throw e
    }

    /** A file at this path inside Camera Roll ("2026/11/PXL_….jpg"), or null if there's none. */
    private fun byPath(path: String): Item? = try {
        val o = get("/me/drive/special/cameraroll:/${path.split('/').joinToString("/") { enc(it) }}?select=id,name,photo,size,file")
        if (o.has("file")) item(o) else null
    } catch (e: GraphError) {
        if (e.code == 404) null else throw e
    }

    /** Files under Camera Roll (and its folders) whose names start like this. */
    private fun search(text: String): List<Item> {
        val q = text.replace("'", "''")
        val o = get("/me/drive/special/cameraroll/search(q='${enc(q)}')?select=id,name,photo,size,file&top=50")
        val arr = o.getJSONArray("value")
        return (0 until arr.length()).map { arr.getJSONObject(it) }.filter { it.has("file") }.map { item(it) }
    }

    /**
     * The OneDrive copy of a phone photo: by its name, by the name the camera gave it, or (if it was renamed on
     * the PC with the rename pattern) by the name its date taken gives, checked against the photo's date taken.
     */
    fun find(names: List<String>, taken: LocalDateTime?, patternNames: List<String>): Item? {
        // Straight to it by name first: in Camera Roll, or its year (and month) folders. OneDrive's search can be
        // hours or days behind new uploads, so photos that were there were still "waiting for camera upload".
        val folders = listOfNotNull("", taken?.let { "%04d/%02d".format(it.year, it.monthValue) },
            taken?.let { "%04d".format(it.year) })
        for (n in (names + patternNames).filter { it.isNotBlank() }.distinct()) {
            for (folder in folders) {
                byPath(if (folder.isEmpty()) n else "$folder/$n")?.let { return it }
            }
        }
        for (n in names.filter { it.isNotBlank() }.distinct()) {
            search(n.substringBeforeLast('.')).firstOrNull { it.name.equals(n, true) }?.let { return it }
        }
        if (taken == null) return null
        for (n in patternNames.distinct()) {
            val stem = n.substringBeforeLast('.')
            val found = search(stem).filter {
                it.name.substringBeforeLast('.').let { s -> s.equals(stem, true) || s.matches(Regex(Regex.escape(stem) + "_\\d+", RegexOption.IGNORE_CASE)) }
            }
            found.firstOrNull { sameTime(it.taken, taken) }?.let { return it }
            if (found.size == 1 && found[0].taken == null) return found[0]
        }
        return null
    }

    private fun sameTime(graph: String?, taken: LocalDateTime): Boolean {
        if (graph == null) return false
        val wall = runCatching { LocalDateTime.parse(graph.removeSuffix("Z").substringBefore('+').take(19)) }.getOrNull()
            ?: return false
        return kotlin.math.abs(java.time.Duration.between(wall, taken).seconds) <= 1
    }

    // ---------------------------------------------------------------- browsing Camera Roll
    /** A file or folder in OneDrive, as listed. */
    data class Entry(val id: String, val name: String, val folder: Boolean, val childCount: Int, val mime: String,
                     val taken: String?, val modified: String, val tag: String)

    private fun entry(o: JSONObject) = Entry(o.getString("id"), o.getString("name"), o.has("folder"),
        o.optJSONObject("folder")?.optInt("childCount") ?: 0, o.optJSONObject("file")?.optString("mimeType") ?: "",
        o.optJSONObject("photo")?.optString("takenDateTime")?.takeIf { it.isNotEmpty() },
        o.optString("lastModifiedDateTime"), o.optString("cTag", o.optString("eTag")))

    /** Camera Roll itself (its id and name). */
    fun cameraRoll(): Entry = entry(get("/me/drive/special/cameraroll?select=id,name,folder,lastModifiedDateTime,cTag"))

    /** Everything in a folder (all pages). */
    fun children(id: String): List<Entry> {
        val out = mutableListOf<Entry>()
        var url: String? = "$GRAPH/me/drive/items/$id/children?\$top=200&\$select=id,name,folder,file,photo,lastModifiedDateTime,cTag,eTag"
        while (url != null) {
            val o = JSONObject(String(request("GET", url, null, null).second))
            val arr = o.getJSONArray("value")
            for (k in 0 until arr.length()) out.add(entry(arr.getJSONObject(k)))
            url = o.optString("@odata.nextLink").takeIf { it.isNotEmpty() }
        }
        return out
    }

    /** OneDrive's own small picture of a photo (up to 800 px). */
    fun thumbnail(id: String): ByteArray = request("GET", "$GRAPH/me/drive/items/$id/thumbnails/0/large/content", null, null).second

    /** The first [n] bytes of a file (where its tags are), without downloading all of it. */
    fun head(id: String, n: Int): ByteArray {
        val conn = URL("$GRAPH/me/drive/items/$id/content").openConnection() as HttpURLConnection
        conn.setRequestProperty("Authorization", "Bearer ${token()}")
        conn.setRequestProperty("Range", "bytes=0-${n - 1}")
        conn.connectTimeout = 30_000
        conn.readTimeout = 60_000
        try {
            val code = conn.responseCode
            if (code !in 200..299) throw GraphError(code, conn.errorStream?.use { String(it.readBytes()) } ?: "")
            val out = ByteArrayOutputStream()
            val buf = ByteArray(16 * 1024)
            conn.inputStream.use { s ->
                while (out.size() < n) {
                    val r = s.read(buf, 0, minOf(buf.size, n - out.size()))
                    if (r < 0) break
                    out.write(buf, 0, r)
                }
            }
            return out.toByteArray()
        } finally {
            conn.disconnect()  // (if the range was ignored: stop the rest)
        }
    }

    // ---------------------------------------------------------------- changing it
    fun download(id: String): ByteArray = request("GET", "$GRAPH/me/drive/items/$id/content", null, null).second

    fun upload(id: String, bytes: ByteArray) {
        if (bytes.size < 4 * 1024 * 1024) {
            request("PUT", "$GRAPH/me/drive/items/$id/content", bytes, "application/octet-stream")
            return
        }
        val session = JSONObject(String(request("POST", "$GRAPH/me/drive/items/$id/createUploadSession",
            "{}".toByteArray(), "application/json").second))
        val url = session.getString("uploadUrl")
        val chunk = 320 * 1024 * 16
        var start = 0
        while (start < bytes.size) {
            val end = minOf(bytes.size, start + chunk)
            val conn = URL(url).openConnection() as HttpURLConnection
            conn.requestMethod = "PUT"
            conn.doOutput = true
            conn.setRequestProperty("Content-Range", "bytes $start-${end - 1}/${bytes.size}")
            conn.setFixedLengthStreamingMode(end - start)
            conn.outputStream.use { it.write(bytes, start, end - start) }
            val code = conn.responseCode
            if (code !in 200..299) throw GraphError(code, conn.errorStream?.readBytes()?.let { String(it) } ?: "")
            start = end
        }
    }

    /** Rename it there; adds _1, _2… if the name is taken. Returns the name it got. */
    fun rename(id: String, name: String): String {
        val stem = name.substringBeforeLast('.')
        val ext = name.substring(stem.length)
        var candidate = name
        for (n in 1..50) {
            try {
                request("PATCH", "$GRAPH/me/drive/items/$id", JSONObject().put("name", candidate).toString().toByteArray(),
                    "application/json")
                return candidate
            } catch (e: GraphError) {
                if (e.code != 409) throw e
                candidate = "${stem}_$n$ext"
            }
        }
        throw IOException("Couldn't rename to $name")
    }

    /** To OneDrive's recycle bin (it can be restored there). */
    fun delete(id: String) {
        try { request("DELETE", "$GRAPH/me/drive/items/$id", null, null) } catch (e: GraphError) { if (e.code != 404) throw e }
    }

    /** The Windows app's companion.json (keyword sets, rename pattern…) from OneDrive › Documents › Phone ›
     *  Media Manager (or OneDrive › Media Manager, where the PC put it before 0.6.1), or null. */
    fun companion(): String? {
        for (path in listOf("Documents/Phone/Media%20Manager/companion.json", "Media%20Manager/companion.json")) {
            try {
                return String(request("GET", "$GRAPH/me/drive/root:/$path:/content", null, null).second)
            } catch (e: GraphError) {
                if (e.code != 404) throw e
            }
        }
        return null
    }

    // ---------------------------------------------------------------- HTTP
    class GraphError(val code: Int, val body: String) : IOException("OneDrive said $code: ${body.take(200)}")

    private fun get(path: String) = JSONObject(String(request("GET", "$GRAPH$path", null, null).second))

    private fun request(method: String, url: String, body: ByteArray?, type: String?): Pair<Int, ByteArray> {
        if (method == "PATCH") return patch(url, body ?: ByteArray(0), type ?: "application/json")
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = method
        conn.setRequestProperty("Authorization", "Bearer ${token()}")
        conn.instanceFollowRedirects = true
        conn.connectTimeout = 30_000
        conn.readTimeout = 120_000
        if (body != null) {
            conn.doOutput = true
            type?.let { conn.setRequestProperty("Content-Type", it) }
            conn.setFixedLengthStreamingMode(body.size)
            conn.outputStream.use { it.write(body) }
        }
        val code = conn.responseCode
        val stream = if (code in 200..299) conn.inputStream else conn.errorStream
        val bytes = stream?.use { s -> ByteArrayOutputStream().also { s.copyTo(it) }.toByteArray() } ?: ByteArray(0)
        if (code !in 200..299) throw GraphError(code, String(bytes))
        return code to bytes
    }

    /** A real PATCH (OneDrive refuses a POST that says it's one: "Invalid request"). */
    private fun patch(url: String, body: ByteArray, type: String): Pair<Int, ByteArray> {
        val request = okhttp3.Request.Builder().url(url)
            .header("Authorization", "Bearer ${token()}")
            .patch(body.toRequestBody(type.toMediaType()))
            .build()
        http.newCall(request).execute().use { r ->
            val bytes = r.body?.bytes() ?: ByteArray(0)
            if (!r.isSuccessful) throw GraphError(r.code, String(bytes))
            return r.code to bytes
        }
    }

    private val http by lazy {
        okhttp3.OkHttpClient.Builder().connectTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
            .readTimeout(120, java.util.concurrent.TimeUnit.SECONDS).build()
    }

    private fun postForm(url: String, form: Map<String, String>): JSONObject {
        val conn = URL(url).openConnection() as HttpURLConnection
        conn.requestMethod = "POST"
        conn.doOutput = true
        conn.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        val body = form.entries.joinToString("&") { "${enc(it.key)}=${enc(it.value)}" }.toByteArray()
        conn.outputStream.use { it.write(body) }
        val code = conn.responseCode
        val text = (if (code in 200..299) conn.inputStream else conn.errorStream)?.use { String(it.readBytes()) } ?: ""
        if (code !in 200..299) throw GraphError(code, text)
        return JSONObject(text)
    }

    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8").replace("+", "%20")

    companion object {
        const val LOGIN = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
        const val GRAPH = "https://graph.microsoft.com/v1.0"
        const val SCOPE = "Files.ReadWrite offline_access"
    }
}
