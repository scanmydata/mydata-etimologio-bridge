"""Παράγει τα γραφικά του installer από το logo.svg.

    uv run --extra gui python installer/make_icon.py

Βγάζει:
  icon.ico          εικονίδιο για το exe και τη γραμμή εργασιών (λογότυπο myDATA)
  installer-icon.ico  εικονίδιο του setup.exe — το σήμα ScanmyData/e-Τιμολόγιο
  logo.png          το λογότυπο σε PNG
  wizard-small.bmp  το λογότυπο στην κεφαλίδα του installer
  wizard-large.bmp  η πλαϊνή εικόνα στην πρώτη/τελευταία σελίδα του installer

Το Qt γράφει ICO και BMP, οπότε δεν χρειάζεται Pillow. Το .ico περιέχει όλα τα
μεγέθη που ζητούν τα Windows: 16 για τη λίστα αρχείων, 32 για τη γραμμή
εργασιών, 48 για τον Explorer, 256 για τα μεγάλα εικονίδια.

Ο Inno Setup δέχεται **μόνο** BMP για τις εικόνες του οδηγού — όχι PNG/SVG —
γι' αυτό γράφονται ξεχωριστά και με αδιαφανές φόντο (το BMP δεν έχει άλφα).

ΠΡΟΣΟΧΗ: μην το τρέξετε με ``QT_QPA_PLATFORM=offscreen``. Το offscreen backend
δεν στοιχειοθετεί το ``<text>`` του SVG, οπότε το λογότυπο βγαίνει **χωρίς τη
λέξη «DATA»** — και μάλιστα σιωπηλά, χωρίς κανένα σφάλμα.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QGuiApplication, QImage, QPainter, QPen
from PySide6.QtSvg import QSvgRenderer

SIZES = (16, 24, 32, 48, 64, 128, 256)

HERE = Path(__file__).parent
SVG = HERE / "logo.svg"
ICO = HERE / "icon.ico"
PNG = HERE / "logo.png"
WIZARD_SMALL = HERE / "wizard-small.bmp"
WIZARD_LARGE = HERE / "wizard-large.bmp"

# Το setup.exe φοράει το σήμα ScanmyData (το ίδιο που δείχνει το πλαϊνό μενού
# κάτω αριστερά όταν είσαι στο e-Τιμολόγιο Pro), όχι το λογότυπο του
# Downloader: αυτό αναγνωρίζει ο πελάτης όταν του στέλνεις το αρχείο.
BRAND_PNG = HERE / "etimologio-logo.png"
INSTALLER_ICO = HERE / "installer-icon.ico"

# Το σήμα ScanmyData σε διαφάνεια, σκούρο μπλε. ΔΕΝ μπαίνει σκέτο σε εικονίδιο:
# πάνω στη σκούρα γραμμή εργασιών των Windows το σκούρο σχέδιο εξαφανίζεται.
# Μπαίνει πάντα σε λευκή στρογγυλεμένη πλακέτα — όπως ακριβώς το παλιό
# εικονίδιο myDATA, που γι' αυτόν τον λόγο είχε κι εκείνο λευκό φόντο.
BRAND_MARK = HERE / "scanmydata-light.png"
TILE_BG = QColor("#ffffff")
TILE_BORDER = QColor("#123a63")
BRAND_PREVIEW = HERE / "app-icon-preview.png"


def render(renderer: QSvgRenderer, size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return image


def _dib_entry(image: QImage) -> bytes:
    """Μία εικόνα ICO σε κλασική μορφή DIB (BITMAPINFOHEADER + BGRA + μάσκα).

    Τα μικρά μεγέθη γράφονται ως DIB και όχι ως PNG: το PNG μέσα σε ICO το
    δέχονται τα Windows από τα Vista και μετά, αλλά αρκετά σημεία του κελύφους
    (γραμμή εργασιών, Alt-Tab) το αγνοούν σιωπηλά στα μικρά μεγέθη και δείχνουν
    το γενικό εικονίδιο — ακριβώς το σύμπτωμα «χάθηκε το λογότυπο».
    """
    image = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = image.width(), image.height()

    # Το ARGB32 του Qt είναι 0xAARRGGBB σε little-endian, δηλαδή bytes B,G,R,A —
    # ακριβώς η σειρά που θέλει το DIB. Οι γραμμές γράφονται από κάτω προς τα πάνω.
    rows = []
    for y in range(height - 1, -1, -1):
        rows.append(bytes(image.constScanLine(y))[: width * 4])
    xor = b"".join(rows)

    # Μάσκα διαφάνειας 1bpp, με γραμμές στοιχισμένες σε 4 bytes. Μένει μηδενική:
    # η διαφάνεια δίνεται από το κανάλι άλφα του 32bit XOR.
    mask_row = ((width + 31) // 32) * 4
    and_mask = b"\x00" * (mask_row * height)

    header = struct.pack(
        "<IiiHHIIiiII",
        40, width, height * 2, 1, 32, 0, len(xor) + len(and_mask), 0, 0, 0, 0,
    )
    return header + xor + and_mask


def write_ico(images: list[QImage], path: Path) -> None:
    """Γράφει ICO με όλα τα μεγέθη — το Qt γράφει μόνο ένα."""
    payloads = [_dib_entry(image) for image in images]

    offset = 6 + 16 * len(images)
    directory = b""
    for image, payload in zip(images, payloads):
        size = image.width()
        directory += struct.pack(
            "<BBBBHHII",
            0 if size >= 256 else size,
            0 if size >= 256 else size,
            0, 0, 1, 32, len(payload), offset,
        )
        offset += len(payload)

    path.write_bytes(
        struct.pack("<HHH", 0, 1, len(images)) + directory + b"".join(payloads)
    )


def alpha_columns(image: QImage) -> list[bool]:
    """Ποιες στήλες έχουν μελάνι· η μάσκα από την οποία βρίσκουμε το κενό."""
    used = []
    for x in range(image.width()):
        column = False
        for y in range(image.height()):
            if ((image.pixel(x, y) >> 24) & 0xFF) > 12:
                column = True
                break
        used.append(column)
    return used


def brand_symbol(source: QImage) -> QImage:
    """Μόνο το σήμα (χέρι + κινητό), χωρίς το λεκτικό «ScanmyData».

    Το λεκτικό δεν διαβάζεται στα 16 ή 32 pixel — γίνεται μουτζούρα. Το κόψιμο
    δεν είναι καρφωμένο σε συντεταγμένες: βρίσκουμε το **πλατύτερο κενό** της
    εικόνας, που είναι το διάστημα ανάμεσα στο σήμα και στο κείμενο, ώστε ένα
    μελλοντικό λογότυπο άλλων διαστάσεων να κοπεί σωστά χωρίς αλλαγή κώδικα.
    """
    image = source.convertToFormat(QImage.Format.Format_ARGB32)
    used = alpha_columns(image)
    gaps, start = [], None
    for x, ink in enumerate(used):
        if not ink and start is None:
            start = x
        elif ink and start is not None:
            gaps.append((start, x - start))
            start = None
    inner = [g for g in gaps if g[0] > 0]
    if not inner:
        return image
    split = max(inner, key=lambda g: g[1])[0]
    first = used.index(True) if True in used else 0
    rows = [y for y in range(image.height())
            if any(((image.pixel(x, y) >> 24) & 0xFF) > 12 for x in range(first, split))]
    if not rows:
        return image
    return image.copy(first, rows[0], split - first, rows[-1] - rows[0] + 1)


def branded_tile(symbol: QImage, size: int) -> QImage:
    """Το σήμα πάνω σε λευκή στρογγυλεμένη πλακέτα, σε ένα μέγεθος."""
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

    # Το περίγραμμα λεπταίνει αναλογικά· κάτω από 24px παραλείπεται εντελώς,
    # γιατί ένα 1px πλαίσιο εκεί τρώει το ίδιο το σχέδιο.
    stroke = size * 0.035
    inset = stroke / 2 if size >= 24 else 0.0
    radius = size * 0.2
    painter.setBrush(QBrush(TILE_BG))
    painter.setPen(QPen(TILE_BORDER, stroke) if size >= 24 else Qt.PenStyle.NoPen)
    painter.drawRoundedRect(
        QRectF(inset, inset, size - 2 * inset, size - 2 * inset), radius, radius
    )

    # Περιθώριο: το σήμα δεν ακουμπά ποτέ την άκρη της πλακέτας.
    pad = size * 0.16
    box = size - 2 * pad
    scaled = symbol.scaled(
        int(box), int(box),
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    painter.drawImage(
        int((size - scaled.width()) / 2), int((size - scaled.height()) / 2), scaled
    )
    painter.end()
    return canvas


def render_png(source: QImage, size: int) -> QImage:
    """Ένα μέγεθος του σήματος, από την πηγαία εικόνα.

    Κάθε μέγεθος βγαίνει με μία σμίκρυνση από το πρωτότυπο 512άρι (και όχι
    αλυσιδωτά), αλλιώς τα μικρά μεγέθη μαζεύουν θολούρα από τα ενδιάμεσα.
    """
    scaled = source.scaled(
        size, size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    if scaled.width() == size and scaled.height() == size:
        return scaled
    # Μη τετράγωνη πηγή: κεντράρισμα σε τετράγωνο καμβά, χωρίς παραμόρφωση.
    canvas = QImage(size, size, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    painter.drawImage((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


def wizard_bmp(
    renderer: QSvgRenderer, width: int, height: int, logo: int, background: str
) -> QImage:
    """Λογότυπο κεντραρισμένο σε αδιαφανές φόντο, σε μορφή που δέχεται ο Inno.

    Format_RGB32 (χωρίς άλφα): το BMP δεν κρατά διαφάνεια, και ένα ARGB θα
    έγραφε μαύρο εκεί που περίμενε κανείς λευκό.
    """
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(background))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    renderer.render(
        painter, QRectF((width - logo) / 2, (height - logo) / 2, logo, logo)
    )
    painter.end()
    return image


def main() -> int:
    QGuiApplication([])  # χρειάζεται για το raster backend
    if not SVG.exists():
        print(f"Δεν βρέθηκε το {SVG}", file=sys.stderr)
        return 1

    renderer = QSvgRenderer(str(SVG))
    if not renderer.isValid():
        print("Το logo.svg δεν είναι έγκυρο SVG", file=sys.stderr)
        return 1

    # Το εικονίδιο της εφαρμογής (γραμμή εργασιών, Alt-Tab, exe) είναι το σήμα
    # ScanmyData — αυτό αναγνωρίζει ο πελάτης. Κάθε μέγεθος συντίθεται ξεχωριστά:
    # μια υποβάθμιση του 256 στα 16 pixel βγάζει θολή κηλίδα.
    mark = QImage(str(BRAND_MARK)) if BRAND_MARK.exists() else QImage()
    if mark.isNull():
        print(f"ΠΡΟΣΟΧΗ: λείπει το {BRAND_MARK.name} — κρατώ το λογότυπο myDATA",
              file=sys.stderr)
        write_ico([render(renderer, size) for size in SIZES], ICO)
    else:
        symbol = brand_symbol(mark)
        write_ico([branded_tile(symbol, size) for size in SIZES], ICO)
        branded_tile(symbol, 256).save(str(BRAND_PREVIEW), "PNG")
    render(renderer, 512).save(str(PNG), "PNG")

    # Κεφαλίδα οδηγού: λευκό φόντο, όσο πιο κοντά στο θέμα «modern» του Inno.
    wizard_bmp(renderer, 138, 138, 118, "#ffffff").save(str(WIZARD_SMALL), "BMP")
    # Πλαϊνή εικόνα: το σκούρο μπλε της εφαρμογής, με το λογότυπο στη μέση.
    wizard_bmp(renderer, 192, 386, 128, "#0d2340").save(str(WIZARD_LARGE), "BMP")

    # Το setup.exe φοράει ΤΟ ΙΔΙΟ σήμα με την εφαρμογή. Δύο διαφορετικά
    # εικονίδια για το ίδιο προϊόν μπερδεύουν: ο πελάτης κατεβάζει ένα αρχείο
    # και μετά ψάχνει άλλο εικονίδιο στη γραμμή εργασιών.
    if not mark.isNull():
        symbol = brand_symbol(mark)
        write_ico([branded_tile(symbol, size) for size in SIZES], INSTALLER_ICO)
    elif BRAND_PNG.exists():
        brand = QImage(str(BRAND_PNG))
        if brand.isNull():
            print(f"Το {BRAND_PNG.name} δεν διαβάζεται", file=sys.stderr)
            return 1
        write_ico([render_png(brand, size) for size in SIZES], INSTALLER_ICO)
    else:
        print(f"ΠΡΟΣΟΧΗ: λείπει το {BRAND_PNG.name} — ο installer θα πάρει το εικονίδιο της εφαρμογής",
              file=sys.stderr)

    outputs = [ICO, PNG, WIZARD_SMALL, WIZARD_LARGE]
    if INSTALLER_ICO.exists():
        outputs.append(INSTALLER_ICO)
    for path in outputs:
        print(f"Δημιουργήθηκε: {path.name}  ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
