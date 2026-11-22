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
