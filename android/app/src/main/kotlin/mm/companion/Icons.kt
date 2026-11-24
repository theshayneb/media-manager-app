package mm.companion

import androidx.compose.material3.Icon
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.SolidColor
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.vector.addPathNodes
import androidx.compose.ui.unit.dp

/** The app's line icons (one style for all; drawn here, so no icon library is needed). */
object Line {
    private fun icon(name: String, vararg paths: String): ImageVector =
        ImageVector.Builder(name, 24.dp, 24.dp, 24f, 24f).apply {
            for (d in paths) addPath(addPathNodes(d), stroke = SolidColor(Color.White), strokeLineWidth = 1.8f,
                strokeLineCap = StrokeCap.Round, strokeLineJoin = StrokeJoin.Round)
        }.build()

    val Back = icon("back", "M15 5l-7 7 7 7")
    val Refresh = icon("refresh", "M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7")
    val Settings = icon("settings", "M9 12a3 3 0 1 0 6 0a3 3 0 1 0 -6 0",
        "M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1 .1a2 2 0 1 1 -2.8 2.8l-.1 -.1a1.7 1.7 0 0 0 -1.8 -.3a1.7 1.7 0 0 0 -1 1.5V21a2 2 0 1 1 -4 0v-.1a1.7 1.7 0 0 0 -1.1 -1.5a1.7 1.7 0 0 0 -1.8 .3l-.1 .1a2 2 0 1 1 -2.8 -2.8l.1 -.1a1.7 1.7 0 0 0 .3 -1.8a1.7 1.7 0 0 0 -1.5 -1H3a2 2 0 1 1 0 -4h.1a1.7 1.7 0 0 0 1.5 -1.1a1.7 1.7 0 0 0 -.3 -1.8l-.1 -.1a2 2 0 1 1 2.8 -2.8l.1 .1a1.7 1.7 0 0 0 1.8 .3H9a1.7 1.7 0 0 0 1 -1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5a1.7 1.7 0 0 0 1.8 -.3l.1 -.1a2 2 0 1 1 2.8 2.8l-.1 .1a1.7 1.7 0 0 0 -.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0 -1.5 1z")
    val Crop = icon("crop", "M6 2v14a2 2 0 0 0 2 2h14", "M18 22V8a2 2 0 0 0-2-2H2")
    val Rotate = icon("rotate", "M21 12a9 9 0 1 1-3-6.7", "M21 3v6h-6")
    val Flip = icon("flip", "M12 3v18", "M8 7l-5 5 5 5V7z", "M16 7l5 5-5 5V7z")
    val FullScreen = icon("full", "M4 9V4h5", "M20 9V4h-5", "M4 15v5h5", "M20 15v5h-5")
    val ExitFullScreen = icon("exitfull", "M9 4v5H4", "M15 4v5h5", "M9 20v-5H4", "M15 20v-5h5")
    val Delete = icon("delete", "M4 7h16", "M10 11v6", "M14 11v6", "M6 7l1 13h10l1-13", "M9 7V4h6v3")
    val Folder = icon("folder", "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z")
    val Pencil = icon("pencil", "M4 20h4L19 9l-4-4L4 16z")
    val Check = icon("check", "M5 12l5 5 9-10")
}

@Composable
fun LineIcon(icon: ImageVector, description: String, tint: Color = Color(0xFFD8DADD), modifier: Modifier = Modifier) =
    Icon(icon, description, modifier, tint = tint)
