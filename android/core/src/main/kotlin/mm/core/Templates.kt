package mm.core

import java.time.LocalDateTime
import java.time.ZoneId
import java.time.ZoneOffset

/**
 * Photo Manager's filename templates (photo_manager/core/templates.py) and rename patterns
 * (photo_manager/core/dates.py format_pattern), so both apps read and write the same names.
 *
 * {YYYY} {YY} {MM} {M} {DD} {D} {HH} {H} {hh} {h} {mm} {ss} {fff} {AMPM}; * any text, ? one character,
 * # one digit. {MM} is month, {mm} minute.
 */
class TemplateError(message: String) : IllegalArgumentException(message)

private val TOKENS = mapOf(
    "YYYY" to "(?<Y>\\d{4})", "YY" to "(?<y>\\d{2})", "MM" to "(?<M>\\d{2})", "M" to "(?<M>\\d{1,2})",
    "DD" to "(?<D>\\d{2})", "D" to "(?<D>\\d{1,2})", "HH" to "(?<H>\\d{2})", "H" to "(?<H>\\d{1,2})",
    "hh" to "(?<h>\\d{2})", "h" to "(?<h>\\d{1,2})", "mm" to "(?<m>\\d{2})", "ss" to "(?<s>\\d{2})",
    "fff" to "(?<f>\\d+)", "AMPM" to "(?<p>[AP]M)",
)
private val PIECE = Regex("""\{(\w+)\}|(\*)|(\?)|(#)|([^{*?#]+|\{)""")

fun compilePattern(pattern: String): Regex {
    if (pattern.isBlank()) throw TemplateError("The pattern is empty.")
    val parts = StringBuilder()
    val used = mutableSetOf<String>()
    for (m in PIECE.findAll(pattern)) {
        val (token, star, question, hash, literal) = m.destructured
        when {
            token.isNotEmpty() -> {
                val re = TOKENS[token] ?: throw TemplateError("Unknown placeholder {$token}.")
                val group = re.substringAfter("(?<").substringBefore(">")
                if (!used.add(group)) throw TemplateError("Each placeholder can only be used once.")
                parts.append(re)
            }
            star.isNotEmpty() -> parts.append(".*?")
            question.isNotEmpty() -> parts.append(".")
            hash.isNotEmpty() -> parts.append("\\d")
            else -> parts.append(Regex.escape(literal))
        }
    }
    if ("Y" !in used && "y" !in used) throw TemplateError("The pattern needs a year: {YYYY} or {YY}.")
    if ("M" !in used || "D" !in used) throw TemplateError("The pattern needs a month {MM} and a day {DD}.")
    return Regex(parts.toString(), RegexOption.IGNORE_CASE)
}

private fun Regex.groupNames(): Set<String> =
    listOf("Y", "y", "M", "D", "H", "h", "m", "s", "f", "p").filter { "(?<$it>" in pattern }.toSet()

data class FilenameTemplate(val name: String, val pattern: String, val utc: Boolean = false) {
    fun match(filename: String): LocalDateTime? {
        val regex = try { compilePattern(pattern) } catch (e: TemplateError) { return null }
        val found = regex.find(filename) ?: return null
        if (found.range.first != 0) return null
        val names = regex.groupNames()
        fun g(n: String): String? = if (n in names) found.groups[n]?.value else null
        val dt = try {
            val year = g("Y")?.toInt() ?: (2000 + (g("y")?.toInt() ?: 0))
            val hour = g("h")?.let {
                val h = it.toInt()
                if (h !in 1..12) return null
                val p = g("p")
                if (p != null) h % 12 + (if (p.uppercase() == "PM") 12 else 0) else h
            } ?: (g("H")?.toInt() ?: 0)
            LocalDateTime.of(year, g("M")!!.toInt(), g("D")!!.toInt(), hour, g("m")?.toInt() ?: 0, g("s")?.toInt() ?: 0)
        } catch (e: Exception) {
            return null
        }
        if (!utc) return dt
        return dt.atOffset(ZoneOffset.UTC).atZoneSameInstant(ZoneId.systemDefault()).toLocalDateTime()
    }
}

/** Photo Manager's DEFAULT_TEMPLATES, in the same order (the first that matches wins). */
val DEFAULT_TEMPLATES = listOf(
    FilenameTemplate("Pixel (PXL_, UTC time)", "PXL_{YYYY}{MM}{DD}_{HH}{mm}{ss}{fff}", utc = true),
    FilenameTemplate("Phone photo (IMG_)", "IMG_{YYYY}{MM}{DD}_{HH}{mm}{ss}"),
    FilenameTemplate("Phone video (VID_)", "VID_{YYYY}{MM}{DD}_{HH}{mm}{ss}"),
    FilenameTemplate("Screenshot", "Screenshot_{YYYY}{MM}{DD}-{HH}{mm}{ss}"),
    FilenameTemplate("Renamed by this app (08-15-2026 11-42-44 AM)", "{MM}-{DD}-{YYYY} {hh}-{mm}-{ss} {AMPM}"),
    FilenameTemplate("Already renamed", "{YYYY}-{MM}-{DD}_{HH}-{mm}-{ss}"),
    FilenameTemplate("Digits only (YYYYMMDDHHMMSS)", "{YYYY}{MM}{DD}{HH}{mm}{ss}"),
    FilenameTemplate("Number_YYYYMMDDHHMMSS (e.g. 4981570_20261105132923_1)", "*_{YYYY}{MM}{DD}{HH}{mm}{ss}"),
    FilenameTemplate("Anything with YYYYMMDD_HHMMSS", "*{YYYY}{MM}{DD}?{HH}{mm}{ss}"),
)

fun matchAny(templates: List<FilenameTemplate>, filename: String): Pair<FilenameTemplate, LocalDateTime>? {
    for (t in templates) {
        val dt = t.match(filename)
        if (dt != null) return t to dt
    }
    return null
}

const val DEFAULT_RENAME_PATTERN = "{MM}-{DD}-{YYYY} {hh}-{mm}-{ss} {AMPM}"
private val INVALID_NAME_CHARS = Regex("""[<>:"/\\|?*\x00-\x1f]""")

/** Fill a rename pattern; {name} is the current name without its extension. */
fun formatPattern(pattern: String, dt: LocalDateTime, name: String = ""): String {
    val values = mapOf(
        "YYYY" to "%04d".format(dt.year), "YY" to "%02d".format(dt.year % 100),
        "MM" to "%02d".format(dt.monthValue), "DD" to "%02d".format(dt.dayOfMonth),
        "HH" to "%02d".format(dt.hour), "hh" to "%02d".format(if (dt.hour % 12 == 0) 12 else dt.hour % 12),
        "mm" to "%02d".format(dt.minute), "ss" to "%02d".format(dt.second),
        "AMPM" to if (dt.hour < 12) "AM" else "PM", "name" to name,
    )
    val filled = Regex("""\{(\w+)\}""").replace(pattern) { values[it.groupValues[1]] ?: it.value }
    return INVALID_NAME_CHARS.replace(filled, "-").trim().trimEnd('.')
}

/** "IMG_1.jpg" -> ("IMG_1", ".jpg"). */
fun splitName(filename: String): Pair<String, String> {
    val dot = filename.lastIndexOf('.')
    return if (dot > 0) filename.substring(0, dot) to filename.substring(dot) else filename to ""
}

/** The new names for photos taken at these times, with "_1", "_2" added where two would be the same
 *  (or a name is already taken), as Photo Manager does. */
fun renamePlan(items: List<Triple<String, LocalDateTime?, String>>, pattern: String, taken: Set<String>):
    List<String?> {
    val used = taken.map { it.lowercase() }.toMutableSet()
    return items.map { (current, dt, _) ->
        if (dt == null) return@map null
        val (stem, ext) = splitName(current)
        val base = formatPattern(pattern, dt, stem)
        if (base.isEmpty()) return@map null
        var candidate = base + ext
        if (candidate.equals(current, ignoreCase = true)) {
            used.add(candidate.lowercase())
            return@map null // already named that way
        }
        var n = 1
        while (candidate.lowercase() in used) {
            candidate = "${base}_$n$ext"
            n++
        }
        used.add(candidate.lowercase())
        candidate
    }
}
