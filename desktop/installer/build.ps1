# Χτίζει το .exe και τον Windows installer.
#
#   powershell -ExecutionPolicy Bypass -File installer\build.ps1
#
# Παράγει:  dist\installer\TimologioDownloader-<έκδοση>-setup.exe
#
# Δουλεύει είτε με uv είτε με σκέτο .venv: σε μηχάνημα χωρίς uv (π.χ. καθαρός
# υπολογιστής γραφείου) το build δεν πρέπει να κολλάει σε εργαλείο ανάπτυξης.

#   -WithVoice   κατεβάζει και πακετάρει το ελληνικό μοντέλο φωνής (~1.1 GB
#                αποσυμπιεσμένο) για τον ψηφιακό βοηθό. Χωρίς αυτό, ο βοηθός
#                δουλεύει κανονικά με κείμενο και το μικρόφωνο εξηγεί τι λείπει.
param([switch]$WithVoice)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# --- Πώς τρέχουμε python -----------------------------------------------------
$uv = (Get-Command uv -ErrorAction SilentlyContinue)
$venvPy = Join-Path $root ".venv\Scripts\python.exe"

if ($uv) {
    Write-Host "== 1/5  Εξαρτήσεις (uv) ==" -ForegroundColor Cyan
    uv sync --extra gui --group dev
    $py = { param($a) & uv run --extra gui python @a }
    $pyi = { param($a) & uv run --extra gui pyinstaller @a }
} elseif (Test-Path $venvPy) {
    Write-Host "== 1/5  Εξαρτήσεις (.venv) ==" -ForegroundColor Cyan
    Write-Host "   uv δεν βρέθηκε — χρησιμοποιώ το υπάρχον .venv" -ForegroundColor Yellow
    & $venvPy -m pip install --quiet pyinstaller
    $py = { param($a) & $venvPy @a }
    $pyi = { param($a) & $venvPy -m PyInstaller @a }
} else {
    throw "Δεν βρέθηκε ούτε uv ούτε .venv. Τρέξτε:  py -m venv .venv ; .venv\Scripts\pip install -e .[gui] pyinstaller"
}

$env:PYTHONPATH = Join-Path $root "src"

# --- Ψηφιακή υπογραφή (προαιρετική) ------------------------------------------
# Το exe και το setup.exe φέρουν ήδη πλήρη VersionInfo (εκδότης «scanmydata»),
# που μειώνει τα ψευδώς-θετικά. Ωστόσο, χωρίς ψηφιακή υπογραφή (Authenticode) το
# SmartScreen δείχνει πάντα «άγνωστος εκδότης». Η υπογραφή θέλει πιστοποιητικό
# code-signing. Αν οριστεί (μέσω μεταβλητών περιβάλλοντος), υπογράφουμε ΚΑΙ το
# exe ΚΑΙ το setup.exe· αλλιώς το βήμα παραλείπεται σιωπηλά. Έτσι το build είναι
# «universal»: μόλις αποκτηθεί πιστοποιητικό, η υπογραφή γίνεται αυτόματα.
#   $env:TIMOLOGIO_SIGN_PFX  = 'C:\path\cert.pfx'; $env:TIMOLOGIO_SIGN_PASS='...'
#   -ή- $env:TIMOLOGIO_SIGN_SHA1 = '<thumbprint πιστοποιητικού στο store>'
function Find-SignTool {
    $cmd = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $roots = @("${env:ProgramFiles(x86)}\Windows Kits\10\bin",
               "$env:ProgramFiles\Windows Kits\10\bin")
    foreach ($r in $roots) {
        if (Test-Path $r) {
            $exe = Get-ChildItem -Path $r -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -match '\\x64\\' } |
                Sort-Object FullName -Descending | Select-Object -First 1
            if ($exe) { return $exe.FullName }
        }
    }
    return $null
}

function Invoke-Sign($file) {
    $pfx  = $env:TIMOLOGIO_SIGN_PFX
    $sha1 = $env:TIMOLOGIO_SIGN_SHA1
    if (-not $pfx -and -not $sha1) { return }   # δεν ρυθμίστηκε υπογραφή — σιωπηλή παράλειψη
    $st = Find-SignTool
    if (-not $st) { throw "Ζητήθηκε υπογραφή αλλά δεν βρέθηκε το signtool.exe (Windows SDK)." }
    $ts = 'http://timestamp.digicert.com'
    if ($pfx) {
        & $st sign /fd SHA256 /f $pfx /p $env:TIMOLOGIO_SIGN_PASS /tr $ts /td SHA256 $file
    } else {
        & $st sign /fd SHA256 /sha1 $sha1 /tr $ts /td SHA256 $file
    }
    if ($LASTEXITCODE -ne 0) { throw "Η υπογραφή απέτυχε: $file" }
    Write-Host "   υπογράφηκε: $file" -ForegroundColor Green
}

# --- Γραφικά -----------------------------------------------------------------
# ΠΡΟΣΟΧΗ: χωρίς offscreen. Το offscreen backend δεν στοιχειοθετεί το <text> του
# SVG και το λογότυπο βγαίνει σιωπηλά χωρίς τη λέξη «DATA».
Write-Host "== 2/5  Εικονίδιο και γραφικά installer ==" -ForegroundColor Cyan
Remove-Item Env:\QT_QPA_PLATFORM -ErrorAction SilentlyContinue
& $py @("installer\make_icon.py")

# --- Εγχειρίδιο --------------------------------------------------------------
Write-Host "== 3/5  Εγχειρίδια PDF (docs\manual.pdf, docs\etim-manual.pdf) ==" -ForegroundColor Cyan
& $py @("-c", @"
from pathlib import Path
from PySide6.QtGui import QGuiApplication
app = QGuiApplication([])
from timologio.gui.manual import build_manual
from timologio.etimologio.help import build_manual as build_etim_manual
docs = Path('docs'); docs.mkdir(exist_ok=True)
# Δύο εγχειρίδια, ένα ανά εφαρμογή. Και τα δύο χτίζονται ΕΔΩ και μπαίνουν έτοιμα
# στο bundle: το runtime rendering στο πακεταρισμένο exe έβγαζε κενό PDF.
# ΜΟΝΟ ASCII στα μηνύματα: η κονσόλα του build τρέχει σε codepage που δεν
# κωδικοποιεί ελληνικά, και ένα print έριχνε ολόκληρο το build με UnicodeEncodeError.
for label, build, out in (
    ('Downloader', build_manual, docs / 'manual.pdf'),
    ('e-Timologio', build_etim_manual, docs / 'etim-manual.pdf'),
):
    build(out)
    size = out.stat().st_size
    print('  ', label, out, size, 'bytes')
    if size < 20000:
        raise SystemExit(f'ERROR: manual {out} came out empty ({size} bytes)')
"@)
if ($LASTEXITCODE -ne 0) { throw "Manual build failed" }

# --- Piper TTS: η φωνή του βοηθού (ελληνικά + αγγλικά) -----------------------
# Τα Windows ΔΕΝ έχουν ελληνική φωνή από προεπιλογή, οπότε κάθε λύση που
# στηρίζεται στο λειτουργικό ή στον browser είτε σωπαίνει είτε συλλαβίζει τα
# ελληνικά με αγγλική φωνή. Κουβαλάμε δική μας μηχανή και δύο μοντέλα (~80 MB).
# Δεν μπαίνουν στο git — κατεβαίνουν εδώ και ξαναχρησιμοποιούνται.
Write-Host "== 3.6/5  Piper TTS (installer\piper) ==" -ForegroundColor Cyan
$piperDir = Join-Path $PSScriptRoot "piper"
$piperExe = Join-Path $piperDir "piper.exe"
$voiceDir = Join-Path $piperDir "voices"
if (-not (Test-Path $piperExe)) {
    New-Item -ItemType Directory -Force $piperDir | Out-Null
    $zip = Join-Path $env:TEMP "piper_windows_amd64.zip"
    $url = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
    Write-Host "   λήψη μηχανής φωνής..." -ForegroundColor DarkGray
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $env:TEMP -Force
    # Το zip ξεπακετάρει σε υποφάκελο piper\ — ισοπεδώνουμε.
    $inner = Join-Path $env:TEMP "piper"
    Copy-Item (Join-Path $inner "*") $piperDir -Recurse -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Force $voiceDir | Out-Null
# ΜΕΣΑΙΑ ποιότητα, όχι low: μετρημένα στην ίδια πρόταση 56 χαρακτήρων —
#   rapunzelina-low     8,19s @ 16000 Hz
#   rapunzelina-medium  8,38s @ 22050 Hz   <- ίδιος ρυθμός, καθαρότερη άρθρωση
#   joy-medium         11,50s @ 22050 Hz   (37% πιο αργή· εναλλακτική χροιά)
# Ίδιο μέγεθος (~63 MB), αισθητά καλύτερη ποιότητα.
# Η ΕΠΙΛΕΓΜΕΝΗ ελληνική φωνή είναι η joy-medium: πιο αργή, με καθαρότερη άρθρωση
# στους αριθμούς και στα ΑΦΜ, που είναι το μισό περιεχόμενο των απαντήσεων.
# ΜΟΝΟ όσες είναι εδώ ταξιδεύουν — μια δεύτερη ελληνική φωνή «για εφεδρεία» δεν
# παίζει ποτέ (το speech.py προτιμά ρητά την joy) και κοστίζει 63 MB.
$voices = @(
    @{ name = "el_GR-joy-medium";         url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/el/el_GR/joy/medium/el_GR-joy-medium" },
    @{ name = "en_US-lessac-medium";      url = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium" }
)
foreach ($v in $voices) {
    $onnx = Join-Path $voiceDir ($v.name + ".onnx")
    $json = Join-Path $voiceDir ($v.name + ".onnx.json")
    if (-not (Test-Path $onnx)) {
        Write-Host ("   voice " + $v.name) -ForegroundColor DarkGray
        Invoke-WebRequest -Uri ($v.url + ".onnx") -OutFile $onnx -UseBasicParsing
    }
    if (-not (Test-Path $json)) {
        Invoke-WebRequest -Uri ($v.url + ".onnx.json") -OutFile $json -UseBasicParsing
    }
}
if (-not (Test-Path $piperExe)) { throw "Piper engine missing" }
# ΜΟΝΟ οι φωνες της λιστας ταξιδευουν. Ενα build απο παλιοτερο checkout ειχε
# αφησει και τη rapunzelina-medium: 63 MB για εφεδρεια που δεν παιζει ποτε,
# αφου το speech.py προτιμα ρητα την joy.
$keepVoices = $voices | ForEach-Object { $_.name }
Get-ChildItem $voiceDir -File | Where-Object {
    ($_.Name -replace '\.onnx(\.json)?$', '') -notin $keepVoices
} | Remove-Item -Force -ErrorAction SilentlyContinue
$voiceSize = [math]::Round(((Get-ChildItem $piperDir -Recurse -File | Measure-Object Length -Sum).Sum/1MB), 1)
Write-Host ("   OK: " + (Get-ChildItem $voiceDir -Filter *.onnx).Count + " voices (" + $voiceSize + " MB)") -ForegroundColor DarkGray

# --- whisper.cpp: η ΑΝΑΓΝΩΡΙΣΗ φωνής του βοηθου -----------------------------
# Το Web Speech API θελει υπηρεσια της Google. Μεσα στο QtWebEngine δεν υπαρχει
# και η κληση ΠΑΓΩΝΕΙ ολοκληρη την εφαρμογη. Το ελληνικο μοντελο του Vosk ειναι
# ~1.1 GB (δεκαπλασιο του installer)· το whisper.cpp base ειναι πολυγλωσσο,
# ~142 MB και τρεχει σε CPU. Δεν μπαινει στο git.
Write-Host "== 3.7/5  whisper.cpp STT (installer\whisper) ==" -ForegroundColor Cyan
$sttDir = Join-Path $PSScriptRoot "whisper"
$sttExe = Join-Path $sttDir "whisper-cli.exe"
New-Item -ItemType Directory -Force $sttDir | Out-Null
# Ο,τι χρειαζεται ΜΟΝΟ για `whisper-cli -m <model> -f <wav>`. Τα ggml-cpu-*.dll
# τα φορτωνει το ggml στην εκτελεση, αναλογα με τον επεξεργαστη -- μενουν ολα.
$sttKeep = @("whisper-cli.exe", "whisper.dll", "ggml.dll", "ggml-base.dll")
# ΠΡΟΣΟΧΗ: "ggml-base.dll" ειναι backend του ggml -- ΔΕΝ ειναι το μοντελο.
$sttModelName = "ggml-small-q5_1.bin"
if (-not (Test-Path $sttExe)) {
    $sttZip = Join-Path $env:TEMP "whisper-bin-x64.zip"
    $sttUrl = "https://github.com/ggml-org/whisper.cpp/releases/latest/download/whisper-bin-x64.zip"
    Write-Host "   downloading speech-recognition engine..." -ForegroundColor DarkGray
    try {
        Invoke-WebRequest -Uri $sttUrl -OutFile $sttZip -UseBasicParsing
        $sttTmp = Join-Path $env:TEMP "whisper_extract"
        Remove-Item $sttTmp -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $sttZip -DestinationPath $sttTmp -Force
        # Το zip αλλαζει διαταξη αναμεσα σε εκδοσεις (Release\ ή ριζα): παιρνουμε
        # ο,τι ειναι exe/dll, οπου κι αν βρισκεται.
        Get-ChildItem $sttTmp -Recurse -Include *.exe, *.dll |
            ForEach-Object { Copy-Item $_.FullName $sttDir -Force }
        # ...και μετα ΠΕΤΑΜΕ ο,τι δεν τρεχει η εφαρμογη. Το zip κουβαλα ολα τα
        # παραδειγματα του whisper.cpp: talk-llama, wchess, parakeet, server,
        # stream, benchmarks, tests, SDL2. Χωρις αυτο το κλαδεμα ο installer
        # φουσκωσε κατα ~10 MB σε σκουπιδια που δεν καλει κανεις.
        Get-ChildItem $sttDir -File | Where-Object {
            $_.Name -notin $sttKeep -and $_.Name -notlike "ggml-cpu-*.dll" -and $_.Name -notlike "ggml-*.bin"
        } | Remove-Item -Force
        Remove-Item $sttZip -Force -ErrorAction SilentlyContinue
        Remove-Item $sttTmp -Recurse -Force -ErrorAction SilentlyContinue
    } catch {
        Write-Host "   WARNING: speech-recognition engine not downloaded" -ForegroundColor Yellow
    }
}
# Μοντελο: small κβαντισμενο (q5_1), ΟΧΙ base. Μετρημενο με ιδιες προτασεις --
# το base εβγαζε "Αν εξετας τα τυστικα" για "ανοιξε τα στατιστικα" και "Νεος
# πελατις" για "νεος πελατης": αχρηστο για εντολες. Το small-q5_1 τα πιανει,
# με +34 MB. (Δοκιμαστηκε και --prompt με λεξιλογιο τιμολογησης: ΧΕΙΡΟΤΕΡΕΥΕΙ
# τα αποτελεσματα, εβγαζε "???" -- μην το ξαναβαλεις.)
$sttModel = Join-Path $sttDir $sttModelName
if (-not (Test-Path $sttModel)) {
    $modelUrl = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$sttModelName"
    Write-Host "   downloading speech model (~182 MB)..." -ForegroundColor DarkGray
    try {
        Invoke-WebRequest -Uri $modelUrl -OutFile $sttModel -UseBasicParsing
    } catch {
        Write-Host "   WARNING: speech model not downloaded" -ForegroundColor Yellow
    }
}
# Η φωνητικη εντολη ειναι προαιρετικη: αν λειψει, το backend απανται 501 και το
# UI ζηταει γραπτη εντολη. Δεν ριχνουμε το build γι' αυτο.
# Το κλαδεμα ξανατρεχει και σε ηδη κατεβασμενο φακελο: ενα build απο παλιοτερο
# checkout ειχε αφησει ολα τα παραδειγματα μεσα.
Get-ChildItem $sttDir -File | Where-Object {
    $_.Name -notin $sttKeep -and $_.Name -notlike "ggml-cpu-*.dll" -and $_.Name -ne $sttModelName
} | Remove-Item -Force -ErrorAction SilentlyContinue
if ((Test-Path $sttExe) -and (Test-Path $sttModel)) {
    $sttSize = [math]::Round(((Get-ChildItem $sttDir -Recurse -File | Measure-Object Length -Sum).Sum/1MB), 1)
    Write-Host ("   OK: speech recognition bundled (" + $sttSize + " MB)") -ForegroundColor DarkGray
} else {
    Write-Host "   NOTE: building WITHOUT speech recognition" -ForegroundColor Yellow
}

# --- Φορητή PHP για το e-Τιμολόγιο Pro ---------------------------------------
# Το backend του e-Τιμολόγιο είναι PHP. Για να δουλεύει η offline λειτουργία σε
# υπολογιστή χωρίς εγκατεστημένη PHP, πακετάρουμε ένα φορητό runtime.
# Δεν μπαίνει στο git (≈30MB): το κατεβάζουμε εδώ και το ξαναχρησιμοποιούμε.
Write-Host "== 3.5/5  Φορητή PHP (installer\php) ==" -ForegroundColor Cyan
$phpDir = Join-Path $PSScriptRoot "php"
$phpExe = Join-Path $phpDir "php.exe"
if (-not (Test-Path $phpExe)) {
    # Η ακριβής έκδοση ΔΕΝ καρφώνεται: το windows.php.net μετακινεί τα παλιά
    # builds στο /archives/ και ένα σταθερό URL σκάει με 404 μόλις βγει η επόμενη
    # patch έκδοση. Ρωτάμε το releases.json για το τρέχον 8.3 NTS x64.
    $branch = "8.3"
    $rel = (Invoke-WebRequest -Uri "https://windows.php.net/downloads/releases/releases.json" `
                              -UseBasicParsing -TimeoutSec 60).Content | ConvertFrom-Json
    $entry = $rel.$branch.PSObject.Properties | Where-Object { $_.Name -like "nts-*-x64" } | Select-Object -First 1
    if (-not $entry) { throw "Δεν βρέθηκε build NTS x64 για PHP $branch στο releases.json" }
    $file = $entry.Value.zip.path
    $url  = "https://windows.php.net/downloads/releases/$file"
    Write-Host "   Λήψη PHP: $file"
    $zip = Join-Path $env:TEMP $file
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 300
    New-Item -ItemType Directory -Force $phpDir | Out-Null
    Expand-Archive -Path $zip -DestinationPath $phpDir -Force
    Remove-Item $zip -Force
} else {
    Write-Host "   Υπάρχει ήδη — παραλείπεται η λήψη."
}

# Το CA bundle: χωρίς ρητό curl.cainfo, το φορητό PHP δεν έχει ρίζες
# πιστοποίησης και ΚΑΘΕ κλήση προς mydata.aade.gr σκάει με OpenSSL error 60.
$cacert = Join-Path $phpDir "cacert.pem"
if (-not (Test-Path $cacert)) {
    Write-Host "   Λήψη cacert.pem"
    Invoke-WebRequest -Uri "https://curl.se/ca/cacert.pem" -OutFile $cacert -UseBasicParsing
}

# php.ini: το φορητό αρχείο έρχεται ΧΩΡΙΣ ini, οπότε καμία επέκταση δεν φορτώνει
# (`could not find driver`). Οι διαδρομές γράφονται σχετικές — ο φάκελος
# μετακινείται στο %LOCALAPPDATA% του πελάτη και τα absolute paths θα έσπαγαν.
@"
; Δημιουργείται από το installer\build.ps1 — μην το επεξεργάζεστε.
extension_dir = "ext"
extension=pdo_sqlite
extension=sqlite3
extension=openssl
extension=mbstring
extension=curl
extension=pdo_pgsql
curl.cainfo = "cacert.pem"
openssl.cafile = "cacert.pem"
memory_limit = 256M
max_execution_time = 300
date.timezone = "Europe/Athens"
"@ | Set-Content -Path (Join-Path $phpDir "php.ini") -Encoding utf8

# Κλάδεμα: η διανομή έρχεται με 40 επεκτάσεις και ~30MB δεδομένα ICU. Εμείς
# φορτώνουμε έξι. Χωρίς αυτό το βήμα ο installer φούσκωνε κατά ~35MB με oci8,
# firebird, snmp, ldap, imap, intl… που δεν καλούνται ποτέ.
$keep = @("php_pdo_sqlite.dll","php_sqlite3.dll","php_openssl.dll",
          "php_mbstring.dll","php_curl.dll","php_pdo_pgsql.dll")
Get-ChildItem (Join-Path $phpDir "ext") -Filter *.dll |
    Where-Object { $keep -notcontains $_.Name } | Remove-Item -Force
# icu*: μόνο για το php_intl που μόλις αφαιρέθηκε. glib/enchant: για το enchant.
foreach ($p in @("icudt*.dll","icuin*.dll","icuuc*.dll","icuio*.dll","glib-2.dll",
                 "extras","lib","php.ini-development","php.ini-production")) {
    Get-ChildItem -Path $phpDir -Filter $p -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# Επαλήθευση ότι το κλάδεμα δεν έσπασε καμία από τις έξι: αν λείπει εξάρτηση, το
# `php -m` δεν θα τη δείξει και η offline λειτουργία θα έσκαγε μόνο στον πελάτη.
$loaded = & $phpExe -c (Join-Path $phpDir "php.ini") -m
foreach ($need in @("PDO","pdo_sqlite","sqlite3","openssl","mbstring","curl")) {
    if ($loaded -notcontains $need) { throw "Η επέκταση '$need' δεν φορτώνει μετά το κλάδεμα της PHP" }
}
$phpSize = [math]::Round(((Get-ChildItem $phpDir -Recurse -File | Measure-Object Length -Sum).Sum/1MB),1)
& $phpExe -n -v | Select-Object -First 1
Write-Host "   PHP έτοιμη: $phpDir  ($phpSize MB, επεκτάσεις: $($keep.Count))"

# --- Ελληνικό μοντέλο φωνής (προαιρετικό) ------------------------------------
# Ίδια λογική με τη φορητή PHP: κατεβαίνει εδώ, δεν μπαίνει στο git. Η διαφορά
# είναι το μέγεθος (~1.1 GB), γι' αυτό μπαίνει μόνο όταν ζητηθεί ρητά.
$voiceDir = Join-Path $PSScriptRoot "vosk-model-el"
if ($WithVoice) {
    Write-Host "== 3.6/5  Ελληνικό μοντέλο φωνής (Vosk) ==" -ForegroundColor Cyan
    if (-not (Test-Path (Join-Path $voiceDir "conf"))) {
        $url = "https://alphacephei.com/vosk/models/vosk-model-el-gr-0.7.zip"
        $zip = Join-Path $env:TEMP "vosk-model-el-gr-0.7.zip"
        Write-Host "   Λήψη ~1.1 GB — θα πάρει ώρα…"
        Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing -TimeoutSec 3600
        $tmp = Join-Path $env:TEMP "vosk-extract"
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        Expand-Archive -Path $zip -DestinationPath $tmp -Force
        # Το zip περιέχει έναν φάκελο με το όνομα της έκδοσης· εμείς θέλουμε το
        # περιεχόμενό του σε σταθερή διαδρομή, αλλιώς το voice.py δεν το βρίσκει.
        $inner = Get-ChildItem $tmp -Directory | Select-Object -First 1
        New-Item -ItemType Directory -Force $voiceDir | Out-Null
        Copy-Item (Join-Path $inner.FullName "*") $voiceDir -Recurse -Force
        Remove-Item $zip, $tmp -Recurse -Force -ErrorAction SilentlyContinue
    } else {
        Write-Host "   Υπάρχει ήδη — παραλείπεται η λήψη."
    }
    $voiceSize = [math]::Round(((Get-ChildItem $voiceDir -Recurse -File | Measure-Object Length -Sum).Sum/1MB),0)
    Write-Host "   Μοντέλο έτοιμο: $voiceDir ($voiceSize MB)"
} elseif (Test-Path $voiceDir) {
    # Υπάρχει από προηγούμενο -WithVoice build: το spec θα το πακετάρει έτσι κι
    # αλλιώς, οπότε το λέμε αντί να φουσκώσει σιωπηλά ο installer κατά 1 GB.
    Write-Host "   ΣΗΜ.: υπάρχει installer\vosk-model-el — θα μπει στο bundle." -ForegroundColor Yellow
}

# --- PyInstaller -------------------------------------------------------------
Write-Host "== 4/5  PyInstaller ==" -ForegroundColor Cyan
# Ένα ανοιχτό αντίγραφο της εφαρμογής κλειδώνει τα αρχεία του dist\ και το build
# σκάει με «Access is denied» / «Device or resource busy».
Get-Process TimologioDownloader -ErrorAction SilentlyContinue | ForEach-Object {
    Write-Host "   τερματίζω ανοιχτή εφαρμογή (PID $($_.Id))" -ForegroundColor Yellow
    Stop-Process -Id $_.Id -Force
}
# Και η φορητή PHP του dist\: ο server του e-Τιμολόγιο επιβιώνει αν η εφαρμογή
# (ή ένα τεστ) τερματίσει απότομα, και κρατά κλειδωμένο το php_curl.dll — το
# build έσκαγε με «Access is denied» χωρίς να λέει ποιος το κρατά.
Get-Process php -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -and $_.Path.StartsWith((Join-Path $root "dist")) } |
    ForEach-Object {
        Write-Host "   τερματίζω ορφανή PHP του dist\ (PID $($_.Id))" -ForegroundColor Yellow
        Stop-Process -Id $_.Id -Force
    }
Start-Sleep -Seconds 1
Remove-Item "$root\dist\TimologioDownloader" -Recurse -Force -ErrorAction SilentlyContinue
& $pyi @("installer\timologio.spec", "--noconfirm", "--distpath", "dist", "--workpath", "build")
if (-not (Test-Path "$root\dist\TimologioDownloader\TimologioDownloader.exe")) {
    throw "Το PyInstaller δεν παρήγαγε το exe."
}
# Υπογράφουμε το exe ΠΡΙΝ το πακετάρει ο Inno, ώστε το υπογεγραμμένο αρχείο να
# μπει μέσα στο setup.
Invoke-Sign "$root\dist\TimologioDownloader\TimologioDownloader.exe"

# --- Inno Setup --------------------------------------------------------------
Write-Host "== 5/5  Inno Setup ==" -ForegroundColor Cyan
# Ο Inno Setup 6 εγκαθίσταται ανά χρήστη από το winget, οπότε ψάχνουμε και τις
# δύο συνηθισμένες τοποθεσίες πριν τα παρατήσουμε.
$iscc = @(
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $iscc) {
    throw "Δεν βρέθηκε το Inno Setup. Εγκαταστήστε το με:  winget install JRSoftware.InnoSetup"
}

& $iscc installer\timologio.iss
if ($LASTEXITCODE -ne 0) { throw "Ο Inno Setup απέτυχε." }

# Ταξινόμηση κατά ώρα και όχι κατά όνομα: παλιότερες εκδόσεις μένουν στον φάκελο
# και αλφαβητικά προηγούνται, οπότε το μήνυμα ανέφερε το λάθος αρχείο.
$setup = Get-ChildItem "$root\dist\installer\*.exe" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Invoke-Sign $setup.FullName
Write-Host ""
Write-Host "Έτοιμο: $($setup.FullName)" -ForegroundColor Green
Write-Host "Μέγεθος: $([math]::Round($setup.Length/1MB,1)) MB"
