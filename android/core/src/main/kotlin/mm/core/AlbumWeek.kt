package mm.core

import java.time.LocalDate
import java.time.temporal.ChronoUnit

/** A week of the user's scrapbook album: its year, number, first and last day (Sunday to Saturday). */
data class AlbumWeek(val year: Int, val number: Int, val first: LocalDate, val last: LocalDate)

/**
 * The album week a day is in, as the PC counts them (photo_manager grid.album_week): each year starts its own
 * Week 1 on January 1; a first week shorter than 4 days is part of Week 1 with the next full week; the last week
 * ends on December 31.
 */
fun albumWeek(day: LocalDate): AlbumWeek {
    val year = day.year
    val jan1 = LocalDate.of(year, 1, 1)
    val offset = jan1.dayOfWeek.value % 7  // days since Sunday
    val short = (7 - offset) % 7           // days before the first full week
    val firstEnd = jan1.plusDays(if (short in 1..3) (short + 6).toLong() else if (short > 0) (short - 1).toLong() else 6L)
    val dec31 = LocalDate.of(year, 12, 31)
    if (!day.isAfter(firstEnd)) return AlbumWeek(year, 1, jan1, minOf(firstEnd, dec31))
    val n = ChronoUnit.DAYS.between(firstEnd, day).toInt() - 1
    val start = firstEnd.plusDays(1L + n / 7 * 7)
    return AlbumWeek(year, 2 + n / 7, start, minOf(start.plusDays(6), dec31))
}
