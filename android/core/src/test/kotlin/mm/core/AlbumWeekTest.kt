package mm.core

import java.time.LocalDate
import kotlin.test.Test
import kotlin.test.assertEquals

class AlbumWeekTest {
    @Test fun firstWeekJoinsTheNextWhenShort() {
        assertEquals(AlbumWeek(2026, 1, LocalDate.of(2026, 1, 1), LocalDate.of(2026, 1, 10)), albumWeek(LocalDate.of(2026, 1, 1)))
        assertEquals(1, albumWeek(LocalDate.of(2026, 1, 10)).number)
        assertEquals(AlbumWeek(2027, 1, LocalDate.of(2027, 1, 1), LocalDate.of(2027, 1, 9)), albumWeek(LocalDate.of(2027, 1, 5)))
    }

    @Test fun novemberWeeks() {
        assertEquals(AlbumWeek(2026, 46, LocalDate.of(2026, 11, 15), LocalDate.of(2026, 11, 21)), albumWeek(LocalDate.of(2026, 11, 21)))
        assertEquals(47, albumWeek(LocalDate.of(2026, 11, 22)).number)
    }

    @Test fun lastWeekEndsOnDecember31() {
        assertEquals(LocalDate.of(2026, 12, 31), albumWeek(LocalDate.of(2026, 12, 31)).last)
    }
}

class ApplyingTest {
    @Test fun keywordsAddAndRemove() {
        val f = XmpFields(keywords = listOf("Me", "josh"))
        assertEquals(listOf("josh", "queens"), f.applying(Change.Keywords(add = listOf("queens", "JOSH"), remove = listOf("me"))).keywords)
        assertEquals(5, f.applying(Change.Flag("Star", true)).rating)
        assertEquals(XmpFields(keywords = listOf("Me", "josh")), f.copy(label = "Red", bookmarked = true).applying(Change.ClearLabels))
    }
}

class ShadowsTest {
    /** The same numbers as photo_edit.py gives (the PC and the phone edit alike). */
    @Test fun sameAsThePc() {
        val at = intArrayOf(0, 10, 30, 46, 90, 128, 200, 255)
        fun table(sh: Int) = lookupTable(Adjustments(shadows = sh, contrast = 20, brightness = 10))[0].let { t -> at.map { t[it] } }
        assertEquals(listOf(0, 19, 79, 104, 122, 135, 221, 255), table(100))
        assertEquals(listOf(0, 0, 0, 6, 75, 134, 221, 255), table(-100))
        assertEquals(listOf(0, 0, 38, 61, 101, 135, 221, 255), table(40))
        val at2 = intArrayOf(0, 10, 30, 46, 90, 128, 200, 230, 255)
        fun high(h: Int) = lookupTable(Adjustments(highlights = h, contrast = 20, brightness = 10))[0].let { t -> at2.map { t[it] } }
        assertEquals(listOf(0, 0, 11, 32, 87, 137, 246, 255, 255), high(100))
        assertEquals(listOf(0, 0, 11, 32, 87, 127, 149, 199, 255), high(-100))
        val mid = lookupTable(Adjustments(shadows = 100))[0][128]
        kotlin.test.assertTrue(mid - 128 <= 4, "mid-grey moved to $mid")
    }
}
