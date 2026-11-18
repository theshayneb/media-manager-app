package mm.core

import org.w3c.dom.Document
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.StringReader
import java.io.StringWriter
import javax.xml.parsers.DocumentBuilderFactory
import javax.xml.transform.OutputKeys
import javax.xml.transform.TransformerFactory
import javax.xml.transform.dom.DOMSource
import javax.xml.transform.stream.StreamResult
import org.xml.sax.InputSource

/**
 * The XMP fields the Windows app uses (photo_manager/core/metadata.py), read and written in an XMP packet:
 * keywords = dc:subject (a Bag), colour label = xmp:Label, Star = xmp:Rating 5, Bookmark = xmpDM:good True,
 * and the ✨ mark = photoshop:History "Media Manager edit". Everything else in the packet is kept.
 */
object Ns {
    const val RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    const val X = "adobe:ns:meta/"
    const val DC = "http://purl.org/dc/elements/1.1/"
    const val XMP = "http://ns.adobe.com/xap/1.0/"
    const val XMP_DM = "http://ns.adobe.com/xmp/1.0/DynamicMedia/"
    const val PHOTOSHOP = "http://ns.adobe.com/photoshop/1.0/"
}

const val EDITED_MARK = "Media Manager edit"
val LABELS = listOf("Red", "Yellow", "Green", "Blue", "Purple")

data class XmpFields(
    val keywords: List<String> = emptyList(),
    val label: String = "",
    val rating: Int = 0,
    val bookmarked: Boolean = false,
    val history: String = "",
) {
    val starred get() = rating > 0
    val edited get() = history.startsWith(EDITED_MARK)
}

class Xmp private constructor(private val doc: Document) {
    companion object {
        private val EMPTY = """<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="${Ns.RDF}">""" +
            """<rdf:Description rdf:about=""/></rdf:RDF></x:xmpmeta>"""

        fun parse(packet: String?): Xmp {
            val text = packet?.takeIf { it.isNotBlank() } ?: EMPTY
            val factory = DocumentBuilderFactory.newInstance().apply {
                isNamespaceAware = true
                runCatching { setFeature("http://apache.org/xml/features/disallow-doctype-decl", true) }
            }
            val doc = try {
                factory.newDocumentBuilder().parse(InputSource(StringReader(stripPacket(text))))
            } catch (e: Exception) {
                factory.newDocumentBuilder().parse(InputSource(StringReader(EMPTY)))
            }
            return Xmp(doc)
        }

        private fun stripPacket(text: String): String =
            text.replace(Regex("""<\?xpacket[^>]*\?>"""), "").trim().trimStart('﻿')
    }

    private fun descriptions(): List<Element> {
        val list = doc.getElementsByTagNameNS(Ns.RDF, "Description")
        return (0 until list.length).map { list.item(it) as Element }
    }

    private fun rdf(): Element {
        val list = doc.getElementsByTagNameNS(Ns.RDF, "RDF")
        if (list.length > 0) return list.item(0) as Element
        val root = doc.documentElement
        val rdf = doc.createElementNS(Ns.RDF, "rdf:RDF")
        root.appendChild(rdf)
        return rdf
    }

    private fun mainDescription(): Element = descriptions().firstOrNull() ?: run {
        val d = doc.createElementNS(Ns.RDF, "rdf:Description")
        d.setAttributeNS(Ns.RDF, "rdf:about", "")
        rdf().appendChild(d)
        d
    }

    /** A simple value: an attribute on a Description, or a child element's text. */
    private fun simple(ns: String, name: String): String? {
        for (d in descriptions()) {
            if (d.hasAttributeNS(ns, name)) return d.getAttributeNS(ns, name)
            val els = d.getElementsByTagNameNS(ns, name)
            if (els.length > 0) {
                val e = els.item(0) as Element
                val lis = e.getElementsByTagNameNS(Ns.RDF, "li")
                return if (lis.length > 0) lis.item(0).textContent else e.textContent
            }
        }
        return null
    }

    private fun remove(ns: String, name: String) {
        for (d in descriptions()) {
            if (d.hasAttributeNS(ns, name)) d.removeAttributeNS(ns, name)
            val els = d.getElementsByTagNameNS(ns, name)
            for (i in els.length - 1 downTo 0) {
                val n = els.item(i)
                n.parentNode.removeChild(n)
            }
        }
    }

    private fun setSimple(ns: String, prefix: String, name: String, value: String?) {
        remove(ns, name)
        if (value.isNullOrEmpty()) return
        val d = mainDescription()
        d.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:$prefix", ns)
        d.setAttributeNS(ns, "$prefix:$name", value)
    }

    val keywords: List<String>
        get() {
            val out = linkedMapOf<String, String>()
            for (d in descriptions()) {
                val subjects = d.getElementsByTagNameNS(Ns.DC, "subject")
                for (i in 0 until subjects.length) {
                    val lis = (subjects.item(i) as Element).getElementsByTagNameNS(Ns.RDF, "li")
                    for (j in 0 until lis.length) {
                        val kw = lis.item(j).textContent.trim()
                        if (kw.isNotEmpty()) out.putIfAbsent(kw.lowercase(), kw)
                    }
                }
                if (d.hasAttributeNS(Ns.DC, "subject")) {
                    d.getAttributeNS(Ns.DC, "subject").split(',').map { it.trim() }.filter { it.isNotEmpty() }
                        .forEach { out.putIfAbsent(it.lowercase(), it) }
                }
            }
            return out.values.toList()
        }

    fun setKeywords(keywords: List<String>) {
        remove(Ns.DC, "subject")
        if (keywords.isEmpty()) return
        val d = mainDescription()
        d.setAttributeNS("http://www.w3.org/2000/xmlns/", "xmlns:dc", Ns.DC)
        val subject = doc.createElementNS(Ns.DC, "dc:subject")
        val bag = doc.createElementNS(Ns.RDF, "rdf:Bag")
        for (kw in keywords) {
            val li = doc.createElementNS(Ns.RDF, "rdf:li")
            li.textContent = kw
            bag.appendChild(li)
        }
        subject.appendChild(bag)
        d.appendChild(subject)
    }

    var label: String
        get() = simple(Ns.XMP, "Label")?.let { v -> LABELS.firstOrNull { it.equals(v, true) } ?: v } ?: ""
        set(value) = setSimple(Ns.XMP, "xmp", "Label", value)

    var rating: Int
        get() = simple(Ns.XMP, "Rating")?.trim()?.toDoubleOrNull()?.toInt() ?: 0
        set(value) = setSimple(Ns.XMP, "xmp", "Rating", if (value > 0) value.toString() else null)

    var bookmarked: Boolean
        get() = simple(Ns.XMP_DM, "good")?.trim()?.lowercase() in setOf("true", "1")
        set(value) = setSimple(Ns.XMP_DM, "xmpDM", "good", if (value) "True" else null)

    var history: String
        get() = simple(Ns.PHOTOSHOP, "History") ?: ""
        set(value) = setSimple(Ns.PHOTOSHOP, "photoshop", "History", value)

    fun fields() = XmpFields(keywords, label, rating, bookmarked, history)

    /** The packet, ready to go in a photo (with the xpacket wrapper and some padding for later edits). */
    fun serialize(): String {
        val t = TransformerFactory.newInstance().newTransformer()
        t.setOutputProperty(OutputKeys.OMIT_XML_DECLARATION, "yes")
        t.setOutputProperty(OutputKeys.ENCODING, "UTF-8")
        val w = StringWriter()
        t.transform(DOMSource(doc.documentElement as Node), StreamResult(w))
        val pad = (" ".repeat(99) + "\n").repeat(20)
        return "<?xpacket begin=\"﻿\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n" + w.toString() + "\n" + pad +
            "<?xpacket end=\"w\"?>"
    }
}
