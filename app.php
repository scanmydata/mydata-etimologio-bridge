<?php
// Clear OPcache on every request so file changes take effect immediately — but
// ONLY for a local/offline install. Στον server αυτό θα άδειαζε την cache
// ΟΛΟΚΛΗΡΗΣ της εφαρμογής σε κάθε άνοιγμα σελίδας, αναγκάζοντας κάθε επόμενη
// κλήση του API να ξαναμεταγλωττίσει το etimologio.php από την αρχή.
if (function_exists('opcache_reset')
    && in_array($_SERVER['REMOTE_ADDR'] ?? '', ['127.0.0.1', '::1', ''], true)
    && empty($_SERVER['HTTP_X_FORWARDED_FOR'])) { opcache_reset(); }

/**
 * e-Timologio Pro — fast, multi-tenant UI on top of etimologio.php
 * ---------------------------------------------------------------
 * Pure front-end: every operation is an AJAX call to etimologio.php with the
 * active `account` (company VAT) appended. Local features (καρτέλες + πληρωμές)
 * are backed by the bridge's encrypted SQLite store.
 *
 * Access is gated by auth.php: unauthenticated visitors (or a password-reset
 * link) get the login/signup/reset screen; logged-in users get the app.
 */
require __DIR__ . '/auth.php';
$__user = current_user();
// Το `desktop_token` έρχεται ΜΟΝΟ στην πρώτη φόρτωση του ενσωματωμένου UI.
// Κάθε επόμενη πλοήγηση (αποσύνδεση, νέα σύνδεση, ανανέωση) το έχανε — και τότε
// ξαναφαινόταν το πλαϊνό μενού της web εφαρμογής ΜΕΣΑ στην εφαρμογή
// υπολογιστή, που έχει ήδη δικό της μενού. Το κρατάμε σε cookie συνεδρίας:
// ελέγχει μόνο εμφάνιση, κανένα δικαίωμα.
$__embedded = isset($_GET['desktop_token']);
if ($__embedded) {
    setcookie('etim_shell', '1', ['expires' => 0, 'path' => '/', 'samesite' => 'Lax']);
} elseif (!empty($_COOKIE['etim_shell'])) {
    $__embedded = true;
}

$__resetToken = trim($_GET['reset'] ?? '');
// Ο σύνδεσμος επιβεβαίωσης email ανοίγει ΠΑΝΤΑ την οθόνη σύνδεσης, ακόμη κι αν
// κάποιος άλλος είναι ήδη συνδεδεμένος σε αυτόν τον browser: το token αφορά
// άλλον λογαριασμό και δεν πρέπει να «καταναλωθεί» σιωπηλά μέσα στην εφαρμογή.
$__verifyToken = trim($_GET['verify'] ?? '');
if (!$__user || $__resetToken !== '' || $__verifyToken !== '') {
    require __DIR__ . '/authview.php';   // outputs the auth page and exits
    exit;
}
$__role = $__user['role'];
$__email = $__user['email'];
$__business = $__user['business_name'];
// Η έκδοση που δείχνει το υποσέλιδο. Σε εγκατάσταση υπολογιστή τη γράφει το
// `service.py` στο config.php· σε server μπορεί να μην οριστεί καθόλου, οπότε
// το υποσέλιδο απλώς δεν τη δείχνει αντί να σκάσει.
$__version = defined('APP_VERSION_LABEL') ? APP_VERSION_LABEL : '';
?>
<!DOCTYPE html>
<html lang="el">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>e-Timologio Pro</title>
<link rel="icon" type="image/png" sizes="32x32" href="assets/icons/favicon-32.png">
<link rel="icon" type="image/png" sizes="96x96" href="assets/icons/favicon-96.png">
<link rel="icon" href="assets/icons/favicon.ico" sizes="any">
<link rel="apple-touch-icon" sizes="180x180" href="assets/icons/apple-touch-icon.png">
<link rel="manifest" href="assets/icons/site.webmanifest">
<meta name="theme-color" content="#0b1220">
<style>
  :root{
    --bg:#0b1220; --panel:#131f33; --panel2:#18263d; --line:#2b3b54;
    --txt:#e6edf6; --muted:#93a4bd; --accent:#38bdf8; --accent2:#0ea5e9;
    --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --chip:#0b2942; --hover:#1b2c45;
    --radius:14px; --shadow:0 10px 30px rgba(0,0,0,.4); --side:230px;
    /* Ίδιο με το on_accent της εφαρμογής υπολογιστή: το χρώμα της μπίλιας
       όταν ο διακόπτης είναι αναμμένος (σκούρο πάνω στο γαλάζιο). */
    --on-accent:#04222f;
    /* Η μπάρα κορυφής ήταν καρφωμένη σκούρα: στο φωτεινό θέμα το κείμενό της
       γινόταν σκούρο πάνω σε σκούρο και δεν διαβαζόταν. */
    --header-bg:rgba(10,18,32,.85);
    --menu-bg:#0a111e;   /* menu_bg της εφαρμογής υπολογιστή */
  }
  /* Light theme — activated by data-theme="light" on <html> (toggle bottom-left). */
  :root[data-theme="light"]{
    --bg:#f1f5fb; --panel:#ffffff; --panel2:#eef3fa; --line:#d5deea;
    /* --muted σκουρότερο από το αρχικό #5b6b84: στα 12px το παλιό έβγαινε 3.46:1
       πάνω στο λευκό, κάτω από το όριο αναγνωσιμότητας (4.5:1) — οι υπότιτλοι
       και οι ετικέτες πεδίων ήταν ξεθωριασμένοι στο φωτεινό θέμα. */
    --txt:#1a2637; --muted:#4a5a72; --accent:#0284c7; --accent2:#0369a1;
    --ok:#16a34a; --warn:#d97706; --bad:#dc2626; --chip:#e5eefb; --hover:#e8eef7;
    --shadow:0 10px 30px rgba(30,50,90,.12);
    --on-accent:#ffffff;
    --header-bg:rgba(255,255,255,.88);
    --menu-bg:#e9eff7;
  }
  :root[data-theme="light"] body{background:var(--bg)}
  /* Colored action buttons need readable (dark-on-tint) text in light mode */
  :root[data-theme="light"] button.add{background:#dcfce7;border-color:#16a34a;color:#166534}
  :root[data-theme="light"] button.add:hover{background:#bbf7d0}
  :root[data-theme="light"] button.tax{background:#fef3c7;border-color:#d97706;color:#92400e}
  :root[data-theme="light"] button.tax:hover{background:#fde68a}
  :root[data-theme="light"] button.info{background:#e0f2fe;border-color:var(--accent2);color:#075985}
  :root[data-theme="light"] button.info:hover{background:#bae6fd}
  :root[data-theme="light"] button.danger{background:#fef2f2;border-color:var(--bad);color:#b91c1c}
  :root[data-theme="light"] button.danger:hover{background:#fee2e2}
  :root[data-theme="light"] button.primary{color:#fff}
  :root[data-theme="light"] .toast{color:var(--txt)}
  /* Theme toggle switch (fixed bottom-left, clear of content) */
  /* Sidebar toggles (theme + tooltips) — live inside the aside, no overlap */
  .side-controls{padding:10px 12px;border-top:1px solid var(--line);display:flex;flex-direction:column;gap:9px}
  .side-actions{display:flex;flex-direction:column;gap:7px;padding-bottom:9px;margin-bottom:2px;border-bottom:1px solid var(--line)}
  .side-actions .side-act{width:100%;text-align:left;justify-content:flex-start}
  /* Τίτλος ενότητας ρυθμίσεων — ίδιος με τον διαχωριστή «ΡΥΘΜΙΣΕΙΣ» της
     εφαρμογής υπολογιστή, ώστε τα δύο μισά του προϊόντος να διαβάζονται ίδια. */
  .side-sec{font-size:10.5px;letter-spacing:.14em;color:var(--muted);font-weight:700;padding:2px 0 1px}
  /* Διακόπτες: ίδιες διαστάσεις και χρώματα με το ToggleSwitch της εφαρμογής
     υπολογιστή — κάψουλα 40×22, μπίλια 16 με περιθώριο 3, διαδρομή 18.
     Κλειστός: κανάλι = --line, μπίλια = --muted. Ανοιχτός: κανάλι =
     --accent2 (accent_deep), μπίλια = --on-accent. */
  .side-toggle{display:flex;align-items:center;gap:8px;cursor:pointer;color:var(--txt);font-size:12px;user-select:none;padding:1px 0}
  .side-toggle:hover .tt-switch{border-color:var(--accent)}
  .side-toggle .tt-switch{position:relative;width:40px;height:22px;border-radius:999px;background:var(--line);
    border:1px solid var(--line);flex:0 0 auto;transition:background .14s ease-out,border-color .14s ease-out}
  .side-toggle .tt-knob{position:absolute;top:2px;left:2px;width:16px;height:16px;border-radius:50%;background:var(--muted);
    display:flex;align-items:center;justify-content:center;font-size:10px;line-height:1;
    transition:transform .14s cubic-bezier(.33,1,.68,1),background .14s ease-out}
  .side-toggle.on .tt-switch{background:var(--accent2);border-color:var(--accent2)}
  .side-toggle.on .tt-knob{background:var(--on-accent);transform:translateX(18px)}
  /* Lightweight CSS tooltips for elements carrying data-tip (suppressed when tips off) */
  [data-tip]{position:relative}
  :root.tips-off [data-tip]:hover::after,:root.tips-off [data-tip]:hover::before{display:none!important}
  [data-tip]:hover::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);
    background:#0f1b2e;color:#e6edf6;border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:12px;
    white-space:nowrap;z-index:80;box-shadow:0 6px 20px rgba(0,0,0,.35);pointer-events:none}
  [data-tip]:hover::before{content:'';position:absolute;left:50%;bottom:calc(100% + 2px);transform:translateX(-50%);
    border:6px solid transparent;border-top-color:#0f1b2e;z-index:80;pointer-events:none}
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;font-family:system-ui,'Segoe UI',Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:14px}
  a{color:var(--accent)}
  /* ⚠️ `minmax(0,1fr)` και ΟΧΙ `1fr`: η στήλη του grid έχει εξ ορισμού
     `min-width:auto`, οπότε ένας φαρδύς πίνακας μεγάλωνε ΟΛΗ τη σελίδα αντί να
     κυλήσει μέσα της. Αποτέλεσμα: οριζόντια μπάρα κύλισης στο κάτω μέρος και —
     χειρότερα — το κουμπί ειδοποιήσεων και η «Έξοδος» έβγαιναν εκτός οθόνης,
     απάτητα. */
  .app{display:grid;grid-template-columns:var(--side) minmax(0,1fr);grid-template-rows:auto 1fr;grid-template-areas:"side top" "side main";height:100vh}
  /* Sidebar */
  /* Ακολουθεί το θέμα, όπως το πλαϊνό μενού της εφαρμογής υπολογιστή: με
     καρφωμένο σκούρο φόντο, το κείμενο (var(--txt)) γινόταν σκούρο-σε-σκούρο
     στο φωτεινό θέμα και η στήλη έμοιαζε άδεια. */
  aside{grid-area:side;background:var(--menu-bg);border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
  .brand{display:flex;align-items:center;gap:9px;padding:18px 18px 10px;font-size:18px;font-weight:800;letter-spacing:.3px}
  .brand-ic{width:28px;height:28px;border-radius:7px;flex:none}
  .brand span{color:var(--accent)}
  nav.menu{padding:8px;overflow:auto;flex:1}
  .nav-item{display:flex;align-items:center;gap:11px;padding:11px 13px;border-radius:10px;cursor:pointer;color:var(--muted);font-weight:600;margin-bottom:2px}
  .nav-item .ic{width:20px;text-align:center;font-size:16px}
  .nav-item:hover{background:var(--panel2);color:var(--txt)}
  /* Το χρώμα του ενεργού στοιχείου ακολουθεί το θέμα: στο σκούρο είναι σκούρο
     πάνω σε γαλάζιο, στο φωτεινό λευκό πάνω σε βαθύ μπλε. Με σταθερό #04222f η
     ενεργή ενότητα γινόταν δυσανάγνωστη στο φωτεινό θέμα. */
  .nav-item.active{background:var(--accent2);color:var(--on-accent)}
  .wiz .wiz-q{font-size:17px;font-weight:800;margin-bottom:14px}
  .wiz-opts{display:flex;gap:16px;flex-wrap:wrap}
  .wiz-card{flex:1;min-width:240px;display:flex;flex-direction:column;align-items:flex-start;gap:4px;text-align:left;
    padding:20px;border-radius:14px;border:1px solid var(--line);background:var(--panel2);color:var(--txt);cursor:pointer;transition:.15s}
  .wiz-card:hover{border-color:var(--accent);background:var(--hover);transform:translateY(-2px)}
  .wiz-card .wic{font-size:30px}
  .wiz-card b{font-size:16px}
  .wiz-card small{color:var(--muted);font-weight:500}
  .side-foot{padding:12px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
  .side-ver{display:flex;align-items:center;gap:6px;margin-top:8px;opacity:.85}
  /* Topbar */
  header{grid-area:top;display:flex;align-items:flex-end;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line);background:var(--header-bg);backdrop-filter:blur(6px)}
  /* Ό,τι είναι κείμενο στη μπάρα ΠΡΕΠΕΙ να μπορεί να στενέψει. Χωρίς αυτό, σε
     στενό παράθυρο το όνομα χρήστη έσπρωχνε τα κουμπιά έξω από την οθόνη. */
  header>.field{flex:0 1 auto;min-width:0}
  header #who{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  header #who b{display:inline-block;max-width:100%;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
  header .bell-wrap,header>button{flex:none;align-self:center}
  /* Ο επιλογέας εταιρείας έχει από πάνω ετικέτα, η αναζήτηση όχι: με
     `align-items:center` κάθονταν σε διαφορετικό ύψος. Ευθυγραμμίζονται στη
     ΒΑΣΗ τους, και τα δύο πλαίσια έχουν το ίδιο ύψος. */
  header>.field>select,.search-trigger{height:38px;box-sizing:border-box}
  .search-trigger{display:flex;align-items:center;gap:8px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:0 12px;color:var(--muted);cursor:text;min-width:0;flex:0 1 260px;overflow:hidden;white-space:nowrap}
  .search-trigger kbd{margin-left:auto;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:11px}
  .grow{flex:1}
  main{grid-area:main;overflow:auto;padding:20px}
  /* Μπάρες κύλισης: μία εμφάνιση σε όλη την εφαρμογή. Οι προεπιλεγμένες του
     browser έβγαιναν ΑΣΠΡΕΣ πάνω σε σκούρο θέμα — χτυπητές και ξένες. Το
     `color-scheme` τις βάφει και σε Firefox· ο κανόνας webkit δίνει το ακριβές
     σχήμα του πλαϊνού μενού. */
  :root{color-scheme:dark}
  :root[data-theme="light"]{color-scheme:light}
  *{scrollbar-width:thin;scrollbar-color:var(--line) transparent}
  ::-webkit-scrollbar{width:10px;height:10px}
  ::-webkit-scrollbar-track{background:transparent}
  ::-webkit-scrollbar-thumb{background:var(--line);border-radius:8px;border:2px solid transparent;background-clip:content-box}
  ::-webkit-scrollbar-thumb:hover{background:var(--muted);background-clip:content-box}
  ::-webkit-scrollbar-corner{background:transparent}
  /* Controls */
  select,input,button,textarea{font:inherit;color:var(--txt);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:9px 11px;outline:none}
  select:focus,input:focus,textarea:focus{border-color:var(--accent)}
  /* ⚠️ Οι επιλογές ενός `<select>` ζωγραφίζονται από το ΛΕΙΤΟΥΡΓΙΚΟ: κληρονομούν
     λευκό φόντο, ενώ το κείμενό μας είναι ανοιχτόχρωμο — αποτέλεσμα λευκό σε
     λευκό. Στον επιλογέα γλώσσας του βοηθού φαινόταν μόνο η μία από τις δύο
     γλώσσες. Τα χρώματα δίνονται ΡΗΤΑ. */
  select option{background:var(--panel);color:var(--txt)}
  button{cursor:pointer;transition:.15s}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent2);border-color:var(--accent2);color:var(--on-accent);font-weight:700}
  button.primary:hover{background:var(--accent)}
  button.danger{border-color:var(--bad);color:#fecaca}
  button.danger:hover{background:rgba(239,68,68,.15)}
  button.ghost{background:transparent}
  button.sm{padding:5px 9px;font-size:12px}
  /* Colored action buttons (distinct at a glance) */
  button.add{background:rgba(34,197,94,.16);border-color:#16a34a;color:#bbf7d0;font-weight:700}
  button.add:hover{background:rgba(34,197,94,.28)}
  button.tax{background:rgba(245,158,11,.16);border-color:#d97706;color:#fcd34d;font-weight:700}
  button.tax:hover{background:rgba(245,158,11,.28)}
  button.info{background:rgba(56,189,248,.16);border-color:var(--accent2);color:#bae6fd;font-weight:700}
  button.info:hover{background:rgba(56,189,248,.28)}
  /* Το PDF ενός παραστατικού ήταν ένας γαλάζιος σύνδεσμος «PDF» μέσα σε γραμμή
     πίνακα — δεν φαινόταν πατήσιμος και δεν έμοιαζε με τίποτα άλλο στην
     εφαρμογή. Είναι κουμπί, πράσινο, με εικονίδιο εγγράφου, όπως στη «Λήψη
     Παραστατικών». */
  a.docbtn,button.docbtn{display:inline-flex;align-items:center;gap:5px;padding:5px 9px;font-size:12px;
    border:1px solid #16a34a;border-radius:8px;background:rgba(34,197,94,.16);color:#bbf7d0;
    font-weight:700;text-decoration:none;cursor:pointer;white-space:nowrap}
  a.docbtn:hover,button.docbtn:hover{background:rgba(34,197,94,.28)}
  :root[data-theme="light"] a.docbtn,:root[data-theme="light"] button.docbtn{background:#dcfce7;color:#166534}
  :root[data-theme="light"] a.docbtn:hover,:root[data-theme="light"] button.docbtn:hover{background:#bbf7d0}
  .view{display:none;animation:fade .2s}
  .view.active{display:block}
  @keyframes fade{from{opacity:0;transform:translateY(4px)}to{opacity:1}}
  .panel{background:var(--panel2);border:1px solid var(--line);border-radius:var(--radius);padding:18px;box-shadow:var(--shadow)}
  h2.title{margin:0 0 4px;font-size:20px}
  .sub{color:var(--muted);margin:0 0 16px;font-size:13px}
  .row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
  .field{display:flex;flex-direction:column;gap:4px}
  .field.grow{flex:1;min-width:160px}
  .field label{font-size:12px;color:var(--muted)}
  /* Data grid — timologio-downloader look: sticky header, zebra rows, hover */
  table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
  th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
  thead th{position:sticky;top:0;z-index:2;background:var(--panel);color:var(--muted);font-weight:700;
    font-size:11px;text-transform:uppercase;letter-spacing:.4px;border-bottom:2px solid var(--line)}
  tbody tr:nth-child(even){background:rgba(148,163,184,.05)}
  tbody tr:hover{background:var(--hover)}
  tbody tr:last-child td{border-bottom:none}
  table.sortable thead th{cursor:pointer;user-select:none}
  table.sortable thead th:hover{color:var(--accent)}
  tr.clickable{cursor:pointer}
  /* Per-column dropdown filters (Excel-style) */
  /* Χωνί φίλτρου, ακριβώς όπως στη «Λήψη Παραστατικών»: δεξιά στην κεφαλίδα,
     αόρατο μέχρι να περάσει από πάνω ο δείκτης — και μόνιμα χρωματισμένο όταν η
     στήλη είναι φιλτραρισμένη. Έτσι οι κεφαλίδες μένουν καθαρές αντί να
     κουβαλούν ένα ▾ σε κάθε στήλη. */
  th{position:relative}
  .filter-btn{position:absolute;right:4px;top:50%;transform:translateY(-50%);
    width:18px;height:18px;display:flex;align-items:center;justify-content:center;
    cursor:pointer;border-radius:4px;color:var(--muted);opacity:0;transition:opacity .12s,color .12s}
  .filter-btn svg{width:11px;height:11px;fill:currentColor}
  th:hover .filter-btn{opacity:1}
  .filter-btn:hover{color:var(--accent);background:var(--panel2)}
  .filter-btn.active{opacity:1;color:var(--accent)}
  /* Λαβή αλλαγής πλάτους στο δεξί όριο της κεφαλίδας + ένδειξη προορισμού όταν
     σέρνεται στήλη. */
  /* Γραφήματα στατιστικών (σκέτο SVG, χωρίς βιβλιοθήκη) */
  svg.chart{width:100%;max-width:820px;height:auto}
  svg.chart.pie{max-width:320px;display:block;margin:0 auto}
  svg.chart .cx-lbl{fill:var(--txt);font-size:12px}
  svg.chart .cx-val{fill:var(--muted);font-size:11px}
  /* Διαχείριση: ο διαχωρισμός «τι βλέπω» πρέπει να είναι το πρώτο πράγμα. */
  .scope-banner{border-left:4px solid var(--accent2)}
  .scope-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
  .scope-warn{margin-top:8px;padding:8px 10px;border-radius:8px;background:rgba(245,158,11,.14);
    border:1px solid #d97706;color:var(--txt);font-size:13px}
  .np-list{display:flex;flex-direction:column;gap:2px}
  .chart-legend{display:flex;flex-wrap:wrap;gap:8px 18px;margin-top:12px;font-size:12px;color:var(--txt)}
  .cl-item{display:inline-flex;align-items:center;gap:6px}
  .cl-item i{width:11px;height:11px;border-radius:3px;display:inline-block}
  /* Η στήλη με τα κουμπιά έπαιρνε ίσο μερίδιο πλάτους σαν να ήταν κείμενο, τα
     κουμπιά δεν χωρούσαν και ΚΑΒΑΛΟΥΣΑΝ τη διπλανή στήλη. Παίρνει όσο ακριβώς
     χρειάζεται (`width:1%` σε auto layout = shrink-to-fit) και δεν σπάει. */
  td.right,th.nofilter{white-space:nowrap;width:1%}
  td.right>button,td.right>a{vertical-align:middle}
  td.right>button+button,td.right>a+button,td.right>button+a{margin-left:4px}
  /* Τα κελιά κειμένου κόβονται με «…» αντί να σπρώχνουν τον πίνακα. */
  table td{overflow:hidden;text-overflow:ellipsis}
  /* Το σήμα του γραφείου ζει ΜΕΣΑ στο υποσέλιδο του μενού. Ως fixed στοιχείο
     καθόταν πάνω στη γραμμή της έκδοσης· εδώ είναι εξίσου «κάτω αριστερά»
     χωρίς να σκεπάζει τίποτα. Και ποτέ δεν πιάνει κλικ (το μάθαμε από το toast). */
  /* Σύνδεσμος πλέον — άρα ΧΡΕΙΑΖΕΤΑΙ κλικ, σε αντίθεση με το toast. Το
     `display:block` το κρατά στο δικό του πλάτος αντί για όλη τη γραμμή. */
  #brandMark{display:block;width:max-content;margin-top:10px;opacity:.72;transition:opacity .15s}
  #brandMark:hover{opacity:1}
  #brandMark img{display:none;width:74px;height:auto}
  /* Η ειδικότητα του id νικά κάθε κανόνα με σκέτη κλάση — γι' αυτό η εναλλαγή
     θέματος γράφεται ΚΙ ΑΥΤΗ μέσα από το id. Χωρίς αυτό το λογότυπο έμενε
     κρυμμένο ό,τι κι αν έλεγε το θέμα. */
  #brandMark .bm-dark{display:block}     /* σκούρο θέμα → σκούρα εκδοχή */
  :root[data-theme="light"] #brandMark .bm-dark{display:none}
  :root[data-theme="light"] #brandMark .bm-light{display:block}
  th.sortable-th{cursor:pointer;user-select:none}
  th.sortable-th:hover{color:var(--accent)}
  .grid-sort{font-size:10px;color:var(--accent)}
  .col-grip{position:absolute;right:-3px;top:0;width:7px;height:100%;cursor:col-resize;z-index:2}
  .col-grip:hover{background:var(--accent2);opacity:.5}
  th.col-drop{box-shadow:inset 3px 0 0 var(--accent2)}
  th[draggable="true"]{cursor:grab}
  #colFilterPop{position:fixed;z-index:210;width:290px;max-width:92vw;background:var(--panel);border:1px solid var(--line);
    border-radius:12px;box-shadow:var(--shadow);padding:14px;display:none}
  #colFilterPop.on{display:block}
  #colFilterPop h5 h5{margin:0 0 10px;font-size:14px;color:var(--accent);font-weight:700}
  #colFilterPop .cf-search .cf-search{width:100%;padding:8px 10px;border:1px solid var(--line);border-radius:9px;background:var(--bg);color:var(--txt);font-size:13px;margin-bottom:10px}
  #colFilterPop .cf-search:focus .cf-search:focus{outline:none;border-color:var(--accent)}
  #colFilterPop .cf-list .cf-list{max-height:230px;overflow:auto;display:flex;flex-direction:column;gap:1px}
  #colFilterPop .cf-item .cf-item{display:flex;align-items:center;gap:9px;padding:6px 8px;border-radius:7px;font-size:13px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #colFilterPop .cf-item:hover .cf-item:hover{background:var(--hover)}
  #colFilterPop .cf-item input .cf-item input{accent-color:var(--accent);flex:0 0 auto}
  #colFilterPop .cf-actions .cf-actions{display:flex;gap:8px;margin-top:12px}
  #colFilterPop .cf-actions button .cf-actions button{flex:1}
  th.grid-check,td.grid-check{width:34px;text-align:center;padding-left:6px;padding-right:6px}
  /* Guided page tour */
  #tourOverlay{position:fixed;inset:0;z-index:200;display:none}
  #tourOverlay.on{display:block}
  #tourBackdrop{position:absolute;inset:0;background:transparent}
  #tourRing{position:absolute;border:2px solid var(--accent);border-radius:12px;box-shadow:0 0 0 9999px rgba(3,10,20,.55),0 0 22px rgba(56,189,248,.6);transition:all .25s ease;pointer-events:none}
  #tourBox{position:absolute;max-width:340px;background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);padding:16px 18px;z-index:201}
  #tourBox h4{margin:0 0 6px;font-size:15px}
  #tourBox p{margin:0 0 12px;font-size:13px;color:var(--muted);line-height:1.45}
  #tourBox .tour-actions{display:flex;gap:8px;align-items:center}
  #tourBox .tour-step{font-size:11px;color:var(--muted);margin-left:auto}
  .num{text-align:right;font-variant-numeric:tabular-nums}
  .cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:4px 0}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:15px 17px}
  .card .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.5px}
  .card .v{font-size:25px;font-weight:800;margin-top:4px}
  .card .v.money{color:var(--accent)}
  .pill{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;background:var(--chip);border:1px solid var(--line)}
  .pill.ok{background:rgba(34,197,94,.12);border-color:#16653433;color:#86efac}
  .pill.bad{background:rgba(239,68,68,.12);color:#fca5a5}
  .pill.warn{background:rgba(245,158,11,.12);color:#fcd34d}
  .muted{color:var(--muted)} .right{text-align:right}
  .hint{font-size:12px;color:var(--muted)}
  .seg{display:inline-flex;border:1px solid var(--line);border-radius:9px;overflow:hidden}
  .seg button{border:none;border-radius:0;border-right:1px solid var(--line)}
  .seg button:last-child{border-right:none}
  .seg button.on{background:var(--accent2);color:#04222f;font-weight:700}
  .bar{height:8px;border-radius:4px;background:#0b2942;overflow:hidden;width:160px}
  .bar>i{display:block;height:100%;background:linear-gradient(90deg,var(--accent2),var(--accent))}
  .balance.pos{color:#fca5a5} .balance.zero{color:#86efac}
  .spin{display:inline-block;width:14px;height:14px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:sp .7s linear infinite;vertical-align:-2px}
  @keyframes sp{to{transform:rotate(360deg)}}
  /* Toast */
  /* ⚠️ `pointer-events:none`. Το toast κάθεται ΑΚΡΙΒΩΣ πάνω από το κουδουνάκι
     και την «Έξοδο», και ένα ορατό (ή ακόμη και διάφανο) μήνυμα κατάπινε το
     κλικ. Επειδή μήνυμα εμφανίζεται κάθε φορά που κάτι αποτυγχάνει — π.χ. όταν
     δεν έχει επιλεγεί πελάτης — τα δύο κουμπιά έμοιαζαν νεκρά ακριβώς τότε που
     τα χρειαζόσουν. Το toast δεν είναι διαδραστικό: δεν έχει λόγο να δέχεται
     κλικ ποτέ. */
  /* --- Μικρές οθόνες ------------------------------------------------------
     Η εφαρμογή σχεδιάστηκε για γραφείο, αλλά ο λογιστής την ανοίγει και από
     κινητό για να δει ένα υπόλοιπο ή να στείλει ένα PDF. Δύο σκαλοπάτια: σε
     tablet στενεύει το πλαϊνό μενού, σε κινητό γίνεται οριζόντια μπάρα πάνω
     από το περιεχόμενο και η κεφαλίδα σπάει σε δύο σειρές. */
  @media (max-width:1024px){
    :root{--side:190px}
    .search-trigger{flex:0 1 180px}
    header #who{display:none}          /* ό,τι είναι διακοσμητικό φεύγει πρώτο */
  }
  @media (max-width:760px){
    .app{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto 1fr;
         grid-template-areas:"side" "top" "main";height:auto;min-height:100vh}
    /* Το πρόθεμα `body` ανεβάζει την ειδικότητα: οι γενικοί κανόνες της μπάρας
       γράφονται ΠΙΟ ΚΑΤΩ στο φύλλο και αλλιώς θα κέρδιζαν μέσα στο media. */
    body .app.offline{grid-template-rows:auto auto auto 1fr;
                      grid-template-areas:"net" "side" "top" "main"}
    body #netBar{padding:8px 12px;font-size:12.5px;flex-wrap:wrap}
    aside{flex-direction:row;flex-wrap:wrap;align-items:center;gap:4px;
          border-right:none;border-bottom:1px solid var(--line);padding:6px 10px}
    .brand{padding:6px 8px;font-size:15px}
    /* ⚠️ ΜΙΑ σειρά που κυλά, όχι αναδίπλωση: με `flex-wrap` οι 14 ενότητες
       γίνονταν μπλοκ 594px και έσπρωχναν την κεφαλίδα στο κάτω μέρος της
       οθόνης — ακριβώς κάτω από το πλωτό κουμπί του βοηθού, που σκέπαζε την
       «Έξοδο». */
    .menu{display:flex;flex-wrap:nowrap;gap:4px;overflow-x:auto;padding:0 0 4px;
          scroll-snap-type:x proximity;-webkit-overflow-scrolling:touch}
    .nav-item{padding:7px 10px;font-size:13px;white-space:nowrap;flex:none;scroll-snap-align:start}
    .nav-item .ic{margin-right:2px}
    /* Οι διακόπτες και το υποσέλιδο δεν χωρούν σε μπάρα — ζουν στις Ρυθμίσεις. */
    .side-controls,.side-foot{display:none}
    header{flex-wrap:wrap;gap:8px;padding:10px 12px}
    header>.field{flex:1 1 100%}
    .search-trigger{flex:1 1 100%}
    main{padding:12px}
    .panel{padding:12px}
    /* Οι πίνακες κυλούν μέσα στο πλαίσιό τους, δεν σπρώχνουν τη σελίδα. */
    .panel table{display:block;overflow-x:auto;white-space:nowrap}
    .row{flex-wrap:wrap}
    .field{min-width:0}
    dialog .modal-body{max-width:96vw!important;padding:14px}
    #cbPanel{right:8px;left:8px;width:auto;bottom:86px}
    .toast{left:10px;right:10px;max-width:none}
    .notif-panel{width:min(360px,92vw);right:-8px}
  }
  .toast{pointer-events:none;position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);padding:12px 16px;border-radius:10px;box-shadow:var(--shadow);z-index:90;max-width:380px;opacity:0;transform:translateY(-10px);transition:.25s}
  .toast.show{opacity:1;transform:none}
  .toast.ok{border-left-color:var(--ok)} .toast.err{border-left-color:var(--bad)}
  /* Η απώλεια σύνδεσης είναι ΚΑΤΑΣΤΑΣΗ, όχι συμβάν: ένα toast που φεύγει σε
     τρία δευτερόλεπτα αφήνει τον χρήστη να νομίζει ότι φταίει η εφαρμογή.
     Η μπάρα μένει όσο κρατά το πρόβλημα και φεύγει μόνη της μόλις λυθεί. */
  #netBar{grid-area:net;display:none;align-items:center;gap:12px;padding:10px 18px;
    background:rgba(239,68,68,.14);border-bottom:1px solid var(--bad);color:var(--txt);
    font-size:13.5px;z-index:95}
  #netBar.on{display:flex}
  #netBar .nb-dot{width:9px;height:9px;border-radius:50%;background:var(--bad);flex:none;
    animation:nbPulse 1.4s ease-in-out infinite}
  @keyframes nbPulse{0%,100%{opacity:1}50%{opacity:.25}}
  #netBar b{color:var(--bad)}
  #netBar .grow{flex:1}
  /* Όταν φαίνεται η μπάρα, χρειάζεται δική της γραμμή στο πλέγμα — αλλιώς
     καθόταν πάνω στην κεφαλίδα. */
  .app.offline{grid-template-rows:auto auto 1fr;grid-template-areas:"side net" "side top" "side main"}
  /* Dialog */
  dialog{background:var(--panel);color:var(--txt);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);max-width:560px;width:94%;padding:0}
  dialog::backdrop{background:rgba(3,8,16,.66)}
  .modal-body{padding:20px} .modal-head{font-weight:700;font-size:17px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
  .tabset{display:flex;gap:6px;margin-bottom:12px}
  .tabset button{flex:1}
  .tabset button.on{background:var(--accent2);color:#04222f;font-weight:700;border-color:var(--accent2)}
  /* Command palette */
  #palette{position:fixed;inset:0;background:rgba(3,8,16,.6);z-index:100;display:none;align-items:flex-start;justify-content:center}
  #palette.open{display:flex}
  .pal-box{margin-top:12vh;width:min(620px,92%);background:var(--panel);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow);overflow:hidden}
  .pal-box input{width:100%;border:none;border-bottom:1px solid var(--line);border-radius:0;padding:16px 18px;font-size:16px;background:transparent}
  .pal-results{max-height:50vh;overflow:auto}
  .pal-row{padding:12px 18px;cursor:pointer;display:flex;gap:10px;align-items:center;border-bottom:1px solid var(--line)}
  .pal-row:hover,.pal-row.sel{background:var(--accent2);color:#04222f}
  .pal-row small{color:var(--muted)} .pal-row.sel small{color:#04343f}
  /* Autocomplete dropdown (customers/products on issue) */
  .ac-panel{position:absolute;top:100%;left:0;right:0;z-index:40;background:var(--panel);border:1px solid var(--line);border-radius:10px;box-shadow:var(--shadow);max-height:260px;overflow:auto;display:none;margin-top:4px}
  .ac-panel.open{display:block}
  .ac-row{padding:9px 12px;cursor:pointer;border-bottom:1px solid var(--line);display:flex;gap:10px;align-items:baseline}
  .ac-row:last-child{border-bottom:none}
  .ac-row:hover,.ac-row.sel{background:var(--accent2);color:#04222f}
  .ac-row small{color:var(--muted)} .ac-row:hover small,.ac-row.sel small{color:#04343f}
  .ln-desc{font-size:11px;color:var(--muted);margin-top:2px}
  /* Notifications bell + feed */
  .bell-badge{position:absolute;top:-6px;right:-6px;min-width:17px;height:17px;padding:0 4px;border-radius:999px;
    background:var(--bad);color:#fff;font-size:10px;font-weight:700;line-height:17px;text-align:center;box-shadow:0 0 0 2px var(--bg)}
  .notif-panel{position:absolute;top:38px;right:0;width:380px;max-height:70vh;overflow:auto;background:var(--panel);
    border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);z-index:70}
  .notif-head{display:flex;align-items:center;gap:6px;padding:10px 12px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--panel);border-radius:12px 12px 0 0}
  .notif-list{padding:4px}
  .notif-item{padding:9px 10px;border-radius:9px;border:1px solid transparent;cursor:default}
  .notif-item:hover{background:var(--hover)}
  .notif-item.unread{background:var(--chip);border-color:var(--line)}
  .notif-item .nt-top{display:flex;align-items:baseline;gap:6px}
  .notif-item .nt-amt{margin-left:auto;font-weight:700;color:var(--accent)}
  .notif-item .nt-sub{font-size:11px;color:var(--muted);margin-top:2px}
  .notif-item .nt-mark{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px;color:var(--muted);word-break:break-all}
  .notif-empty{padding:18px;text-align:center;color:var(--muted)}
  select.rolesel{padding:3px 6px;font-size:12px;border-radius:8px;background:var(--panel2);color:var(--txt);border:1px solid var(--line)}
  .np-check{display:flex;align-items:center;gap:8px;padding:4px 2px;cursor:pointer;font-size:13px}
  .np-check input{width:16px;height:16px;accent-color:var(--accent)}
  .sched-status{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .sched-status.pending{background:#0b2942;color:var(--accent)}
  .sched-status.done{background:#052e1b;color:var(--ok)}
  .sched-status.failed{background:#3a0d12;color:var(--bad)}
  .sched-status.running{background:#3a2c07;color:var(--warn)}
  .sched-status.cancelled{background:var(--panel2);color:var(--muted)}
  :root[data-theme="light"] .sched-status.pending{background:#e0f2fe;color:#075985}
  :root[data-theme="light"] .sched-status.done{background:#dcfce7;color:#166534}
  :root[data-theme="light"] .sched-status.failed{background:#fee2e2;color:#b91c1c}
  :root[data-theme="light"] .sched-status.running{background:#fef3c7;color:#92400e}
  /* Το «ματάκι» των κωδικών — ίδιο με της οθόνης σύνδεσης (authview.php). */
  .pw{position:relative;display:block}
  .pw input{width:100%;padding-right:42px}
  .pw .eye{position:absolute;top:50%;right:6px;transform:translateY(-50%);width:30px;height:30px;
    display:flex;align-items:center;justify-content:center;background:none;border:0;cursor:pointer;
    color:var(--muted);font-size:15px;line-height:1;padding:0;border-radius:7px}
  .pw .eye:hover{color:var(--accent);background:rgba(56,189,248,.12)}
  /* Μέσα στην desktop εφαρμογή το πλαϊνό μενού υπάρχει ήδη (native, με τα δικά
     του εικονίδια και συντομεύσεις). Δύο μενού δίπλα-δίπλα είναι σκέτη σύγχυση:
     κρύβουμε το δικό μας και αφήνουμε όλο το πλάτος στο περιεχόμενο. */
  body.embedded aside{display:none}
  body.embedded .app{grid-template-columns:minmax(0,1fr);grid-template-areas:"top" "main"}
  body.embedded .app.offline{grid-template-rows:auto auto 1fr;grid-template-areas:"net" "top" "main"}
</style>
</head>
<body class="<?= $__embedded ? 'embedded' : '' ?>">
<div class="app">
  <aside>
    <div class="brand"><img src="assets/icons/app-icon-192.png" alt="" class="brand-ic">e-Timologio <span>Pro</span></div>
    <nav class="menu" id="menu">
      <div class="nav-item active" data-view="issue"><span class="ic">🧾</span> Έκδοση</div>
      <div class="nav-item" data-view="bulk"><span class="ic">📚</span> Μαζική έκδοση</div>
      <div class="nav-item" data-view="customers"><span class="ic">👥</span> Πελάτες</div>
      <div class="nav-item" data-view="card"><span class="ic">📇</span> Καρτέλα</div>
      <div class="nav-item" data-view="documents"><span class="ic">📄</span> Παραστατικά</div>
      <div class="nav-item" data-view="bankimp"><span class="ic">🏦</span> Εισαγωγή πληρωμών</div>
      <div class="nav-item" data-view="products"><span class="ic">📦</span> Είδη</div>
      <div class="nav-item" data-view="series"><span class="ic">🔢</span> Σειρές</div>
      <div class="nav-item" data-view="drafts"><span class="ic">📝</span> Πρόχειρα</div>
      <div class="nav-item" data-view="cancel"><span class="ic">↩️</span> Ακύρωση</div>
      <div class="nav-item" data-view="schedule"><span class="ic">⏰</span> Προγραμματισμός</div>
      <div class="nav-item" data-view="stats"><span class="ic">📊</span> Στατιστικά</div>
      <div class="nav-item" data-view="settings"><span class="ic">⚙️</span> Ρυθμίσεις</div>
      <?php if (in_array($__role, ['master','editor'], true)): ?>
      <div class="nav-item" data-view="admin"><span class="ic">🛡️</span> Διαχείριση</div>
      <?php endif; ?>
    </nav>
    <div class="side-controls">
      <div class="side-actions">
        <button class="ghost sm side-act" id="btnTour" onclick="startTour()" data-tip="Γρήγορη ξενάγηση στην εφαρμογή">🧭 Ξενάγηση</button>
        <button class="ghost sm side-act" id="btnManual" onclick="downloadManual()" data-tip="Κατέβασε το εγχειρίδιο χρήσης (PDF)">📄 Εγχειρίδιο</button>
      </div>
      <div class="side-sec">ΡΥΘΜΙΣΕΙΣ</div>
      <div class="side-toggle" id="themeToggle" onclick="toggleTheme()" data-tip="Εναλλαγή ανάμεσα σε σκούρο και φωτεινό">
        <span class="tt-switch"><span class="tt-knob"></span></span><span id="themeLbl">Φωτεινό θέμα</span></div>
      <div class="side-toggle on" id="tipsToggle" onclick="toggleTips()" data-tip="Εμφάνιση επεξηγήσεων όταν αφήνετε τον δείκτη πάνω από ένα κουμπί">
        <span class="tt-switch"><span class="tt-knob"></span></span><span id="tipsLbl">Βοηθητικά μηνύματα</span></div>
    </div>
    <div class="side-foot">🔒 Τοπικά δεδομένα κρυπτογραφημένα<br>Πάτα <b>Ctrl+K</b> για γρήγορη αναζήτηση
      <?php /* Κάτω αριστερά στέκεται ΜΟΝΟ το σήμα του γραφείου. Το όνομα του
               προϊόντος γράφεται ήδη στην κορυφή του μενού· εδώ μένει μόνο ο
               αριθμός έκδοσης, που χρειάζεται όποιος ζητά υποστήριξη. */ ?>
      <?php if ($__version !== ''): ?>
      <div class="side-ver">έκδοση <?= htmlspecialchars($__version, ENT_QUOTES) ?></div>
      <?php endif; ?>
      <a id="brandMark" href="https://scanmydata.gr" target="_blank" rel="noopener noreferrer"
         title="scanmydata.gr">
        <img src="assets/brand/scanmydata-light.png" alt="ScanmyData" class="bm-light">
        <img src="assets/brand/scanmydata-dark.png" alt="ScanmyData" class="bm-dark">
      </a></div>
  </aside>

  <div id="netBar" role="status" aria-live="polite">
    <span class="nb-dot"></span>
    <span><b>Δεν υπάρχει σύνδεση στο internet.</b>
      <span id="netBarWhy">Η έκδοση παραστατικών και κάθε κλήση προς την ΑΑΔΕ θα αποτύχει. Τα τοπικά δεδομένα (πελάτες, πληρωμές, πρόχειρα) δουλεύουν κανονικά.</span></span>
    <span class="grow"></span>
    <button class="ghost sm" id="netBarRetry" onclick="netRecheck(true)">↻ Έλεγχος ξανά</button>
  </div>

  <header>
    <div class="field" style="min-width:230px">
      <label class="hint">Λογαριασμός (επιχείρηση)</label>
      <select id="account"></select>
    </div>
    <div class="search-trigger" onclick="openPalette()">🔍 Αναζήτηση πελάτη… <kbd>Ctrl K</kbd></div>
    <div class="grow"></div>
    <span id="who" class="hint" style="text-align:right;line-height:1.3">
      <b><?= htmlspecialchars($__business ?: $__email, ENT_QUOTES) ?></b><br>
      <span class="muted"><?= htmlspecialchars($__email, ENT_QUOTES) ?><?= $__role==='master'?' · 🛡️ admin':'' ?></span>
    </span>
    <div class="bell-wrap" style="position:relative;margin-left:8px">
      <button class="ghost sm bell-btn" onclick="toggleNotifPanel()" data-tip="Ειδοποιήσεις εκδόσεων παραστατικών" style="position:relative">🔔<span id="bellBadge" class="bell-badge" hidden>0</span></button>
      <div id="notifPanel" class="notif-panel" hidden>
        <div class="notif-head"><b>Ειδοποιήσεις</b><span class="grow"></span>
          <button class="ghost sm" onclick="notifMarkAll()" title="Σήμανση όλων ως αναγνωσμένων">✓ Όλα</button>
          <button class="ghost sm" onclick="checkAadeNewDocs(false).then(loadNotifications)" title="Σύγκριση με την πλατφόρμα της ΑΑΔΕ: ειδοποίηση για κάθε παραστατικό που δεν εκδόθηκε από εδώ">🛰️ Έλεγχος ΑΑΔΕ</button>
          <button class="ghost sm" onclick="loadNotifications()" title="Ανανέωση">↻</button></div>
        <div id="notifList" class="notif-list"><div class="notif-empty">—</div></div>
      </div>
    </div>
    <button class="ghost sm" onclick="logout()" title="Αποσύνδεση" style="margin-left:6px">Έξοδος</button>
  </header>

  <main>
    <!-- STATS -->
    <section class="view" id="view-stats">
      <h2 class="title">Στατιστικά</h2><p class="sub">Σύνοψη τζίρου & παραστατικών από την ΑΑΔΕ.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <div class="seg" id="statPeriod">
            <button data-p="month" class="on">Τρέχων μήνας</button>
            <button data-p="preMonth">Προηγ. μήνας</button>
            <button data-p="year">Τρέχον έτος</button>
          </div>
          <div class="seg" id="statChart">
            <button data-c="table" class="on" data-tip="Αναλυτικός πίνακας">📋 Πίνακας</button>
            <button data-c="bar" data-tip="Ράβδοι ανά τύπο παραστατικού">📊 Ράβδοι</button>
            <button data-c="pie" data-tip="Μερίδιο κάθε τύπου στον τζίρο">🥧 Πίτα</button>
          </div>
          <button class="ghost" onclick="loadStats()">↻ Ανανέωση</button>
        </div>
        <div class="cards" id="statCards" style="margin-top:14px"></div>
        <div id="statGraph" style="display:none;margin-top:10px"></div>
        <table id="statTable"><thead><tr><th>Τύπος</th><th class="num">Πλήθος</th><th class="num">Αξία (€)</th><th>Μερίδιο</th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- CUSTOMERS -->
    <section class="view" id="view-customers">
      <h2 class="title">Πελάτες</h2><p class="sub">Έξυπνη αναζήτηση & διαχείριση πελατολογίου.</p>
      <div class="panel">
        <div class="row">
          <div class="field grow"><label>Αναζήτηση (ΑΦΜ / επωνυμία / κωδικός)</label>
            <input id="custSearch" placeholder="Πληκτρολόγησε…" autocomplete="off"></div>
          <button class="primary" onclick="loadCustomers()">Αναζήτηση</button>
          <button class="ghost" onclick="loadCustomers(true)">Όλοι</button>
          <button class="ghost" onclick="zipAllInvoices()">🗜️ ZIP όλων (έτος)</button>
          <button class="primary" onclick="openCustomerModal()">+ Νέος πελάτης</button>
        </div>
        <div class="hint" id="custCount"></div>
        <table id="custTable" class="sortable"><thead><tr>
          <th onclick="sortCustomers('code')" id="cs-code">Κωδ.<span class="sort-ind" id="si-code"></span></th>
          <th onclick="sortCustomers('vat')" id="cs-vat">ΑΦΜ<span class="sort-ind" id="si-vat"></span></th>
          <th onclick="sortCustomers('name')" id="cs-name">Επωνυμία<span class="sort-ind" id="si-name"></span></th>
          <th onclick="sortCustomers('city')" id="cs-city">Πόλη<span class="sort-ind" id="si-city"></span></th>
          <th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- CARD -->
    <section class="view" id="view-card">
      <h2 class="title">Καρτέλα πελάτη</h2><p class="sub">Τιμολόγια ΑΑΔΕ + τοπικές πληρωμές + τρέχον υπόλοιπο.</p>
      <div class="panel">
        <div class="row" style="position:relative">
          <div class="field grow" style="min-width:260px"><label>Πελάτης</label><input id="cardCust" placeholder="Αναζήτηση με επωνυμία ή ΑΦΜ…" autocomplete="off" oninput="cardAc(this)" onfocus="cardAc(this)"><div id="cardAcPanel" class="ac-panel"></div></div>
          <input id="cardVat" type="hidden">
          <div class="field"><label>Από</label><input id="cardFrom" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <div class="field"><label>Έως</label><input id="cardTo" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <button class="primary" onclick="loadCard()">Φόρτωση</button>
          <button class="ghost" onclick="openPaymentModal()">+ Πληρωμή</button>
          <button class="ghost" onclick="ledgerPdf()">📄 PDF καρτέλας</button>
          <button class="ghost" onclick="emailLedger()" data-tip="Στέλνει την καρτέλα στον πελάτη — με προεπισκόπηση κειμένου πριν φύγει">✉️ Αποστολή καρτέλας</button>
          <button class="ghost" onclick="openLedgerBulk()" data-tip="Καρτέλες σε πολλούς πελάτες μαζί, με φίλτρο για όσους χρωστούν">📨 Μαζική αποστολή</button>
          <button class="ghost" onclick="printCustomerInvoices()" data-tip="Προεπισκόπηση &amp; εκτύπωση όλων των παραστατικών του πελάτη">🖨️ Μαζική εκτύπωση</button>
          <button class="ghost" onclick="zipCustomerInvoices()" data-tip="Πακετάρει τα PDF της καρτέλας σε ένα ZIP">🗜️ ZIP παραστατικών</button>
        </div>
        <div id="cardHead" style="margin-top:12px"></div>
        <div class="cards" id="cardCards"></div>
        <table id="cardTable"><thead><tr><th>Ημ/νία</th><th>Κίνηση</th><th>Στοιχεία</th><th class="num">Χρέωση</th><th class="num">Πίστωση</th><th class="num">Υπόλοιπο</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- DOCUMENTS (όλα τα παραστατικά του έτους) -->
    <section class="view" id="view-documents">
      <h2 class="title">Παραστατικά</h2>
      <p class="sub">Όλα τα εκδοθέντα παραστατικά της περιόδου. Τσέκαρε όσα θέλεις και τύπωσέ τα μαζί ή κατέβασέ τα σε ZIP.</p>
      <div class="panel">
        <div class="row">
          <div class="field"><label>Από</label><input id="docFrom" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <div class="field"><label>Έως</label><input id="docTo" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <div class="field grow"><label>Αναζήτηση (ΑΦΜ / επωνυμία / ΜΑΡΚ / σειρά)</label><input id="docSearch" placeholder="Πληκτρολόγησε…" autocomplete="off" oninput="renderDocs()"></div>
          <button class="primary" onclick="loadDocs()">Αναζήτηση</button>
          <button class="ghost" onclick="docsYear()" data-tip="Επαναφορά στο τρέχον έτος">📅 Τρέχον έτος</button>
        </div>
        <div class="row" style="align-items:center;margin-top:6px">
          <span class="hint" id="docCount"></span>
          <div class="grow"></div>
          <button class="ghost sm" onclick="docToggleAll(true)">Επιλογή όλων</button>
          <button class="ghost sm" onclick="docToggleAll(false)">Καμία</button>
          <button class="ghost" onclick="printSelectedDocs()" data-tip="Προεπισκόπηση &amp; εκτύπωση των επιλεγμένων">🖨️ Μαζική εκτύπωση</button>
          <button class="ghost" onclick="zipSelectedDocs()" data-tip="Πακετάρει τα επιλεγμένα σε ένα ZIP">🗜️ Εξαγωγή ZIP</button>
        </div>
        <table id="docTable" style="margin-top:10px"><thead><tr>
          <th class="grid-check" style="width:34px"><input type="checkbox" id="docAll" onchange="docToggleAll(this.checked)"></th>
          <th>Ημ/νία</th><th>Τύπος</th><th>Σειρά</th><th>Α/Α</th><th>Πελάτης</th>
          <th class="num">Καθαρή</th><th class="num">ΦΠΑ</th><th class="num">Σύνολο</th><th>ΜΑΡΚ</th><th class="nofilter"></th>
        </tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- BANK IMPORT -->
    <section class="view" id="view-bankimp">
      <h2 class="title">Εισαγωγή κινήσεων τραπέζης</h2>
      <p class="sub">Ανέβασε extrait (CSV/XLSX) — κάθε <b>κατάθεση</b> γίνεται υποψήφια πληρωμή πελάτη. Το ποσό κατάθεσης <b>δεν</b> «κλείνει» υπόλοιπο· καταχωρείται όπως είναι (μερική/υπερβάλλουσα επιτρέπονται).</p>
      <!-- Μεμονωμένη καταχώρηση: όχι κάθε είσπραξη έρχεται από extrait — μετρητά
           και επιταγές μπαίνουν με το χέρι, συχνά πολλές στη σειρά. -->
      <div class="panel">
        <div class="row" style="justify-content:space-between;align-items:center">
          <div><strong>✍️ Μεμονωμένη είσπραξη</strong>
            <div class="sub">Μία πληρωμή με το χέρι — με «επαναλαμβανόμενη εισαγωγή» η φόρμα μένει ανοιχτή και κρατά τον πελάτη για την επόμενη.</div></div>
          <button class="primary" onclick="openManualPayment()">+ Νέα πληρωμή</button>
        </div>
        <div id="pmRecent" class="hint" style="margin-top:8px"></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="row">
          <div class="field"><label>Τράπεζα</label>
            <select id="biBank">
              <option value="">Αυτόματα</option>
              <option value="eurobank">Eurobank</option>
              <option value="optima">Optima</option>
              <option value="ethniki">Εθνική (NBG)</option>
              <option value="generic">Άλλη (γενικό)</option>
            </select></div>
          <div class="field grow"><label>Αρχείο extrait (.csv / .xlsx)</label>
            <input id="biFile" type="file" accept=".csv,.xlsx,.txt"></div>
          <button class="primary" onclick="biPreview()">🔎 Ανάλυση</button>
        </div>
        <div class="hint" id="biInfo"></div>
        <div class="row" id="biBar" style="display:none;gap:14px;align-items:center;margin-top:6px">
          <label style="display:flex;gap:6px;align-items:center"><input type="checkbox" id="biOnlyCredit" checked onchange="biRender()"> Μόνο εισπράξεις (καταθέσεις)</label>
          <span class="hint" id="biSel"></span>
          <div style="flex:1"></div>
          <button class="ghost sm" onclick="biToggleAll(true)">Επιλογή όλων</button>
          <button class="ghost sm" onclick="biToggleAll(false)">Καμία</button>
          <button class="primary" onclick="biImport()">💾 Καταχώρηση επιλεγμένων</button>
        </div>
        <table id="biTable" style="margin-top:10px"><thead><tr>
          <th style="width:34px"><input type="checkbox" id="biAll" onchange="biToggleAll(this.checked)"></th>
          <th>Ημ/νία</th><th>Περιγραφή</th><th class="num">Ποσό</th><th>Κίνηση</th>
          <th style="min-width:220px">Πελάτης (αντιστοίχιση)</th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- PRODUCTS -->
    <section class="view" id="view-products">
      <h2 class="title">Είδη / Υπηρεσίες</h2><p class="sub">Κατάλογος ειδών που τροφοδοτεί την έκδοση.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <input id="prodFilter" placeholder="Φίλτρο…" oninput="renderProducts()" style="width:260px">
          <div class="row">
            <button class="ghost" onclick="loadProducts()">↻ Ανανέωση</button>
            <button class="primary" onclick="openProductModal()">+ Νέο είδος</button>
          </div>
        </div>
        <table id="prodTable"><thead><tr><th>Κωδικός</th><th>Περιγραφή</th><th>Κατηγορία</th><th>ΦΠΑ</th><th class="num">Τιμή</th><th></th></tr></thead><tbody></tbody></table>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between">
          <div><strong>🏷️ Χαρακτηρισμοί κατηγορίας</strong><div class="sub">Προεπιλεγμένοι χαρακτηρισμοί εσόδων ανά κατηγορία ειδών & τύπο παραστατικού (myDATA §9).</div></div>
          <div class="row">
            <button class="ghost" onclick="loadCatCls()">↻ Ανανέωση</button>
            <button class="primary" onclick="openCatClsModal()">+ Νέα κατηγορία</button>
          </div>
        </div>
        <table id="catClsTable"><thead><tr><th>Κατηγορία</th><th>Χαρακτηρισμοί</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- SERIES -->
    <section class="view" id="view-series">
      <h2 class="title">Σειρές παραστατικών</h2><p class="sub">Δημιουργία & διαχείριση σειρών ανά τύπο παραστατικού (όπως στο e-timologio). Κάθε τύπος χρειάζεται τουλάχιστον μία σειρά για να εκδοθεί.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
          <button class="ghost" onclick="loadSeriesView()">↻ Ανανέωση</button>
          <button class="add" onclick="openSeriesModal()">➕ Νέα σειρά</button>
        </div>
        <div id="srResult" style="margin-top:10px"></div>
        <table id="srTable" style="margin-top:12px"><thead><tr><th>Τύπος παραστατικού</th><th>Σειρά</th><th>Αρχικό Α/Α</th><th>Περιγραφή</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- ISSUE -->
    <section class="view active" id="view-issue">
      <h2 class="title">Έκδοση παραστατικού</h2><p class="sub">Με αυτόματη συμπλήρωση πελάτη από Taxisnet.</p>

      <!-- Guided start -->
      <div class="panel wiz" id="issueWizard">
        <div id="wizStep1">
          <div class="wiz-q">1️⃣ Τι θέλεις να εκδώσεις;</div>
          <div class="wiz-opts">
            <button class="wiz-card" onclick="wizDoc('invoice')"><span class="wic">🧾</span><b>Τιμολόγιο / Απόδειξη</b><small>Πώληση αγαθών ή παροχή υπηρεσιών (με αξίες & ΦΠΑ)</small></button>
            <button class="wiz-card" onclick="wizDoc('delivery')"><span class="wic">🚚</span><b>Δελτίο αποστολής</b><small>Διακίνηση αγαθών (μόνο ποσότητες, χωρίς αξίες)</small></button>
          </div>
        </div>
        <div id="wizStep2" style="display:none">
          <div class="wiz-q">2️⃣ Ο πελάτης είναι;</div>
          <div class="wiz-opts">
            <button class="wiz-card" onclick="wizWho('pro')"><span class="wic">🏢</span><b>Επαγγελματίας</b><small>Έχει ΑΦΜ → Τιμολόγιο (πώλησης / παροχής)</small></button>
            <button class="wiz-card" onclick="wizWho('idiot')"><span class="wic">👤</span><b>Ιδιώτης</b><small>Χωρίς ΑΦΜ → Απόδειξη λιανικής</small></button>
          </div>
          <button class="ghost sm" style="margin-top:12px" onclick="wizReset()">← Πίσω</button>
        </div>
      </div>

      <div class="panel" id="issueFormPanel">
        <div class="row" style="justify-content:space-between;align-items:center;margin-bottom:4px">
          <span class="hint" id="issueMode"></span>
          <button class="ghost sm" onclick="wizReset()" title="Άλλαξε τύπο παραστατικού / πελάτη">↺ Αλλαγή επιλογής</button>
        </div>
        <div class="row" style="position:relative">
          <div class="field"><label>ΑΦΜ πελάτη</label><input id="iAfm" placeholder="9 ψηφία ή αναζήτηση" autocomplete="off" oninput="lookupAfm();custAc(this)" onfocus="custAc(this)"></div>
          <div class="field grow"><label>Επωνυμία</label><input id="iName" autocomplete="off" oninput="custAc(this)" onfocus="custAc(this)"></div>
          <div id="iCustAc" class="ac-panel"></div>
        </div>
        <div class="row">
          <div class="field grow"><label>Διεύθυνση</label><input id="iAddress"></div>
          <div class="field"><label>Πόλη</label><input id="iCity"></div>
          <div class="field"><label>Τ.Κ.</label><input id="iZip"></div>
        </div>
        <div class="row">
          <div class="field grow" style="min-width:240px"><label>Τύπος παραστατικού <span class="hint">(μόνο με ενεργή σειρά)</span></label>
            <select id="iType" onchange="issueTypeChange()"><option>…</option></select></div>
          <div class="field"><label>Σειρά</label><select id="iSeries" onchange="seriesChange()"></select></div>
          <div class="field"><label>Πληρωμή</label>
            <select id="iPay"><option value="3">Μετρητά</option><option value="1">Τραπεζικός λογ.</option>
              <option value="5" selected>Επί πιστώσει</option><option value="6">Web Banking</option>
              <option value="7">POS</option><option value="8">IRIS</option></select></div>
          <div class="field"><label>Γλώσσα</label>
            <select id="iLang" title="Γλώσσα παραστατικού"><option value="el">Ελληνικά</option><option value="en">English</option></select></div>
        </div>
        <table id="iLines"><thead><tr><th style="width:40%">Είδος</th><th style="width:78px">Ποσότητα</th><th class="num">Τιμή μον. (€)</th><th style="width:80px" class="num">Έκπτ. %</th><th style="width:70px" class="num">ΦΠΑ</th><th class="num">Σύνολο (με ΦΠΑ)</th><th></th></tr></thead><tbody></tbody></table>
        <datalist id="prodList"></datalist>
        <div class="row" style="margin-top:8px;gap:8px">
          <button class="add sm" type="button" onclick="addLine()">➕ Γραμμή</button>
          <button class="tax sm" type="button" onclick="openTaxModal()">💶 Φόρος/Κράτηση</button>
        </div>
        <div id="iCls" class="hint" style="margin-top:6px"></div>

        <!-- Φόροι / Κρατήσεις / Τέλη -->
        <div style="margin:14px 0 2px"><strong>💶 Φόροι / Κρατήσεις / Τέλη</strong> <span class="hint" id="iTaxHint" style="margin-left:8px"></span></div>
        <table id="iTaxes"><thead><tr><th>Είδος</th><th>Κατηγορία</th><th class="num">Ποσό (€)</th><th>Σημ.</th><th></th></tr></thead><tbody></tbody></table>

        <div class="row" style="margin-top:12px"><div class="field grow"><label>Σχόλια / Παρατηρήσεις</label><input id="iNotes" placeholder="Προαιρετικές παρατηρήσεις παραστατικού"></div></div>

        <div style="display:flex;justify-content:flex-end;margin-top:12px">
          <div style="min-width:300px">
            <div style="display:flex;justify-content:space-between;padding:3px 0"><span class="muted">Καθαρή αξία</span><span><b id="iNet">0,00</b> €</span></div>
            <div style="display:flex;justify-content:space-between;padding:3px 0"><span class="muted">ΦΠΑ</span><span><b id="iVat">0,00</b> €</span></div>
            <div style="display:flex;justify-content:space-between;padding:3px 0"><span class="muted">Τέλη / Λοιποί φόροι (+)</span><span><b id="iTaxPlus">0,00</b> €</span></div>
            <div style="display:flex;justify-content:space-between;padding:3px 0"><span class="muted">Παρακρατήσεις / Κρατήσεις (−)</span><span><b id="iTaxMinus">0,00</b> €</span></div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-top:1px solid var(--line);margin-top:4px;font-size:16px;font-weight:800"><span>Τελικό πληρωτέο</span><span><span id="iPayable">0,00</span> €</span></div>
          </div>
        </div>
        <div class="issue-actions">
          <div class="hint" style="margin-bottom:8px">👁 <b>Προεπισκόπηση</b> & 💾 <b>Πρόχειρο</b> = δοκιμαστικά, <b>ΔΕΝ</b> υποβάλλονται στην ΑΑΔΕ (χωρίς ΜΑΡΚ). Μόνο το κόκκινο <b>Οριστική Έκδοση</b> υποβάλλει πραγματικά και δίνει ΜΑΡΚ.</div>
          <div class="row" style="align-items:center">
            <button class="info" onclick="previewInvoice()" title="Αποθηκεύει το πρόχειρο ΚΑΙ δείχνει το PDF της ΑΑΔΕ — χωρίς υποβολή/ΜΑΡΚ. Επαναλαμβανόμενες προεπισκοπήσεις ενημερώνουν το ΙΔΙΟ πρόχειρο (δεν δημιουργούν νέο).">💾👁 Αποθήκευση &amp; Προεπισκόπηση</button>
            <button class="ghost sm" onclick="issueNewDraft()" title="Ξεκίνα νέο πρόχειρο (το επόμενο Αποθήκευση θα δημιουργήσει νέο ID)">🆕 Νέο</button>
            <div class="grow"></div>
            <button class="tax" onclick="scheduleIssue('invoice')" title="Προγραμμάτισε την οριστική έκδοση για μελλοντική ημερομηνία/ώρα (με προαιρετική επανάληψη)">⏰ Προγραμματισμός</button>
            <button class="danger" onclick="confirmIssue()" title="ΟΡΙΣΤΙΚΗ υποβολή στην ΑΑΔΕ — το παραστατικό παίρνει ΜΑΡΚ και δεν αναιρείται">📤 Οριστική Έκδοση στην ΑΑΔΕ (ΜΑΡΚ)</button>
          </div>
        </div>
        <div id="issueResult" style="margin-top:14px"></div>
      </div>
    </section>

    <!-- DELIVERY NOTE -->
    <section class="view" id="view-delivery">
      <h2 class="title">Δελτίο Αποστολής / Επιστροφής</h2>
      <p class="sub">Διακίνηση <strong>αγαθών</strong> (9.x) — φέρει τον χαρακτηρισμό διακίνησης. Για επιστροφή επίλεξε σκοπό «Επιστροφή».</p>
      <div class="panel">
        <div class="row">
          <div class="field"><label>Τύπος δελτίου</label>
            <select id="dnType" onchange="dnFillSeries()"><option value="503">9.3 Δελτίο Αποστολής</option><option value="504">9.1 Συσχετιζόμενο</option><option value="505">9.2 Συγκεντρωτικό</option></select></div>
          <div class="field"><label>Σειρά</label><select id="dnSeries" onchange="dnSeriesChange()"></select></div>
          <div class="field grow"><label>Σκοπός διακίνησης</label>
            <select id="dnPurpose">
              <option value="1">Πώληση</option><option value="2">Πώληση για Λογ. Τρίτων</option>
              <option value="3">Δειγματισμός</option><option value="4">Έκθεση</option>
              <option value="5">Επιστροφή</option><option value="6">Φύλαξη</option>
              <option value="8">Ενδοδιακίνηση</option><option value="9">Αγορά</option>
              <option value="19">Λοιπές Διακινήσεις</option><option value="20">Μεταφορές</option>
            </select></div>
        </div>
        <div class="row" style="position:relative">
          <div class="field grow" style="min-width:260px"><label>Πελάτης / Παραλήπτης</label>
            <input id="dnCust" placeholder="Αναζήτηση με επωνυμία ή ΑΦΜ…" autocomplete="off" oninput="dnCustAc(this)" onfocus="dnCustAc(this)"><div id="dnCustAcPanel" class="ac-panel"></div></div>
          <div class="field"><label>ΑΦΜ</label><input id="dnAfm" placeholder="9 ψηφία" oninput="dnLookup()"></div>
          <div class="field grow"><label>Επωνυμία</label><input id="dnName"></div>
        </div>
        <div class="row">
          <div class="field"><label>Όχημα</label><input id="dnVehicle" placeholder="π.χ. ΙΧΥ-1234"></div>
          <div class="field"><label>Ημ/νία αποστολής</label><input id="dnDate" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <div class="field"><label>Ώρα</label><input id="dnTime" type="time"></div>
        </div>
        <div class="row" style="margin:8px 0 2px;align-items:center">
          <strong>Γραμμές ειδών (αγαθά)</strong><div class="grow"></div>
          <button class="add sm" type="button" onclick="addDnLine()">➕ Γραμμή</button>
        </div>
        <table id="dnLines"><thead><tr><th style="width:70%">Αγαθό</th><th style="width:120px">Ποσότητα</th><th></th></tr></thead><tbody></tbody></table>
        <div class="hint" style="margin-top:6px">Το δελτίο διακίνησης καταγράφει <b>μόνο αγαθά & ποσότητες</b> — δεν φέρει αξίες/ΦΠΑ (χαρακτηρισμός «Διακίνηση»).</div>

        <div class="row" style="margin:10px 0 2px;align-items:center"><strong>Τόπος φόρτωσης</strong>
          <button class="info sm" type="button" onclick="dnUseBase()" title="Συμπλήρωση από την έδρα της επιχείρησης">🏢 Χρήση έδρας</button></div>
        <div class="row">
          <div class="field grow"><label>Οδός</label><input id="dnLStreet" placeholder="Οδός"></div>
          <div class="field"><label>Αριθ.</label><input id="dnLNumber"></div>
          <div class="field"><label>Πόλη</label><input id="dnLCity"></div>
          <div class="field"><label>Τ.Κ.</label><input id="dnLZip"></div>
          <div class="field"><label>Υποκ. φόρτ.</label><input id="dnLBranch" type="number" min="0" value="0" style="width:80px" title="0 = κεντρικό"></div>
        </div>

        <div class="row" style="margin:10px 0 2px"><strong>Τόπος παράδοσης</strong> <span class="muted" style="margin-left:8px">(αποθηκεύεται ανά πελάτη)</span></div>
        <div class="row">
          <div class="field grow"><label>Οδός</label><input id="dnDStreet" placeholder="Οδός"></div>
          <div class="field"><label>Αριθ.</label><input id="dnDNumber"></div>
          <div class="field"><label>Πόλη</label><input id="dnDCity"></div>
          <div class="field"><label>Τ.Κ.</label><input id="dnDZip"></div>
          <div class="field"><label>Υποκ. παράδ.</label><input id="dnDBranch" type="number" min="0" value="0" style="width:80px" title="0 = κεντρικό"></div>
        </div>
        <div class="row"><div class="field grow"><label>Σχόλια / Παρατηρήσεις</label><input id="dnNotes" placeholder="προαιρετικά"></div></div>
        <div class="issue-actions">
          <div class="hint" style="margin-bottom:8px">👁 <b>Προεπισκόπηση</b> & 💾 <b>Πρόχειρο</b> = χωρίς υποβολή/ΜΑΡΚ. Μόνο το κόκκινο <b>Οριστική Έκδοση</b> υποβάλλει το δελτίο στην ΑΑΔΕ (ΜΑΡΚ). Το δελτίο φέρει <b>μόνο αγαθά, χωρίς αξίες</b>.</div>
          <div class="row" style="align-items:center">
            <button class="info" onclick="dnPreviewPdf()" title="Αποθηκεύει το πρόχειρο ΚΑΙ δείχνει το PDF — χωρίς υποβολή/ΜΑΡΚ. Επαναλαμβανόμενες προεπισκοπήσεις ενημερώνουν το ΙΔΙΟ πρόχειρο.">💾👁 Αποθήκευση &amp; Προεπισκόπηση</button>
            <button class="ghost sm" onclick="dnNewDraft()" title="Ξεκίνα νέο πρόχειρο δελτίο">🆕 Νέο</button>
            <div class="grow"></div>
            <button class="danger" onclick="submitDelivery(true)" title="ΟΡΙΣΤΙΚΗ υποβολή δελτίου στην ΑΑΔΕ — παίρνει ΜΑΡΚ">📤 Οριστική Έκδοση δελτίου (ΜΑΡΚ)</button>
          </div>
        </div>
        <div id="dnResult" style="margin-top:14px"></div>
      </div>
    </section>

    <!-- CANCEL -->
    <section class="view" id="view-cancel">
      <h2 class="title">Ακύρωση / Πιστωτικό (συσχετιζόμενο)</h2>
      <p class="sub">Επίλεξε πελάτη, φέρε τα χρεωστικά του και επίλεξε ποιο θα ακυρώσεις/πιστώσεις. Μπορείς να αλλάξεις την αξία (μερική πίστωση).</p>
      <div class="panel">
        <div class="row" style="position:relative">
          <div class="field grow" style="min-width:280px"><label>Πελάτης</label><input id="cxCust" placeholder="Αναζήτηση με επωνυμία ή ΑΦΜ…" autocomplete="off" oninput="cxAc(this)" onfocus="cxAc(this)"><div id="cxAcPanel" class="ac-panel"></div></div>
          <input id="cxVat" type="hidden">
          <div class="field"><label>Από</label><input id="cxFrom" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <div class="field"><label>Έως</label><input id="cxTo" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
          <button class="primary" onclick="cxLoadInvoices()" data-tip="Αναζήτηση εκδοθέντων χρεωστικών — με πελάτη ή μόνο με το διάστημα Από–Έως">🔍 Αναζήτηση χρεωστικών</button>
        </div>
        <p class="hint">Άφησε τον πελάτη κενό για να ψάξεις <b>μόνο με το διάστημα Από–Έως</b>.</p>
        <table id="cxTable"><thead><tr><th>Ημ/νία</th><th>Τύπος</th><th>Σειρά/ΑΑ</th><th>Πελάτης (ΑΦΜ)</th><th class="num">Καθαρή</th><th class="num">Σύνολο</th><th>ΜΑΡΚ</th><th></th></tr></thead><tbody></tbody></table>
        <div id="cxSel" style="margin-top:12px"></div>
      </div>
    </section>

    <!-- DRAFTS -->
    <section class="view" id="view-drafts">
      <h2 class="title">Πρόχειρα παραστατικά</h2><p class="sub">Προσωρινά αποθηκευμένα (χωρίς ΜΑΡΚ). Διαγραφή ή επεξεργασία/έκδοση.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <div class="row">
            <div class="field"><label>Από</label><input id="dfFrom" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
            <div class="field"><label>Έως</label><input id="dfTo" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
            <button class="primary" onclick="loadDrafts()">Φόρτωση</button>
          </div>
          <div class="row" style="align-items:center">
            <span class="hint" id="dfCount"></span>
            <button class="danger sm" onclick="delSelectedDrafts()" data-tip="Διαγραφή όλων των επιλεγμένων προχείρων">🗑 Διαγραφή επιλεγμένων</button>
          </div>
        </div>
        <table id="draftsTable"><thead><tr><th class="grid-check nofilter"><input type="checkbox" id="dfAll" onchange="dfToggleAll(this.checked)"></th><th>Ημ/νία</th><th>Τύπος</th><th>Σειρά</th><th>Πελάτης</th><th class="nofilter"></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- BULK / MASS ISSUANCE -->
    <section class="view" id="view-bulk">
      <h2 class="title">Μαζική Έκδοση</h2>
      <p class="sub">Έκδοση πολλών παραστατικών μαζί. Κοινός τύπος/σειρά/πληρωμή· μία γραμμή ανά παραστατικό.</p>
      <div class="panel">
        <div class="row">
          <div class="field"><label>Τύπος παραστατικού</label><select id="blkType" onchange="blkFillSeries()"><option>…</option></select></div>
          <div class="field"><label>Σειρά</label><select id="blkSeries"></select></div>
          <div class="field"><label>Τρόπος πληρωμής</label><select id="blkPay">
            <option value="5">Επί πιστώσει</option><option value="3">Μετρητά</option>
            <option value="1">Τραπεζικός λογ/σμός</option><option value="7">POS / e-POS</option><option value="6">Web Banking</option></select></div>
          <div class="field"><label>Γλώσσα</label><select id="blkLang"><option value="el">Ελληνικά</option><option value="en">Αγγλικά</option></select></div>
        </div>
        <div class="row" style="margin:6px 0 2px;align-items:center">
          <strong>Παραστατικά (ένα ανά γραμμή)</strong><div class="grow"></div>
          <button class="add sm" type="button" onclick="blkAddRow()">➕ Γραμμή</button>
        </div>
        <table id="blkTable"><thead><tr>
          <th style="min-width:240px">Πελάτης</th><th style="min-width:220px">Είδος</th>
          <th style="width:90px" class="num">Ποσότητα</th><th style="width:120px" class="num">Τιμή μον. (€)</th><th></th></tr></thead><tbody></tbody></table>
        <details style="margin-top:12px">
          <summary style="cursor:pointer;color:var(--muted);font-size:12px">⚙️ Εισαγωγή από κείμενο (για προχωρημένους) — ΑΦΜ, κωδικός, ποσότητα, τιμή</summary>
          <textarea id="blkCsv" rows="5" placeholder="800702104, 1, 1, 100&#10;800702104, 3, 2, 50&#10;# γραμμές με # αγνοούνται" style="width:100%;font-family:monospace;margin-top:8px"></textarea>
          <button class="ghost sm" type="button" onclick="blkImportCsv()">⬇ Φόρτωσε στις γραμμές</button>
        </details>
        <div class="row" style="align-items:center;margin-top:12px">
          <span class="hint" id="blkCount"></span>
          <div class="grow"></div>
          <button class="add" onclick="bulkRun(false)" title="Δημιουργία προχείρων για όλες τις γραμμές — χωρίς υποβολή/ΜΑΡΚ">💾 Δημιουργία προχείρων (όλα)</button>
          <button class="tax" onclick="scheduleIssue('bulk')" title="Προγραμμάτισε την οριστική μαζική έκδοση για μελλοντική ημερομηνία/ώρα">⏰ Προγραμματισμός</button>
          <button class="danger" onclick="bulkRun(true)" title="ΟΡΙΣΤΙΚΗ μαζική έκδοση στην ΑΑΔΕ — κάθε παραστατικό παίρνει ΜΑΡΚ">📤 Οριστική έκδοση όλων (ΜΑΡΚ)</button>
        </div>
        <div id="blkResult" style="margin-top:14px"></div>
      </div>
    </section>

    <!-- SETTINGS -->
    <section class="view" id="view-settings">
      <h2 class="title">Ρυθμίσεις λογαριασμού</h2><p class="sub">Στοιχεία χρήστη, κωδικός πρόσβασης και συνδεδεμένοι λογαριασμοί AADE.</p>
      <div class="panel">
        <strong>🔑 Αλλαγή κωδικού</strong>
        <div class="row" style="margin-top:10px">
          <div class="field"><label>Τρέχων κωδικός</label><input id="cpOld" type="password"></div>
          <div class="field"><label>Νέος κωδικός (≥ 8)</label><input id="cpNew" type="password"></div>
          <div class="field"><label>Επιβεβαίωση</label><input id="cpNew2" type="password"></div>
          <button class="primary" onclick="changePassword()">Αλλαγή</button>
        </div>
        <div id="cpResult" class="sub" style="margin-top:8px"></div>
      </div>
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>🔐 Έλεγχος ταυτότητας δύο παραγόντων (2FA)</strong>
          <span id="twofaState" class="pill">—</span>
        </div>
        <p class="sub" style="margin-top:4px">Προαιρετική προστασία: εκτός από τον κωδικό, θα ζητείται και ένας 6ψήφιος κωδικός από εφαρμογή authenticator (Google Authenticator, Authy, Microsoft Authenticator, 1Password κ.λπ.).</p>
        <div id="twofaDisabled" style="display:none">
          <button class="primary" onclick="start2fa()">Ενεργοποίηση 2FA</button>
        </div>
        <div id="twofaSetup" style="display:none;margin-top:12px">
          <div class="row" style="gap:22px;align-items:flex-start;flex-wrap:wrap">
            <div style="text-align:center">
              <div id="twofaQr" style="background:#fff;padding:12px;border-radius:12px;display:inline-block;min-width:196px;min-height:196px"></div>
              <div class="sub" style="margin-top:6px">Σκάναρε τον κωδικό QR</div>
            </div>
            <div style="flex:1;min-width:240px">
              <p class="sub">Ή καταχώρησε χειροκίνητα αυτό το κλειδί στην εφαρμογή authenticator:</p>
              <code id="twofaSecret" style="display:block;background:var(--panel2);border:1px solid var(--line);padding:8px 10px;border-radius:8px;word-break:break-all;letter-spacing:1px"></code>
              <div class="field" style="margin-top:12px"><label>Κωδικός επιβεβαίωσης (6 ψηφία)</label>
                <input id="twofaCode" inputmode="numeric" maxlength="6" placeholder="••••••" style="letter-spacing:6px;text-align:center;font-size:18px;max-width:160px"></div>
              <div class="row" style="margin-top:10px">
                <button class="primary" onclick="confirm2fa()">Επιβεβαίωση & ενεργοποίηση</button>
                <button class="ghost" onclick="cancel2fa()">Άκυρο</button>
              </div>
            </div>
          </div>
        </div>
        <div id="twofaEnabled" style="display:none;margin-top:8px">
          <p class="sub">Το 2FA είναι <b style="color:var(--ok)">ενεργό</b>. Για απενεργοποίηση δώσε τον τρέχοντα κωδικό authenticator ή τον κωδικό σου.</p>
          <div class="row"><div class="field"><label>Κωδικός authenticator ή password</label><input id="twofaOff" type="text" placeholder="123456 ή ο κωδικός σου" style="max-width:220px"></div>
            <button class="danger" onclick="disable2fa()">Απενεργοποίηση 2FA</button></div>
        </div>
        <div id="twofaResult" class="sub" style="margin-top:8px"></div>
      </div>
      <?php if ($__role === 'master'): ?>
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>📮 Πάροχος email (SMTP ή Resend)</strong>
          <span class="pill" id="mailStatus">—</span>
        </div>
        <p class="sub" style="margin-top:4px">Χωρίς πάροχο, οι προσκλήσεις μελών και οι ειδοποιήσεις δεν στέλνονται με email (εμφανίζονται ως σύνδεσμοι για χειροκίνητη αποστολή). Τα μυστικά αποθηκεύονται κρυπτογραφημένα.</p>
        <div class="row" style="margin-top:8px">
          <div class="field"><label>Πάροχος</label>
            <select id="mpProvider" onchange="mpSyncFields()">
              <option value="auto">Αυτόματα (ό,τι είναι ρυθμισμένο)</option>
              <option value="resend">Resend (API)</option>
              <option value="smtp">SMTP</option>
            </select></div>
          <div class="field grow"><label>Αποστολέας (From)</label><input id="mpFrom" placeholder="e-Τιμολόγιο &lt;noreply@example.gr&gt;"></div>
          <div class="field grow"><label>Email ειδοποιήσεων διαχειριστή</label><input id="mpNotify" placeholder="κενό = ο master· «-» για κανένα"></div>
        </div>
        <!-- Τα πεδία ακολουθούν τον πάροχο: με «Resend» δεν έχει νόημα να ζητάς
             θύρα SMTP, και με «SMTP» να ζητάς API key. Παλιά φαίνονταν όλα μαζί
             και ο χρήστης συμπλήρωνε τα λάθος. -->
        <div id="mpResendBox" class="row" style="margin-top:4px">
          <div class="field grow"><label>Resend API key</label><input id="mpResend" type="password" placeholder="re_…"></div>
          <div class="hint" style="align-self:center;max-width:340px">Το κλειδί από το <b>resend.com/api-keys</b>. Ο αποστολέας πρέπει να είναι επαληθευμένος τομέας στο Resend.</div>
        </div>
        <div id="mpSmtpBox">
          <div class="row">
            <div class="field"><label>Γνωστός πάροχος</label>
              <select id="mpPreset" onchange="mpApplyPreset()">
                <option value="">— δικές μου ρυθμίσεις —</option>
                <option value="gmail">Gmail / Google Workspace</option>
                <option value="outlook">Outlook / Microsoft 365</option>
                <option value="yahoo">Yahoo Mail</option>
                <option value="otenet">OTEnet</option>
              </select></div>
            <div class="field grow"><label>SMTP host</label><input id="mpHost" placeholder="smtp.example.com"></div>
            <div class="field"><label>Θύρα</label><input id="mpPort" placeholder="587" style="max-width:100px"></div>
            <div class="field"><label>Κρυπτογράφηση</label>
              <select id="mpSecure" style="max-width:140px">
                <option value="tls">STARTTLS (587)</option>
                <option value="ssl">SSL/TLS (465)</option>
                <option value="none">Καμία</option>
              </select></div>
          </div>
          <div class="row">
            <div class="field grow"><label>Χρήστης</label><input id="mpUser" placeholder="π.χ. λογαριασμός@gmail.com"></div>
            <div class="field grow"><label>Κωδικός</label><input id="mpPass" type="password"></div>
          </div>
          <div class="hint" id="mpSmtpHint" style="margin-top:4px"></div>
        </div>
        <div class="row" style="justify-content:flex-end;margin-top:10px;align-items:center">
          <span class="sub" id="mpResult" style="margin-right:auto"></span>
          <div class="field"><label>Δοκιμή προς</label><input id="mpTestTo" placeholder="(ο δικός σου λογαριασμός)" style="width:220px"></div>
          <button class="ghost" onclick="testMailSettings()" data-tip="Στέλνει ένα δοκιμαστικό μήνυμα με τις αποθηκευμένες ρυθμίσεις">✉️ Δοκιμαστική αποστολή</button>
          <button class="primary" onclick="saveMailSettings()">Αποθήκευση</button>
        </div>
      </div>
      <?php endif; ?>
      <?php if (in_array($__role, ['master','editor'], true)): ?>
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>🔔 Ειδοποιήσεις email — εταιρίες & κινήσεις</strong>
          <label class="side-toggle" style="color:var(--txt)"><input type="checkbox" id="npEnabled" checked> Λαμβάνω email</label>
        </div>
        <p class="sub" style="margin-top:4px">Επίλεξε για <b>ποιες εταιρίες-πελάτες</b> και <b>ποιες κινήσεις</b> θέλεις να λαμβάνεις email όταν εκδίδεται παραστατικό. Οι ειδοποιήσεις μέσα στην εφαρμογή (🔔) δεν επηρεάζονται.</p>
        <div class="row" style="gap:26px;align-items:flex-start;flex-wrap:wrap;margin-top:8px">
          <div style="min-width:240px">
            <div class="hint" style="margin-bottom:6px"><b>Εταιρίες-πελάτες</b></div>
            <label class="np-check"><input type="checkbox" id="npCompAll" checked onchange="npToggleAll('comp')"> <b>(Όλες)</b></label>
            <div id="npCompanies" style="max-height:180px;overflow:auto;margin-top:4px"></div>
          </div>
          <div style="min-width:220px">
            <div class="hint" style="margin-bottom:6px"><b>Κινήσεις (τύποι)</b></div>
            <label class="np-check"><input type="checkbox" id="npTypeAll" checked onchange="npToggleAll('type')"> <b>(Όλες)</b></label>
            <div id="npTypes" style="margin-top:4px">
              <label class="np-check"><input type="checkbox" class="np-type" value="invoice"> 🧾 Τιμολόγια</label>
              <label class="np-check"><input type="checkbox" class="np-type" value="receipt"> 🧾 Αποδείξεις λιανικής</label>
              <label class="np-check"><input type="checkbox" class="np-type" value="credit"> ↩️ Πιστωτικά / Ακυρώσεις</label>
            </div>
          </div>
        </div>
        <div class="row" style="margin-top:12px;align-items:center">
          <button class="primary" onclick="saveNotifPrefs()">Αποθήκευση προτιμήσεων</button>
          <span id="npResult" class="sub"></span>
        </div>
      </div>
      <?php endif; ?>
      <?php /* Μόνο ο διαχειριστής: το κλειδί συνδέει ΟΛΟΚΛΗΡΗ εγκατάσταση με
               τον server, δεν είναι προσωπική ρύθμιση του λογιστή. */ ?>
      <?php if ($__role === 'master'): ?>
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>🔑 Κλειδιά πρόσβασης — σύνδεση εφαρμογής υπολογιστή</strong>
          <button class="add" onclick="createAccessKey()">➕ Νέο κλειδί</button>
        </div>
        <p class="sub" style="margin-top:4px">Δώσε ένα κλειδί σε κάθε υπολογιστή που θα συνδέεται σε αυτόν τον server. Στην εφαρμογή: <b>Πίνακας ελέγχου → Σύνδεση σε server</b> — επικόλληση και τέλος· τη διεύθυνση τη βρίσκει μόνη της. Το κλειδί εμφανίζεται <b>μία φορά</b>.</p>
        <div id="akNew" style="margin:8px 0"></div>
        <table id="akTable"><thead><tr><th>Περιγραφή</th><th>Δημιουργήθηκε</th><th>Τελευταία χρήση</th><th>Κατάσταση</th><th class="nofilter"></th></tr></thead><tbody></tbody></table>
      </div>
      <?php endif; ?>
      <!-- Τραπεζικοί λογαριασμοί + αυτόματη αποστολή. Ανά ΕΤΑΙΡΕΙΑ, όχι ανά
           χρήστη: το IBAN και το «στείλε το τιμολόγιο στον πελάτη» ανήκουν
           στην επιχείρηση που εκδίδει, όχι σε όποιον έτυχε να είναι μπροστά. -->
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>🏦 Λογαριασμοί & αυτόματη αποστολή <span class="muted" id="bkCompany"></span></strong>
          <button class="add" onclick="bkAddRow()">➕ Λογαριασμός</button>
        </div>
        <p class="sub" style="margin-top:4px">Οι λογαριασμοί με ✓ στο «στο email» μπαίνουν ως κείμενο στα μηνύματα καρτέλας με <b>χρεωστικό</b> υπόλοιπο. Αν ανεβάσεις PDF με τους λογαριασμούς, επισυνάπτεται κι αυτό.</p>
        <table id="bkTable">
          <thead><tr><th>Τράπεζα</th><th>IBAN</th><th>Δικαιούχος</th><th>Στο email</th><th class="nofilter"></th></tr></thead>
          <tbody></tbody>
        </table>
        <div class="row" style="margin-top:10px;align-items:center;gap:10px">
          <div class="field grow"><label>PDF με τους λογαριασμούς <span class="muted">(προαιρετικό, έως 3 MB)</span></label>
            <input type="file" id="bkPdfFile" accept="application/pdf" onchange="bkUploadPdf(this)"></div>
          <span class="sub" id="bkPdfState">—</span>
          <button class="ghost sm" id="bkPdfView" onclick="bkViewPdf()" style="display:none">👁 Προβολή</button>
          <button class="ghost sm" id="bkPdfDel" onclick="bkDeletePdf()" style="display:none">🗑 Αφαίρεση</button>
        </div>

        <div style="border-top:1px solid var(--line);margin:14px 0 10px"></div>
        <div class="row" style="align-items:center;gap:18px;flex-wrap:wrap">
          <label class="side-toggle" style="color:var(--txt)"><input type="checkbox" id="bkAutoSend"> Αυτόματη αποστολή παραστατικού στον πελάτη μόλις εκδοθεί</label>
          <div class="field grow"><label>Κρυφή κοινοποίηση (BCC)</label><input id="bkAutoBcc" placeholder="π.χ. logistirio@example.gr"></div>
        </div>
        <p class="sub">Στέλνεται μόνο όταν ο πελάτης έχει καταχωρημένο email. Χωρίς email καταγράφεται στο ημερολόγιο ενεργειών και δεν χάνεται σιωπηλά.</p>

        <div style="border-top:1px solid var(--line);margin:14px 0 10px"></div>
        <div class="row" style="align-items:center;gap:18px;flex-wrap:wrap">
          <label class="side-toggle" style="color:var(--txt)"><input type="checkbox" id="bkSchedOn"> Προγραμματισμένη αποστολή καρτελών</label>
          <div class="field"><label>Ημέρα μήνα</label><input id="bkSchedDay" type="number" min="1" max="28" value="1" style="width:90px"></div>
          <label class="side-toggle" style="color:var(--txt)"><input type="checkbox" id="bkSchedDebit" checked> Μόνο χρεωστικά υπόλοιπα</label>
          <div class="field"><label>Ελάχιστο ποσό €</label><input id="bkSchedMin" type="number" step="0.01" min="0" value="0" style="width:120px"></div>
          <button class="ghost sm" onclick="bkDispatchNow()" data-tip="Στέλνει τώρα, χωρίς να περιμένει την ημέρα του μήνα">▶️ Αποστολή τώρα</button>
        </div>
        <p class="sub">Η προγραμματισμένη αποστολή γράφει την καρτέλα <b>μέσα στο μήνυμα</b> (πίνακα κινήσεων): ο server δεν φτιάχνει PDF με ελληνικά — αυτό το κάνει ο browser. Από την οθόνη «Καρτέλα» η μαζική αποστολή επισυνάπτει κανονικό PDF.</p>
        <div class="row" style="justify-content:flex-end;margin-top:10px;align-items:center">
          <span class="sub" id="bkResult" style="margin-right:auto"></span>
          <button class="primary" onclick="bkSave()">Αποθήκευση</button>
        </div>
      </div>
      <?php if (defined('DESKTOP_TOKEN') && DESKTOP_TOKEN !== ''): ?>
      <!-- ΜΟΝΟ στην εγκατάσταση γραφείου. Στον server δεν έχει νόημα: εκεί τα
           δεδομένα ΕΙΝΑΙ ήδη στον server. -->
      <div class="panel" style="margin-top:16px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>☁️ Σύνδεση με web server (προαιρετική)</strong>
          <span class="pill" id="lkState">—</span>
        </div>
        <p class="sub" style="margin-top:4px">
          Δουλεύεις μια χαρά και χωρίς αυτήν. Με τη σύνδεση όμως, τα δεδομένα των
          εταιρειών σου ζουν <b>στον server</b> και κάθε πελάτης μπορεί να μπει
          από browser με έναν σύνδεσμο — χωρίς να εγκαταστήσει τίποτα.
          Ζήτα από τον διαχειριστή του server ένα <b>κλειδί πρόσβασης</b>
          (Ρυθμίσεις → «🔑 Κλειδιά πρόσβασης» στον server) και επικόλλησέ το εδώ·
          τη διεύθυνση την κουβαλά το ίδιο το κλειδί.
        </p>
        <div class="row" style="margin-top:8px">
          <div class="field grow"><label>Κλειδί πρόσβασης</label>
            <input id="lkKey" type="password" placeholder="etim1_…" autocomplete="off"></div>
          <button class="primary" onclick="linkConnect()">Σύνδεση σε server</button>
          <button class="ghost" onclick="linkDisconnect()">Αποσύνδεση</button>
        </div>
        <div class="hint" id="lkInfo" style="margin-top:8px"></div>
        <table id="lkTable"><thead><tr>
          <th>Εταιρεία</th><th>ΑΦΜ</th><th>Σύνδεσμος για τον πελάτη</th><th class="nofilter"></th>
        </tr></thead><tbody></tbody></table>
      </div>
      <?php endif; ?>
      <div class="panel" style="margin-top:16px">
        <strong>🏢 Συνδεδεμένοι λογαριασμοί AADE</strong>
        <p class="sub" style="margin-top:4px">Τα διαπιστευτήρια e-timologio αποθηκεύονται κρυπτογραφημένα και ρυθμίζονται από τον διαχειριστή.</p>
        <table id="settAccts"><thead><tr><th>ΑΦΜ</th><th>Ετικέτα</th><th>Username</th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <?php if (in_array($__role, ['master','editor'], true)): ?>
    <!-- ADMIN -->
    <section class="view" id="view-admin">
      <h2 class="title">🛡️ Διαχείριση</h2>
      <p class="sub" id="adminIntro"></p>
      <!-- Ο διαχωρισμός είναι το θέμα αυτής της οθόνης, γι' αυτό λέγεται πρώτος:
           ποιος βλέπει τι. Χωρίς αυτό ο λογιστής νόμιζε ότι «λείπουν εταιρείες». -->
      <div class="panel scope-banner" id="adminScope"></div>

      <?php if ($__role === 'master'): ?>
      <div class="panel" style="margin-top:14px">
        <div class="row" style="justify-content:space-between">
          <strong>👤 Χρήστες & μέλη</strong>
          <div class="row">
            <button class="ghost" onclick="loadAdmin()">↻ Ανανέωση</button>
            <button class="add" onclick="openInviteModal()">✉️ Πρόσκληση μέλους</button>
            <button class="primary" onclick="openUserModal()">+ Νέα επιχείρηση</button>
          </div>
        </div>
        <p class="sub" style="margin-top:4px">Ρόλοι: <b>Διαχειριστής</b> = κάθε εταιρεία + διαχείριση μελών· <b>Λογιστής</b> = <u>μόνο οι εταιρείες που του αναθέτεις</u>· <b>Επιχείρηση</b> = μόνο οι δικές της.</p>
        <table id="adminUsers"><thead><tr><th>Επωνυμία / Όνομα</th><th>Email</th><th>Ρόλος</th><th>Κατάσταση</th><th>2FA</th><th>Εταιρείες</th><th class="nofilter"></th></tr></thead><tbody></tbody></table>
      </div>
      <?php endif; ?>

      <!-- Χρονομέτρηση: πόση ώρα δούλεψε ποιος, για ποια εταιρεία. Δεν προκύπτει
           από τις ενέργειες — μια ώρα ελέγχου καρτελών δεν αφήνει «ενέργεια». -->
      <div class="panel" style="margin-top:14px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>⏱️ Χρόνος εργασίας ανά εταιρεία</strong>
          <div class="row">
            <div class="field"><label>Από</label><input id="wtFrom" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
            <div class="field"><label>Έως</label><input id="wtTo" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)"></div>
            <button class="ghost" onclick="loadWorkTime()">↻ Ανανέωση</button>
          </div>
        </div>
        <p class="sub">Μετράει μόνο όση ώρα η εφαρμογή είναι <b>ανοιχτή και ορατή</b> με επιλεγμένη την εταιρεία. Ένα ξεχασμένο παράθυρο δεν χρεώνεται.</p>
        <table id="wtTable"><thead><tr><th>Εταιρεία</th><th>Χρήστης</th><th class="num">Ώρες</th><th>Τελευταία δραστηριότητα</th></tr></thead><tbody></tbody></table>
      </div>

      <!-- Ημερολόγιο ενεργειών -->
      <div class="panel" style="margin-top:14px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>📜 Ημερολόγιο ενεργειών</strong>
          <div class="row">
            <div class="field"><label>Ενέργεια</label>
              <select id="alAction" onchange="loadAuditLog()">
                <option value="">(όλες)</option>
                <option value="login">Σύνδεση</option>
                <option value="logout">Αποσύνδεση</option>
                <option value="issue">Έκδοση παραστατικού</option>
                <option value="payment_update">Αλλαγή πληρωμής</option>
                <option value="payment_delete">Διαγραφή πληρωμής</option>
                <option value="email_sent">Αποστολή email</option>
              </select></div>
            <button class="ghost" onclick="loadAuditLog()">↻ Ανανέωση</button>
          </div>
        </div>
        <table id="alTable"><thead><tr><th>Πότε</th><th>Χρήστης</th><th>Εταιρεία</th><th>Ενέργεια</th><th>Λεπτομέρειες</th></tr></thead><tbody></tbody></table>
      </div>

      <div class="panel" style="margin-top:14px">
        <div class="row" style="justify-content:space-between;align-items:center">
          <strong>🏢 Επιχειρήσεις (λογαριασμοί AADE)</strong>
          <div class="row">
            <span class="hint" id="adminBizCount"></span>
            <button class="add" onclick="openNewCompany()" data-tip="Προσθήκη εταιρείας με τα διαπιστευτήρια AADE της">➕ Νέα εταιρεία</button>
          </div>
        </div>
        <p class="sub" id="adminBizNote"></p>
        <table id="adminBiz"><thead><tr><th>Επωνυμία</th><th>ΑΦΜ</th><th>Χρήστης (κάτοχος)</th><th>Λογιστές</th><th class="nofilter"></th></tr></thead><tbody></tbody></table>
      </div>

    </section>
    <?php endif; ?>

    <!-- SCHEDULED ISSUANCE -->
    <section class="view" id="view-schedule">
      <h2 class="title">Προγραμματισμός εκδόσεων</h2>
      <p class="sub">Προγραμματισμένη αυτόματη έκδοση παραστατικών (μεμονωμένων ή μαζικών) σε μελλοντική ημερομηνία/ώρα, με προαιρετική επανάληψη. Δημιούργησε ένα πρόγραμμα από το κουμπί «⏰ Προγραμματισμός» στην <a href="#" onclick="showView('issue');return false">Έκδοση</a> ή στη <a href="#" onclick="showView('bulk');return false">Μαζική έκδοση</a>.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between;align-items:center">
          <span class="hint" id="schedCount"></span>
          <button class="ghost" onclick="loadSchedule()">↻ Ανανέωση</button>
          <button class="ghost" onclick="clearFinishedJobs()" title="Διαγράφει ακυρωμένα, εκτελεσμένα και αποτυχημένα — τα εκκρεμή μένουν">🗑 Καθαρισμός ολοκληρωμένων</button>
        </div>
        <div id="schedNote" class="hint" style="margin:6px 0 0"></div>
        <table id="schedTable"><thead><tr>
          <th>Περιγραφή</th><th>Τύπος</th><th>Πότε</th><th>Επανάληψη</th><th>Κατάσταση</th><th>Τελευταία εκτέλεση</th><th></th>
        </tr></thead><tbody></tbody></table>
      </div>
    </section>
  </main>
</div>

<!-- Customer modal -->
<dialog id="custModal"><div class="modal-body">
  <div class="modal-head">👤 <span id="custModalTitle">Νέος πελάτης</span></div>
  <div class="tabset" id="custTabs">
    <button class="on" data-t="afm" onclick="custTab('afm')">Με ΑΦΜ (Taxisnet)</button>
    <button data-t="personal" onclick="custTab('personal')">Ιδιώτης (χωρίς ΑΦΜ)</button>
  </div>
  <div id="custTabAfm">
    <div class="row"><div class="field grow"><label>ΑΦΜ</label><input id="cmAfm" placeholder="9 ψηφία"></div>
      <button class="ghost" onclick="cmLookup()">Άντληση από Taxisnet</button></div>
    <div class="row" style="margin-top:8px"><div class="field grow"><label>Επωνυμία</label><input id="cmName"></div></div>
    <div class="row"><div class="field grow"><label>Διεύθυνση</label><input id="cmAddress"></div>
      <div class="field"><label>Πόλη</label><input id="cmCity"></div><div class="field"><label>Τ.Κ.</label><input id="cmZip"></div></div>
    <!-- Προαιρετικά, αλλά απαραίτητα για την αποστολή παραστατικού/καρτέλας με
         email: αν λείπει το email, ο πελάτης δεν μπορεί να παραλάβει τίποτα. -->
    <div class="row"><div class="field grow"><label>Email <span class="muted">(για αποστολή παραστατικών)</span></label><input id="cmEmail" type="email" placeholder="πχ. logistirio@example.gr"></div>
      <div class="field"><label>Τηλέφωνο</label><input id="cmPhone1" style="width:150px"></div>
      <div class="field"><label>Τηλέφωνο 2</label><input id="cmPhone2" style="width:150px"></div></div>
    <p class="hint">Αποθήκευση δημιουργεί τον πελάτη στο e-timologio (αν δεν υπάρχει).</p>
  </div>
  <div id="custTabPersonal" style="display:none">
    <div class="row"><div class="field grow"><label>Ονοματεπώνυμο *</label><input id="cpName"></div></div>
    <div class="row"><div class="field grow"><label>Διεύθυνση</label><input id="cpAddress"></div>
      <div class="field"><label>Πόλη *</label><input id="cpCity"></div><div class="field"><label>Τ.Κ. *</label><input id="cpZip"></div></div>
    <div class="row"><div class="field grow"><label>Επάγγελμα</label><input id="cpJob" value="ΙΔΙΩΤΗΣ"></div>
      <div class="field grow"><label>Email</label><input id="cpEmail"></div><div class="field"><label>Τηλέφωνο</label><input id="cpPhone"></div></div>
  </div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="custModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveCustomer()">Αποθήκευση</button>
  </div>
</div></dialog>

<!-- Customer EDIT modal ------------------------------------------------------
     Ξεχωριστό από τη «Νέος πελάτης»: η προσθήκη ρωτά ΑΦΜ και αντλεί από το
     Taxisnet, η επεξεργασία δουλεύει σε υπάρχουσα καρτέλα — καρτέλες, τηλέφωνα
     και ΔΟΥ δεν έχουν νόημα στη μία και είναι απαραίτητα στην άλλη. Με κοινή
     φόρμα τα μισά πεδία ήταν πάντα λάθος. -->
<dialog id="custEditModal"><div class="modal-body" style="max-width:720px">
  <div class="modal-head">✎ Επεξεργασία πελάτη</div>
  <div class="sub" style="margin:-6px 0 10px">ΑΦΜ <b id="ceVatLbl">—</b> · οι αλλαγές αποθηκεύονται στο e-timologio.</div>
  <div class="row">
    <div class="field"><label>Κωδικός πελάτη</label><input id="ceCode" style="width:120px"></div>
    <div class="field grow"><label>Επωνυμία *</label><input id="ceName"></div>
    <button class="ghost" onclick="ceLookup()" data-tip="Ξανα-αντλεί τα επίσημα στοιχεία από το Taxisnet">↻ Από Taxisnet</button>
  </div>
  <div class="row" style="margin-top:8px">
    <div class="field grow"><label>Διεύθυνση</label><input id="ceAddress"></div>
    <div class="field"><label>Πόλη</label><input id="ceCity"></div>
    <div class="field"><label>Τ.Κ.</label><input id="ceZip" style="width:100px"></div>
  </div>
  <div class="row" style="margin-top:8px">
    <div class="field grow"><label>Επάγγελμα / δραστηριότητα</label><input id="ceJob"></div>
    <div class="field"><label>ΔΟΥ</label><input id="ceDoy" style="width:160px"></div>
  </div>
  <div class="row" style="margin-top:8px">
    <div class="field grow"><label>Email</label><input id="ceEmail" type="email"></div>
    <div class="field"><label>Τηλέφωνο</label><input id="cePhone1" style="width:150px"></div>
    <div class="field"><label>Τηλέφωνο 2</label><input id="cePhone2" style="width:150px"></div>
  </div>
  <div id="ceResult" class="sub" style="margin-top:8px"></div>
  <div class="row" style="margin-top:16px;justify-content:space-between">
    <button class="ghost" onclick="ceOpenCard()">📇 Άνοιγμα καρτέλας</button>
    <span>
      <button class="ghost" onclick="custEditModal.close()">Άκυρο</button>
      <button class="primary" onclick="saveCustomerEdit()">Αποθήκευση</button>
    </span>
  </div>
</div></dialog>

<!-- Product modal -->
<dialog id="prodModal"><div class="modal-body">
  <div class="modal-head">📦 <span id="prodModalTitle">Νέο είδος</span></div>
  <div class="row"><div class="field"><label>Κωδικός *</label><input id="pdCode"></div>
    <div class="field"><label>Τύπος</label><select id="pdType" onchange="pdTypeChange()"><option value="2">Υπηρεσία</option><option value="1">Αγαθό</option></select></div></div>
  <div class="row" style="margin-top:8px"><div class="field grow"><label>Περιγραφή *</label><input id="pdDesc"></div></div>
  <div class="row"><div class="field grow"><label>Κατηγορία</label><select id="pdCategory"></select></div>
    <div class="field"><label>ΦΠΑ</label><select id="pdVat">
      <option value="1">24%</option><option value="2">13%</option><option value="3">6%</option>
      <option value="5">9%</option><option value="7">0%</option><option value="8">Απαλλ.</option></select></div>
    <div class="field" id="pdUnitField"><label>Μον. μέτρ.</label><select id="pdUnit">
      <option value="1">Τεμάχιο</option><option value="2">Κιλό</option><option value="3">Λίτρο</option>
      <option value="4">Μέτρο</option><option value="7">Άλλο</option></select></div>
    <div class="field"><label>Τιμή (€)</label><input id="pdPrice" type="number" step="0.01" value="0"></div></div>
  <div class="card" style="margin-top:12px;background:rgba(56,189,248,.08)">
    <div id="pdClsSuggest" class="sub" style="margin-bottom:6px"></div>
    <button class="info sm" type="button" onclick="suggestCatClsFromProduct()">🏷️ Νέα κατηγορία με προτεινόμενο χαρακτηρισμό</button>
    <span class="hint" style="margin-left:8px">Δημιουργεί κατηγορία με τον σωστό χαρακτηρισμό ανά τύπο παραστατικού· διάλεξέ την μετά στο πεδίο «Κατηγορία».</span>
  </div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="prodModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveProduct()">Αποθήκευση</button>
  </div>
</div></dialog>

<!-- Series create modal -->
<dialog id="seriesModal"><div class="modal-body" style="max-width:560px">
  <div class="modal-head">🔢 Νέα σειρά παραστατικού</div>
  <div class="row"><div class="field grow"><label>Τύπος παραστατικού *</label><select id="srType" style="min-width:280px"></select></div></div>
  <div class="row" style="margin-top:8px">
    <div class="field"><label>Κωδικός σειράς *</label><input id="srCode" placeholder="π.χ. Α, ΤΠΥ, ΔΑ" style="width:150px" maxlength="10"></div>
    <div class="field"><label>Αρχικό Α/Α</label><input id="srAa" type="number" min="1" value="1" style="width:100px"></div>
    <div class="field grow"><label>Περιγραφή (προαιρετικό)</label><input id="srDesc" placeholder="Περιγραφή"></div>
  </div>
  <div id="srModalResult" style="margin-top:10px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="seriesModal.close()">Άκυρο</button>
    <button class="add" onclick="createSeriesUI()">➕ Εισαγωγή σειράς</button>
  </div>
</div></dialog>

<!-- Category classifications modal -->
<dialog id="catClsModal"><div class="modal-body" style="max-width:820px">
  <div class="modal-head">🏷️ <span id="catClsTitle">Χαρακτηρισμοί κατηγορίας</span></div>
  <div class="row"><div class="field grow"><label>Ονομασία κατηγορίας *</label><input id="ccName"></div></div>
  <div class="row" style="margin:10px 0 2px;align-items:center"><strong>Χαρακτηρισμοί</strong><span class="sub" style="margin-left:8px">ένας ανά τύπο παραστατικού</span><div class="grow"></div>
    <button class="ghost sm" type="button" onclick="addCatClsRow()">+ Χαρακτηρισμός</button></div>
  <table id="ccRows"><thead><tr><th style="width:34%">Τύπος παραστατικού</th><th style="width:30%">Κατηγορία εσόδου</th><th style="width:30%">Κωδικός (E3)</th><th></th></tr></thead><tbody></tbody></table>
  <div id="ccErr" class="sub" style="color:#fca5a5;margin-top:6px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="catClsModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveCatCls()">Αποθήκευση</button>
  </div>
</div></dialog>

<!-- Payment modal -->
<dialog id="payModal"><form method="dialog" class="modal-body" onsubmit="savePayment(event)">
  <div class="modal-head" id="pmHead">💶 Καταχώρηση πληρωμής</div>
  <!-- Ο επιλογέας πελάτη φαίνεται μόνο στη μεμονωμένη καταχώρηση· από την
       Καρτέλα ο πελάτης είναι ήδη γνωστός και μένει κλειδωμένος. -->
  <div class="row" id="pmPickRow" style="position:relative;display:none">
    <div class="field grow"><label>Πελάτης *</label>
      <input id="pmCust" placeholder="Αναζήτηση με επωνυμία ή ΑΦΜ…" autocomplete="off" oninput="pmAc(this)" onfocus="pmAc(this)">
      <div id="pmAcPanel" class="ac-panel"></div></div>
  </div>
  <div class="row" style="align-items:flex-end"><div class="field grow"><label>Πελάτης (ΑΦΜ)</label><input id="pmVat" readonly></div>
    <button type="button" class="ghost" id="pmCardBtn" style="display:none" onclick="pmShowCard()" data-tip="Δείχνει τζίρο, πληρωμές και τρέχον υπόλοιπο χωρίς να κλείσει η φόρμα">📇 Καρτέλα</button>
    <div class="field"><label>Ποσό (€)</label><input id="pmAmount" type="number" step="0.01" required></div></div>
  <div class="row"><div class="field"><label>Ημ/νία</label><input id="pmDate" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)" required></div>
    <div class="field"><label>Τρόπος</label><select id="pmMethod"><option value="3">Μετρητά</option><option value="1">Τραπεζική μεταφορά</option><option value="4">Επιταγή</option></select></div></div>
  <div class="field" style="margin-top:8px"><label>Σημειώσεις</label><input id="pmNotes" placeholder="π.χ. έναντι τιμολογίου…"></div>
  <label class="np-check" id="pmRepeatWrap" style="margin-top:10px;display:none">
    <input type="checkbox" id="pmRepeat"> Επαναλαμβανόμενη εισαγωγή <span class="muted">(το παράθυρο μένει ανοιχτό και κρατά τον ίδιο πελάτη)</span></label>
  <div id="pmResult" class="sub" style="margin-top:6px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button type="button" class="ghost" onclick="payModal.close()">Κλείσιμο</button>
    <button type="submit" class="primary">Αποθήκευση</button></div>
</form></dialog>

<!-- Αποστολή με email: ΠΑΝΤΑ με προεπισκόπηση κειμένου. Ο λογιστής γράφει
     διαφορετικά σε κάθε πελάτη, και ένα σταθερό κείμενο δεν εξυπηρετεί. -->
<dialog id="mailModal"><form method="dialog" class="modal-body" style="max-width:660px" onsubmit="sendMailDoc(event)">
  <div class="modal-head">✉️ <span id="mmTitle">Αποστολή με email</span></div>
  <div class="row"><div class="field grow"><label>Προς *</label><input id="mmTo" type="email" required placeholder="πελάτης@example.gr"></div></div>
  <div class="row"><div class="field grow"><label>Θέμα *</label><input id="mmSubject" required></div></div>
  <div class="field" style="margin-top:8px"><label>Μήνυμα</label>
    <textarea id="mmBody" rows="7" style="width:100%;resize:vertical"></textarea></div>
  <div class="hint" id="mmAttach" style="margin-top:6px"></div>
  <div id="mmResult" class="sub" style="margin-top:8px"></div>
  <div class="row" style="margin-top:14px;justify-content:flex-end">
    <button type="button" class="ghost" onclick="mailModal.close()">Άκυρο</button>
    <button type="submit" class="primary">✉️ Αποστολή</button>
  </div>
</form></dialog>

<!-- Μαζική αποστολή καρτελών: πρώτα ΒΛΕΠΕΙΣ ποιος θα λάβει και τι χρωστά,
     μετά στέλνεις. Μια λίστα παραληπτών που δεν φαίνεται είναι επικίνδυνη. -->
<dialog id="ledgerBulkModal"><div class="modal-body" style="max-width:860px">
  <div class="modal-head">📨 Μαζική αποστολή καρτελών</div>
  <div class="row" style="align-items:flex-end;gap:12px;flex-wrap:wrap">
    <div class="field"><label>Από</label><input id="lbFrom" type="date"></div>
    <div class="field"><label>Έως</label><input id="lbTo" type="date"></div>
    <label class="side-toggle" style="color:var(--txt)"><input type="checkbox" id="lbOnlyDebit" checked onchange="lbLoad()"> Μόνο χρεωστικά υπόλοιπα</label>
    <div class="field"><label>Ελάχιστο ποσό €</label><input id="lbMin" type="number" step="0.01" min="0" value="0" style="width:110px"></div>
    <button class="ghost sm" onclick="lbLoad()">🔄 Ανανέωση</button>
    <button class="ghost sm" onclick="lbFindEmails()" data-tip="Ρωτά την ΑΑΔΕ για όσους δεν έχουν email — μία φορά ανά πελάτη">🔎 Εύρεση email</button>
  </div>
  <div style="max-height:340px;overflow:auto;margin-top:10px">
    <table id="lbTable"><thead><tr><th class="nofilter"></th><th>Πελάτης</th><th>ΑΦΜ</th><th>Υπόλοιπο</th><th>Email</th></tr></thead><tbody></tbody></table>
  </div>
  <div class="hint" style="margin-top:6px">Κάθε καρτέλα φεύγει ως συνημμένο PDF, με το κείμενο να αναφέρει αν το υπόλοιπο είναι προς πληρωμή ή πιστωτικό. Η αποστολή γίνεται με SMTP.</div>
  <div class="row" style="margin-top:12px;justify-content:flex-end;align-items:center">
    <span class="sub" id="lbResult" style="margin-right:auto"></span>
    <button type="button" class="ghost" onclick="ledgerBulkModal.close()">Κλείσιμο</button>
    <button type="button" class="primary" onclick="lbSend()">📨 Αποστολή στους επιλεγμένους</button>
  </div>
</div></dialog>

<!-- Καρτέλα «με μια ματιά», μέσα από την καταχώρηση πληρωμής -->
<dialog id="pmCardModal"><div class="modal-body" style="max-width:720px">
  <div class="modal-head">📇 Καρτέλα — <span id="pmCardTitle"></span></div>
  <div id="pmCardBody"></div>
  <div class="row" style="margin-top:14px;justify-content:flex-end">
    <button class="ghost" onclick="pmCardModal.close()">Κλείσιμο</button>
  </div>
</div></dialog>

<?php if (in_array($__role, ['master','editor'], true)): ?>
<!-- Μία εταιρεία, ένα παράθυρο -----------------------------------------------
     Παλιά υπήρχε ΕΝΑ παράθυρο «Λογαριασμοί AADE» ανά χρήστη, με μια γραμμή
     πίνακα και τέσσερα στενά πεδία για ΟΛΕΣ τις εταιρείες μαζί. Δεν χωρούσε
     τίποτα παραπάνω από ΑΦΜ/ετικέτα, και ο διαχειριστής δεν έβλεπε ποτέ πού
     ανήκει η κάθε μία. -->
<dialog id="companyModal"><div class="modal-body" style="max-width:700px">
  <div class="modal-head">🏢 <span id="coTitle">Εταιρεία</span></div>
  <div class="sub" style="margin:-6px 0 12px" id="coSub"></div>
  <div class="row">
    <div class="field"><label>ΑΦΜ *</label><input id="coVat" style="width:130px" oninput="coVatLookup()"></div>
    <div class="field grow"><label>Επωνυμία / ετικέτα *</label><input id="coLabel"></div>
  </div>
  <div class="row" style="margin-top:8px">
    <div class="field grow"><label>e-timologio username *</label><input id="coUser"></div>
    <div class="field grow"><label>Subscription key</label><input id="coKey" type="password" placeholder="(αμετάβλητο)"></div>
  </div>
  <div class="hint" id="coKeyHint" style="margin-top:4px"></div>
  <?php if ($__role === 'master'): ?>
  <div style="margin-top:14px">
    <div class="hint" style="margin-bottom:6px"><b>Λογιστές με πρόσβαση σε αυτή την εταιρεία</b></div>
    <div id="coManagers" class="np-list"></div>
  </div>
  <?php endif; ?>
  <div id="coResult" class="sub" style="margin-top:10px"></div>
  <div class="row" style="margin-top:16px;justify-content:space-between">
    <?php if ($__role === 'master'): ?>
    <button class="danger" id="coDelete" onclick="deleteCompany()">🗑 Διαγραφή εταιρείας</button>
    <?php else: ?><span></span><?php endif; ?>
    <span>
      <button class="ghost" onclick="companyModal.close()">Άκυρο</button>
      <button class="primary" onclick="saveCompany()">Αποθήκευση</button>
    </span>
  </div>
</div></dialog>
<?php endif; ?>

<?php if ($__role === 'master'): ?>
<!-- Admin: ανάθεση εταιρειών σε λογιστή -->
<dialog id="assignModal"><div class="modal-body" style="max-width:620px">
  <div class="modal-head">🔗 Εταιρείες του λογιστή — <span id="asWho"></span></div>
  <p class="sub" style="margin:-4px 0 10px">Ο λογιστής βλέπει, εκδίδει και προγραμματίζει <b>μόνο</b> για τις εταιρείες που τσεκάρεις. Χωρίς καμία επιλογή δεν βλέπει τίποτα.</p>
  <div class="row" style="align-items:center">
    <input id="asFilter" placeholder="Φίλτρο εταιρείας…" oninput="renderAssign()" style="flex:1">
    <button class="ghost sm" onclick="asToggleAll(true)">Όλες</button>
    <button class="ghost sm" onclick="asToggleAll(false)">Καμία</button>
  </div>
  <div id="asList" class="np-list" style="max-height:320px;overflow:auto;margin-top:8px"></div>
  <div id="asResult" class="sub" style="margin-top:8px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="assignModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveAssign()">Αποθήκευση</button>
  </div>
</div></dialog>

<!-- Admin: create user -->
<dialog id="userModal"><div class="modal-body" style="max-width:640px">
  <div class="modal-head">🏢 Νέα επιχείρηση</div>
  <div class="sub" style="margin:-6px 0 10px">Στοιχεία σύνδεσης AADE (e-timologio) — η επωνυμία συμπληρώνεται αυτόματα από το ΑΦΜ.</div>
  <div class="row"><div class="field"><label>ΑΦΜ *</label><input id="uVat" placeholder="9 ψηφία" oninput="uVatLookup()" style="width:120px"></div>
    <div class="field grow"><label>Επωνυμία επιχείρησης *</label><input id="uName" placeholder="(αυτόματα από ΑΦΜ)"></div></div>
  <div class="row" style="margin-top:8px"><div class="field grow"><label>e-timologio username *</label><input id="uUsername"></div>
    <div class="field grow"><label>Subscription key *</label><input id="uKey"></div></div>
  <div class="row" style="margin-top:8px"><div class="field grow"><label>Email σύνδεσης *</label><input id="uEmail" type="email"></div>
    <div class="field"><label>Κωδικός * (≥ 8)</label><input id="uPass" type="password"></div></div>
  <div id="uErr" class="sub" style="color:#fca5a5;margin-top:6px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="userModal.close()">Άκυρο</button>
    <button class="primary" onclick="createUser()">Δημιουργία</button></div>
</div></dialog>

<!-- Admin: οι εταιρείες ενός χρήστη. Η ΕΠΕΞΕΡΓΑΣΙΑ γίνεται ανά εταιρεία
     (companyModal)· εδώ μένει μόνο η λίστα και η προσθήκη νέας. -->
<dialog id="acctModal"><div class="modal-body" style="max-width:720px">
  <div class="modal-head">🏢 Εταιρείες του χρήστη — <span id="amUser"></span></div>
  <table id="amList"><thead><tr><th>ΑΦΜ</th><th>Ετικέτα</th><th>Username</th><th class="nofilter"></th></tr></thead><tbody></tbody></table>
  <div class="row" style="margin-top:14px;align-items:flex-end">
    <div class="field"><label>ΑΦΜ</label><input id="amVat" oninput="amVatLookup()" style="width:120px"></div>
    <div class="field"><label>Ετικέτα</label><input id="amLabel" placeholder="(αυτόματα)" style="width:160px"></div>
    <div class="field"><label>Username</label><input id="amUsername" style="width:140px"></div>
    <div class="field"><label>Subscription key</label><input id="amKey" style="width:220px"></div>
    <button class="primary" onclick="addAccount()">+ Προσθήκη</button>
  </div>
  <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="ghost" onclick="acctModal.close()">Κλείσιμο</button></div>
</div></dialog>

<!-- Invite member modal -->
<dialog id="inviteModal"><div class="modal-body" style="max-width:520px">
  <div class="modal-head">✉️ Πρόσκληση μέλους</div>
  <p class="sub" style="margin:-4px 0 12px">Στέλνεται email με σύνδεσμο ενεργοποίησης όπου το μέλος ορίζει κωδικό.</p>
  <div class="row"><div class="field grow"><label>Email *</label><input id="invEmail" type="email" placeholder="name@example.gr"></div></div>
  <div class="row" style="margin-top:8px">
    <div class="field grow"><label>Όνομα / Επωνυμία (προαιρετικό)</label><input id="invName" placeholder="π.χ. Λογιστήριο ή Επωνυμία"></div>
    <div class="field"><label>Ρόλος *</label>
      <select id="invRole">
        <option value="editor">Λογιστής (όλες οι εταιρίες)</option>
        <option value="master">Διαχειριστής (πλήρη + μέλη)</option>
        <option value="business">Επιχείρηση (δικές της εταιρίες)</option>
      </select></div>
  </div>
  <div id="invResult" style="margin-top:10px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="inviteModal.close()">Άκυρο</button>
    <button class="add" onclick="sendInvite()">✉️ Αποστολή πρόσκλησης</button>
  </div>
</div></dialog>
<?php endif; ?>

<!-- New tax / withholding / fee (Νέος Φόρος) -->
<dialog id="taxModal"><div class="modal-body" style="max-width:560px">
  <div class="modal-head">💶 Νέος Φόρος / Κράτηση</div>
  <div class="field"><label>Είδος Φόρου *</label>
    <select id="txType" onchange="txTypeChange()">
      <option value="">Επιλέξτε…</option>
      <option value="1">Παρακρατούμενοι</option>
      <option value="2">Τέλη</option>
      <option value="3">Άλλοι φόροι</option>
      <option value="4">Ψηφιακό Τέλος Συναλλαγής</option>
      <option value="5">Κρατήσεις</option>
    </select></div>
  <div class="field" id="txCatField" style="margin-top:8px"><label>Κατηγορία Φόρου *</label>
    <select id="txCat"><option value="">Επιλέξτε…</option></select></div>
  <div class="row" style="margin-top:8px">
    <div class="field"><label>Ποσό Φόρου (€) *</label><input id="txAmount" type="number" step="0.01" min="0" value="0"></div>
    <div class="field grow"><label>Σημειώσεις</label><input id="txNotes"></div>
  </div>
  <div id="txWarn" class="sub" style="color:#fcd34d;margin-top:6px"></div>
  <div id="txErr" class="sub" style="color:#fca5a5;margin-top:2px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="taxModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveTax()">Αποθήκευση</button>
  </div>
</div></dialog>

<!-- Issue confirmation -->
<dialog id="issueConfirm"><div class="modal-body" style="max-width:460px">
  <div class="modal-head" id="icHead">Επιβεβαίωση έκδοσης</div>
  <div id="icBody" class="sub" style="margin:6px 0 4px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="issueConfirm.close()">Άκυρο</button>
    <button class="primary" id="icOk" onclick="issueConfirm.close();submitInvoice(true)">✔ Επιβεβαίωση</button>
  </div>
</div></dialog>

<!-- Schedule issuance modal -->
<dialog id="schedModal"><div class="modal-body" style="max-width:520px">
  <div class="modal-head">⏰ Προγραμματισμός έκδοσης</div>
  <div class="sub" style="margin:-4px 0 10px">Το παραστατικό θα εκδοθεί <b>οριστικά (με ΜΑΡΚ)</b> αυτόματα την ώρα που θα ορίσεις. Απαιτείται ενεργός runner (scheduler.php) στον server.</div>
  <div id="schedSummary" class="card" style="margin-bottom:10px"></div>
  <div class="row">
    <div class="field"><label>Ημερομηνία *</label><input id="schDate" type="date" onchange="schedDateNote()"></div>
    <div class="field"><label>Ώρα *</label><input id="schTime" type="time" value="09:00" onchange="schedDateNote()"></div>
    <div class="field grow"><label>Επανάληψη</label>
      <select id="schRec" onchange="schedDateNote()">
        <option value="none">Καμία (μία φορά)</option>
        <option value="daily">Καθημερινά</option>
        <option value="weekly">Εβδομαδιαία</option>
        <option value="monthly">Μηνιαία</option>
      </select></div>
  </div>
  <div id="schedWhenNote" class="scope-warn" style="margin-top:10px"></div>
  <div class="field" style="margin-top:8px"><label>Περιγραφή (προαιρετικό)</label><input id="schTitle" placeholder="π.χ. Μηνιαίο τιμολόγιο ΑCME"></div>
  <div id="schResult" style="margin-top:10px"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="schedModal.close()">Άκυρο</button>
    <button class="primary" onclick="confirmSchedule()">⏰ Προγραμματισμός</button>
  </div>
</div></dialog>

<!-- Command palette -->
<div id="palette"><div class="pal-box">
  <input id="palInput" placeholder="Αναζήτηση πελάτη (ΑΦΜ ή επωνυμία)… ↵ για καρτέλα">
  <div class="pal-results" id="palResults"></div>
</div></div>

<!-- Σήμα του γραφείου, σταθερά κάτω αριστερά. Δύο εκδοχές, μία ανά θέμα:
     το φωτεινό λογότυπο πάνω σε σκούρο φόντο χάνεται (και αντίστροφα). -->

<div class="toast" id="toast"></div>
<div id="colFilterPop"></div>

<!-- Guided page tour -->
<div id="tourOverlay"><div id="tourBackdrop" onclick="endTour()"></div><div id="tourRing"></div>
  <div id="tourBox">
    <h4 id="tourTitle"></h4><p id="tourText"></p>
    <div class="tour-actions">
      <button class="ghost sm" onclick="endTour()">Παράλειψη</button>
      <button class="ghost sm" id="tourPrev" onclick="tourPrev()">← Πίσω</button>
      <button class="primary sm" id="tourNext" onclick="tourNext()">Επόμενο →</button>
      <span class="tour-step" id="tourStep"></span>
    </div>
  </div>
</div>

<!-- Voice assistant / chatbot -->
<style>
#cbToggle{position:fixed;right:22px;bottom:22px;width:56px;height:56px;border-radius:50%;border:none;cursor:pointer;
  background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;font-size:24px;box-shadow:0 8px 24px rgba(0,0,0,.35);z-index:60}
#cbToggle:hover{transform:scale(1.06)}
#cbPanel{position:fixed;right:22px;bottom:88px;width:360px;max-width:calc(100vw - 44px);height:480px;max-height:calc(100vh - 130px);
  background:var(--panel,#141a24);border:1px solid rgba(255,255,255,.08);border-radius:16px;box-shadow:0 16px 48px rgba(0,0,0,.5);
  display:none;flex-direction:column;overflow:hidden;z-index:60}
#cbPanel.open{display:flex}
#cbHead{padding:12px 14px;background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff;font-weight:700;display:flex;align-items:center;gap:8px}
#cbHead .grow{flex:1}
#cbHead select{background:rgba(255,255,255,.15);color:#fff;border:1px solid rgba(255,255,255,.45);border-radius:8px;padding:3px 22px 3px 8px;font-size:12px;
  /* Το βελάκι του συστήματος χάνεται πάνω στη γαλάζια κεφαλίδα — ζωγραφίζεται
     εδώ, ώστε να φαίνεται ότι είναι επιλογέας και όχι ετικέτα. */
  appearance:none;-webkit-appearance:none;cursor:pointer;
  background-image:linear-gradient(45deg,transparent 50%,#fff 50%),linear-gradient(135deg,#fff 50%,transparent 50%);
  background-position:calc(100% - 12px) 50%,calc(100% - 8px) 50%;
  background-size:4px 4px,4px 4px;background-repeat:no-repeat}
/* ⚠️ Η ΛΙΣΤΑ του select τη ζωγραφίζει το λειτουργικό και κληρονομεί το
   ημιδιαφανές λευκό φόντο: λευκά γράμματα σε λευκό: φαινόταν μόνο η μία από τις
   δύο γλώσσες. Τα χρώματα δίνονται ρητά. */
#cbHead select option{background:var(--panel);color:var(--txt)}
#cbHead button{background:transparent;border:none;color:#fff;cursor:pointer;font-size:16px}
#cbLog{flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;background:rgba(0,0,0,.15)}
.cbMsg{max-width:82%;padding:8px 11px;border-radius:12px;font-size:13.5px;line-height:1.4;white-space:pre-wrap;word-break:break-word}
.cbMsg.bot{align-self:flex-start;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.06)}
.cbMsg.me{align-self:flex-end;background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff}
.cbMsg .cbAct{margin-top:6px;display:flex;gap:6px;flex-wrap:wrap}
.cbMsg .cbAct button{font-size:12px;padding:4px 10px;border-radius:8px;border:1px solid rgba(255,255,255,.2);background:rgba(255,255,255,.1);color:inherit;cursor:pointer}
.cbMsg .cbAct button.go{background:#16a34a;border-color:#16a34a;color:#fff}
#cbBar{display:flex;gap:6px;padding:10px;border-top:1px solid rgba(255,255,255,.08)}
#cbInput{flex:1;background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:8px 10px;color:inherit;font-size:13.5px}
#cbMic,#cbSend{border:none;border-radius:10px;cursor:pointer;padding:0 12px;font-size:16px}
#cbMic{background:rgba(255,255,255,.1);color:inherit}
#cbMic.rec{background:#dc2626;color:#fff;animation:cbPulse 1s infinite}
#cbSend{background:linear-gradient(135deg,#0ea5e9,#6366f1);color:#fff}
@keyframes cbPulse{0%,100%{opacity:1}50%{opacity:.5}}
#cbHint{font-size:11px;color:var(--muted,#8a94a6);padding:0 12px 8px}
</style>
<button id="cbToggle" title="Φωνητικός βοηθός" onclick="cbTogglePanel()">🎤</button>
<div id="cbPanel">
  <div id="cbHead"><span>🎤</span><span class="grow">Βοηθός</span>
    <select id="cbLang" title="Γλώσσα"><option value="el-GR">Ελληνικά</option><option value="en-US">English</option></select>
    <button title="Καθαρισμός" onclick="cbClear()">🗑</button>
    <button title="Κλείσιμο" onclick="cbTogglePanel()">✕</button></div>
  <div id="cbLog"></div>
  <div id="cbHint">π.χ. «έκδοση τιμολογίου στον 802012659 για 2 τεμ ΚΩΔ 10 ευρώ» · «μαζική εκτύπωση» · «ZIP παραστατικών» · «πόσες αδιάβαστες» · «ενεργοποίηση 2FA» · «βοήθεια»</div>
  <div id="cbBar">
    <input id="cbInput" placeholder="Γράψε ή πάτα το μικρόφωνο…" onkeydown="if(event.key==='Enter')cbSubmitText()">
    <button id="cbMic" title="Ομιλία" onclick="cbToggleMic()">🎙</button>
    <button id="cbSend" title="Αποστολή" onclick="cbSubmitText()">➤</button>
  </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.2/dist/jspdf.plugin.autotable.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/qrcode@1.5.1/build/qrcode.min.js"></script>
<script>
const API='etimologio.php';
const ROLE=<?= json_encode($__role) ?>;
const ME_ID=<?= (int)$__user['id'] ?>;
const IS_STAFF=<?= json_encode(in_array($__role, ['master','editor'], true)) ?>;
let ACCOUNT='';
const $=s=>document.querySelector(s);
const $$=s=>Array.from(document.querySelectorAll(s));
const fmt=n=>(Number(n)||0).toLocaleString('el-GR',{minimumFractionDigits:2,maximumFractionDigits:2});
// Parse a number that may be el-GR formatted (1.234,56) OR plain (1234.56 / 12.3456).
// Rule: if both separators present, the LAST one is the decimal; comma-only ⇒ decimal
// comma; dot-only ⇒ treated as a normal decimal point (matches product prices).
function elNum(v){if(typeof v==='number')return v;let s=(v==null?'':v).toString().trim();if(!s)return 0;
  s=s.replace(/[^\d,.\-]/g,'');const lc=s.lastIndexOf(','),ld=s.lastIndexOf('.');
  if(lc>-1&&ld>-1){s=lc>ld?s.replace(/\./g,'').replace(',','.'):s.replace(/,/g,'');}
  else if(lc>-1){s=s.replace(',','.');}
  return parseFloat(s)||0;}
// el-GR display: gross/totals = 2 decimals; unit price up to 4 (prices can be finer).
function elFmt(n,max=2){if(n===''||n==null||isNaN(Number(n)))return '';return (Number(n)).toLocaleString('el-GR',{minimumFractionDigits:2,maximumFractionDigits:max});}
// Format a line input field in place (on blur), preserving empty.
function elFmtField(el,max){if(!el)return;const v=(el.value||'').trim();if(v==='')return;el.value=elFmt(elNum(v),max);}
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const q1=s=>String(s??'').replace(/'/g,"\\'");
// Το PDF ενός παραστατικού: ΕΝΑ κουμπί, παντού το ίδιο (καρτέλα, παραστατικά,
// αποτέλεσμα έκδοσης). Παλιά ήταν σκέτος σύνδεσμος «PDF» και ο χρήστης δεν
// καταλάβαινε ότι πατιέται.
function docUrl(mark,download){return API+'?account='+encodeURIComponent(ACCOUNT)+'&mark='+encodeURIComponent(mark)+'&pdf_raw=1'+(download?'&dl=1':'');}
function docBtn(mark,label){if(!mark)return '';
  return `<button type="button" class="docbtn" onclick="event.stopPropagation();openDoc('${q1(mark)}',this)" title="Άνοιγμα του παραστατικού σε PDF">📗 ${esc(label||'Παραστατικό')}</button>`;}
// Το PDF έρχεται από την ΑΑΔΕ και αργεί 1-3 δευτερόλεπτα. Χωρίς ανάδραση, ο
// χρήστης πατούσε και «δεν γινόταν τίποτα» — και ξαναπατούσε.
async function openDoc(mark,btn){
  const old=btn?btn.innerHTML:'';
  if(btn){btn.disabled=true;btn.innerHTML='<span class="spin"></span> Λήψη…';}
  toast('Άνοιγμα παραστατικού… (ΜΑΡΚ '+mark+')');
  try{
    if(isEmbedded()){
      // Στην εφαρμογή υπολογιστή δεν υπάρχει καρτέλα browser να δείξει το PDF:
      // το κατεβάζουμε (ο χειριστής λήψεων το αποθηκεύει και το ανοίγει με τον
      // προβολέα του συστήματος, όπου δουλεύει και η εκτύπωση).
      location.href=docUrl(mark,true);
      toast('Το παραστατικό κατεβαίνει και θα ανοίξει','ok');
    }else{
      const w=window.open(docUrl(mark),'_blank','noopener');
      if(!w)toast('Επίτρεψε τα αναδυόμενα παράθυρα για να ανοίξει το PDF','warn');
      else toast('Το παραστατικό άνοιξε σε νέα καρτέλα','ok');
    }
  }catch(e){toast('Παραστατικό: '+e.message,'err');}
  finally{if(btn){setTimeout(()=>{btn.disabled=false;btn.innerHTML=old;},1200);}}
}
const PAYMETHODS={3:'Μετρητά',1:'Τραπεζική μεταφορά',4:'Επιταγή'};
function payMethod(m){return PAYMETHODS[parseInt(m,10)]||'';}
// Τρέχουμε μέσα στην εφαρμογή υπολογιστή (ενσωματωμένος browser) ή σε κανονικό
// browser; Αλλάζει τι μπορεί να γίνει με νέα παράθυρα και λήψεις.
function isEmbedded(){return document.body.classList.contains('embedded');}
function toast(m,t=''){const e=$('#toast');e.className='toast show '+t;e.textContent=m;clearTimeout(e._t);e._t=setTimeout(()=>e.className='toast',3400);}
// --- Κατάσταση σύνδεσης -------------------------------------------------------
// Τρεις πηγές, με αυτή τη σειρά αξιοπιστίας:
//   1. Ο server δοκιμάζει να φτάσει την ΑΑΔΕ (`?netcheck=1`) — η μόνη απόδειξη.
//   2. Μια κλήση που έσκασε με σφάλμα δικτύου, ή απάντηση με `offline:true`.
//   3. Το `navigator.onLine`, που λέει μόνο αν υπάρχει *κάποιο* δίκτυο: σε
//      router χωρίς γραμμή απαντά «ναι», γι' αυτό δεν αρκεί από μόνο του.
let NET_OFFLINE=false, NET_TIMER=null;

function netBar(on,why){
  const bar=$('#netBar');if(!bar)return;
  bar.classList.toggle('on',!!on);
  const app=document.querySelector('.app');if(app)app.classList.toggle('offline',!!on);
  if(why)$('#netBarWhy').textContent=why;
}

function netSetOffline(on,why){
  if(on===NET_OFFLINE){if(on&&why)netBar(true,why);return;}
  NET_OFFLINE=on;
  netBar(on,why);
  if(on){
    toast('Χάθηκε η σύνδεση στο internet','err');
    // Όσο είμαστε εκτός, ξαναδοκιμάζουμε μόνοι μας: ο χρήστης δεν χρειάζεται
    // να θυμάται να πατήσει κουμπί για να ξαναζωντανέψει η εφαρμογή.
    clearInterval(NET_TIMER);NET_TIMER=setInterval(()=>netRecheck(false),20000);
  }else{
    clearInterval(NET_TIMER);NET_TIMER=null;
    toast('Η σύνδεση επανήλθε','ok');
  }
}

// Αναγνωρίζει την αποτυχία ΔΙΚΤΥΟΥ του fetch. Το fetch πετά TypeError όταν δεν
// έφυγε καν το αίτημα — διαφορετικό από «ο server απάντησε σφάλμα».
function netIsFetchFailure(err){
  const m=String((err&&err.message)||err||'');
  return err instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(m);
}

async function netRecheck(loud){
  const btn=$('#netBarRetry');
  if(loud&&btn){btn.disabled=true;btn.textContent='Έλεγχος…';}
  try{
    const r=await fetch(API+'?netcheck=1',{cache:'no-store'});
    const d=await r.json();
    if(d.online)netSetOffline(false);
    else netSetOffline(true,d.reason||'');
  }catch(e){
    netSetOffline(true,'Ο υπολογιστής δεν έχει σύνδεση στο internet.');
  }finally{
    if(loud&&btn){btn.disabled=false;btn.textContent='↻ Έλεγχος ξανά';}
  }
}

// Το λειτουργικό μας λέει πότε ΣΙΓΟΥΡΑ χάθηκε το δίκτυο· η επιστροφή
// επιβεβαιώνεται με πραγματικό έλεγχο, γιατί «online» δεν σημαίνει «internet».
window.addEventListener('offline',()=>netSetOffline(true,'Ο υπολογιστής αποσυνδέθηκε από το δίκτυο.'));
window.addEventListener('online',()=>netRecheck(false));
if(navigator.onLine===false)netSetOffline(true,'Ο υπολογιστής αποσυνδέθηκε από το δίκτυο.');

// --- Theme (light / dark) -----------------------------------------------------
function applyTheme(t){const light=t==='light';document.documentElement.setAttribute('data-theme',light?'light':'dark');
  // Ο διακόπτης ακολουθεί την κατάσταση μέσω της κλάσης .on (όπως στην εφαρμογή
  // υπολογιστή): αναμμένος = φωτεινό θέμα. Η ετικέτα μένει σταθερή ώστε να
  // περιγράφει ΤΙ κάνει ο διακόπτης, όχι πού βρίσκεται τώρα.
  const tg=$('#themeToggle');if(tg)tg.classList.toggle('on',light);}
function toggleTheme(){const cur=document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';
  const next=cur==='light'?'dark':'light';localStorage.setItem('etim_theme',next);applyTheme(next);}
applyTheme(localStorage.getItem('etim_theme')||'dark');
// --- Tooltips on/off ----------------------------------------------------------
function applyTips(on){document.documentElement.classList.toggle('tips-off',!on);
  const t=$('#tipsToggle');if(t)t.classList.toggle('on',on);
  // Η ετικέτα μένει σταθερή, όπως στην εφαρμογή υπολογιστή: περιγράφει ΤΙ
  // ελέγχει ο διακόπτης — την κατάσταση τη δείχνει η ίδια η μπίλια.
}
function toggleTips(){const on=!document.documentElement.classList.contains('tips-off')?false:true;
  localStorage.setItem('etim_tips',on?'1':'0');applyTips(on);}
applyTips((localStorage.getItem('etim_tips')||'1')==='1');

async function api(params){const q=new URLSearchParams(params);if(ACCOUNT)q.set('account',ACCOUNT);
  let r;
  try{r=await fetch(API+'?'+q.toString());}
  catch(e){if(netIsFetchFailure(e))netSetOffline(true,'Ο υπολογιστής δεν έχει σύνδεση στο internet.');throw e;}
  const txt=await r.text();
  let d;try{d=JSON.parse(txt);}catch(e){throw new Error(txt.slice(0,200));}
  netNoteReply(d);
  return d;}

// Ο server ξεχωρίζει «δεν βγήκαμε στο internet» από «η ΑΑΔΕ δεν απαντά». Όταν
// το πει, ανάβει η μπάρα· όταν μια κλήση προς ΑΑΔΕ πετύχει, σβήνει.
function netNoteReply(d){
  if(!d||typeof d!=='object')return;
  if(d.offline)netSetOffline(true,d.error||'');
  else if(NET_OFFLINE&&d.success)netRecheck(false);
}

// Navigation
function showView(v){
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===v));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  $('#view-'+v).classList.add('active');
  // Κάθε πίνακας της ενότητας παίρνει φίλτρα + μεταβλητό πλάτος/σειρά στηλών.
  // Παλιά η λίστα ήταν γραμμένη με το χέρι, ανά ενότητα, και κάθε νέος πίνακας
  // ξεχνιόταν — γι' αυτό μερικοί είχαν χωνί και άλλοι όχι.
  enhanceViewTables(v);
  if(v==='stats')loadStats();
  if(v==='customers')loadCustomers();
  if(v==='documents')docsInit();
  if(v==='products'){loadProducts();loadCategories();loadCatCls();}
  if(v==='delivery'){if(!$('#dnDate').value)dset('dnDate',new Date().toISOString().slice(0,10));if(!$('#dnLines tbody').children.length)addDnLine();dnInit();}
  // Ο οδηγός ΞΑΝΑΡΩΤΑ σε κάθε είσοδο στην Έκδοση: φεύγοντας στην Καρτέλα και
  // επιστρέφοντας, η φόρμα είναι νέο παραστατικό — και ο τύπος/πελάτης πρέπει
  // να επιλεγούν ξανά, όχι να κληρονομηθούν σιωπηλά από την προηγούμενη φορά.
  if(v==='issue'){if(!$('#iLines tbody').children.length)addLine();loadIssueTypes();renderTaxes();loadTaxCats();
    if(!issueHasContent()){WIZ_DONE=false;ISSUE_WHO='';}
    wizShow(!WIZ_DONE);}
  if(v==='drafts')loadDrafts();
  if(v==='bankimp'){if(!ALL_CUSTOMERS.length)loadCustomers();}
  if(v==='bulk')loadBulkView();
  if(v==='schedule')loadSchedule();
  if(v==='series')loadSeriesView();
  if(v==='settings'){loadSettings();loadBankSettings(true);}
  if(v==='admin')loadAdmin();
}
function enhanceViewTables(v){
  const view=$('#view-'+v);if(!view)return;
  view.querySelectorAll('table[id]').forEach(t=>attachColumnFilters(t.id));
}
document.querySelectorAll('.nav-item').forEach(n=>n.onclick=()=>showView(n.dataset.view));

// Accounts
async function initAccounts(){
  try{const d=await api({accounts:1});const sel=$('#account');
    fillAccountSelect(sel,d.accounts||[],d.active||'');
    sel.onchange=()=>{ACCOUNT=sel.value;loadProductList();const v=document.querySelector('.nav-item.active').dataset.view;showView(v);};
  }catch(e){toast('Λογαριασμοί: '+e.message,'err');}
}
function fillAccountSelect(sel,accounts,active){
  const previous=sel.value;
  sel.innerHTML='';
  accounts.forEach(a=>{const o=document.createElement('option');o.value=a.vat;o.textContent=a.label+' ('+a.vat+')';sel.appendChild(o);});
  if(!accounts.length){const o=document.createElement('option');o.textContent='— κανένας λογαριασμός AADE —';sel.appendChild(o);}
  // Η επιλογή επιβιώνει το ξαναγέμισμα, εκτός αν η εταιρεία δεν υπάρχει πια.
  const keep=accounts.some(a=>a.vat===previous)?previous:'';
  ACCOUNT=keep||active||(accounts[0]&&accounts[0].vat)||'';
  sel.value=ACCOUNT;
}
// Ο επιλογέας εταιρείας ΔΕΝ ενημερωνόταν όταν προστίθετο ή αφαιρούνταν εταιρεία:
// έπρεπε να ξαναφορτώσεις τη σελίδα για να δεις αυτή που μόλις καταχώρησες.
async function refreshAccounts(){
  try{const d=await api({accounts:1});
    const before=ACCOUNT;
    fillAccountSelect($('#account'),d.accounts||[],d.active||'');
    if(ACCOUNT!==before){loadProductList();const nav=document.querySelector('.nav-item.active');if(nav)showView(nav.dataset.view);}
  }catch(e){}
}

// Auth: logout, settings, admin
async function logout(){
  // Η αποσύνδεση είναι δίπλα στο κουδουνάκι και πατιόταν κατά λάθος — και στην
  // εφαρμογή υπολογιστή σημαίνει ξαναγράψιμο κωδικού που παρήγαγε η ίδια.
  if(!confirm('Αποσύνδεση από την εφαρμογή;'))return;
  try{await fetch(API+'?auth=logout',{method:'POST'});}catch(e){}location.href='app.php';}
async function changePassword(){const o=$('#cpOld').value,n=$('#cpNew').value,n2=$('#cpNew2').value;
  if(n!==n2){$('#cpResult').textContent='Οι νέοι κωδικοί δεν ταιριάζουν.';return;}
  try{const b=new URLSearchParams({auth:'change_password',old_password:o,password:n});
    const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b});const d=await r.json();
    if(d.success){$('#cpResult').textContent='';toast('Ο κωδικός άλλαξε','ok');['cpOld','cpNew','cpNew2'].forEach(i=>$('#'+i).value='');}
    else $('#cpResult').textContent=d.error||'Αποτυχία';
  }catch(e){$('#cpResult').textContent='Σφάλμα δικτύου';}}
// --- Πάροχος email ------------------------------------------------------------
// Τα μυστικά (API key, κωδικός SMTP) ΔΕΝ κατεβαίνουν ποτέ: το backend στέλνει
// «__SET__» όταν υπάρχουν, και αν το πεδίο μείνει έτσι δεν τα πειράζει.
const MAIL_SECRET='__SET__';
async function loadMailSettings(){
  const box=$('#mpProvider'); if(!box)return;
  try{const d=await apost({auth:'mail_settings_get'});
    if(!d.success)return;
    const s=d.settings||{};
    $('#mpProvider').value=s.MAIL_PROVIDER||'auto';
    $('#mpFrom').value=s.SMTP_FROM||s.RESEND_EMAIL_SENDER||'';
    $('#mpNotify').value=s.NOTIFY_ADMIN_EMAIL||'';
    $('#mpHost').value=s.SMTP_HOST||''; $('#mpPort').value=s.SMTP_PORT||'';
    $('#mpUser').value=s.SMTP_USER||'';
    $('#mpSecure').value=s.SMTP_SECURE||(String(s.SMTP_PORT)==='465'?'ssl':'tls');
    $('#mpResend').value=s.RESEND_API_KEY===MAIL_SECRET?MAIL_SECRET:'';
    $('#mpPass').value=s.SMTP_PASS===MAIL_SECRET?MAIL_SECRET:'';
    const st=$('#mailStatus');
    st.textContent=d.enabled?('ενεργό · '+d.provider):'ανενεργό';
    st.className='pill '+(d.enabled?'ok':'');
    mpSyncFields();
    addEyes($('#view-settings'));
  }catch(e){}
}
// Οι ρυθμίσεις των γνωστών παρόχων. Ό,τι δεν είναι εδώ το γράφει ο χρήστης.
const MAIL_PRESETS={
  gmail:  {host:'smtp.gmail.com',    port:'587', secure:'tls',
           note:'Το Gmail ΔΕΝ δέχεται τον κανονικό σου κωδικό: φτιάξε «κωδικό εφαρμογής» (App password) με ενεργό 2FA στον λογαριασμό Google.'},
  outlook:{host:'smtp.office365.com',port:'587', secure:'tls',
           note:'Ο λογαριασμός πρέπει να έχει ενεργή «SMTP AUTH» από τον διαχειριστή του Microsoft 365.'},
  yahoo:  {host:'smtp.mail.yahoo.com',port:'465',secure:'ssl',
           note:'Το Yahoo θέλει κι αυτό κωδικό εφαρμογής, όχι τον κωδικό σύνδεσης.'},
  otenet: {host:'smtp.otenet.gr',    port:'25',  secure:'none',
           note:'Χωρίς κρυπτογράφηση — δουλεύει μόνο από γραμμή OTE.'},
};
function mpApplyPreset(){
  const p=MAIL_PRESETS[$('#mpPreset').value];if(!p)  {$('#mpSmtpHint').textContent='';return;}
  $('#mpHost').value=p.host;$('#mpPort').value=p.port;$('#mpSecure').value=p.secure;
  $('#mpSmtpHint').textContent=p.note;
}
// Δείχνει μόνο τα πεδία που αφορούν τον επιλεγμένο πάροχο.
function mpSyncFields(){
  const v=$('#mpProvider').value;
  const showResend=v!=='smtp', showSmtp=v!=='resend';
  $('#mpResendBox').style.display=showResend?'':'none';
  $('#mpSmtpBox').style.display=showSmtp?'':'none';
  if(showSmtp&&!$('#mpPreset').value){
    const host=($('#mpHost').value||'').toLowerCase();
    const hit=Object.entries(MAIL_PRESETS).find(([,p])=>host===p.host);
    if(hit){$('#mpPreset').value=hit[0];$('#mpSmtpHint').textContent=hit[1].note;}
  }
}
async function saveMailSettings(){
  const p={auth:'mail_settings_set',
    MAIL_PROVIDER:$('#mpProvider').value,
    SMTP_FROM:$('#mpFrom').value.trim(),
    RESEND_EMAIL_SENDER:$('#mpFrom').value.trim(),
    NOTIFY_ADMIN_EMAIL:$('#mpNotify').value.trim(),
    SMTP_HOST:$('#mpHost').value.trim(), SMTP_PORT:$('#mpPort').value.trim(),
    SMTP_SECURE:$('#mpSecure').value,
    SMTP_USER:$('#mpUser').value.trim(), SMTP_PASS:$('#mpPass').value,
    RESEND_API_KEY:$('#mpResend').value};
  try{const d=await apost(p);
    if(d.success){$('#mpResult').textContent='Αποθηκεύτηκε.';toast('Ο πάροχος email ενημερώθηκε','ok');loadMailSettings();}
    else $('#mpResult').textContent=d.error||'Αποτυχία';
  }catch(e){$('#mpResult').textContent='Σφάλμα δικτύου';}
}
async function testMailSettings(){
  $('#mpResult').innerHTML='<span class="spin"></span> Αποστολή δοκιμαστικού…';
  try{const d=await apost({auth:'mail_test',to:$('#mpTestTo').value.trim()});
    $('#mpResult').innerHTML=d.success
      ? '<span class="pill ok">Στάλθηκε</span> μέσω '+esc(d.provider||'')
      : '<span class="pill bad">'+esc(d.error||'Αποτυχία')+'</span>';
  }catch(e){$('#mpResult').textContent='Σφάλμα δικτύου';}
}

async function loadSettings(){
  // Πρώτα η κάρτα σύνδεσης: είναι τοπική και ακαριαία, ενώ η λίστα
  // λογαριασμών ΑΑΔΕ πιο κάτω περιμένει το δίκτυο — χωρίς αυτή τη σειρά, σε
  // υπολογιστή χωρίς σύνδεση η κάρτα έμενε άδεια για δευτερόλεπτα.
  loadLink();
  loadMailSettings();try{const d=await api({accounts:1});
  $('#settAccts tbody').innerHTML=(d.accounts||[]).map(a=>`<tr><td>${esc(a.vat)}</td><td>${esc(a.label)}</td><td class="muted">•••</td></tr>`).join('')||'<tr><td colspan="3" class="muted">Δεν έχει συνδεθεί λογαριασμός AADE.</td></tr>';
}catch(e){}
  load2fa();loadNotifPrefs();loadAccessKeys();}
// --- Κλειδιά πρόσβασης -------------------------------------------------------
// Το κλειδί είναι το μόνο που χρειάζεται η εφαρμογή υπολογιστή για να στραφεί σε
// αυτόν τον server: κουβαλά κωδικοποιημένη τη διεύθυνση, οπότε ο χρήστης δεν
// πληκτρολογεί URL που μπορεί να γράψει λάθος.
async function loadAccessKeys(){
  const el=$('#akTable');if(!el)return;
  try{const d=await apost({auth:'access_keys_list'});
    el.querySelector('tbody').innerHTML=(d.keys||[]).map(k=>`<tr>
      <td>${esc(k.label||'—')}</td><td>${esc((k.created_at||'').slice(0,16))}</td>
      <td>${esc(k.last_used_at||'—')}</td>
      <td>${k.revoked?'<span class="pill bad">ανακλήθηκε</span>':'<span class="pill ok">ενεργό</span>'}</td>
      <td class="right">${k.revoked?'':`<button class="danger sm" onclick="revokeAccessKey(${k.id})">Ανάκληση</button>`}</td></tr>`).join('')
      ||'<tr><td colspan="5" class="muted">Κανένα κλειδί.</td></tr>';
  }catch(e){}}
async function createAccessKey(){
  const label=prompt('Περιγραφή (π.χ. «Φορητός Μαρίας»):','');
  if(label===null)return;
  try{const d=await apost({auth:'access_key_create',label});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    // Δείχνεται ΜΙΑ φορά — γι' αυτό μένει στην οθόνη μέχρι να το αντιγράψει.
    $('#akNew').innerHTML=`<div class="card" style="border-left:4px solid var(--ok)">
      <b>Το κλειδί (αντίγραψέ το τώρα — δεν εμφανίζεται ξανά):</b>
      <div style="display:flex;gap:8px;margin-top:8px;align-items:center">
        <code id="akValue" style="flex:1;word-break:break-all;background:var(--panel2);border:1px solid var(--line);padding:8px 10px;border-radius:8px">${esc(d.key)}</code>
        <button class="primary sm" onclick="copyAccessKey()">📋 Αντιγραφή</button>
      </div></div>`;
    loadAccessKeys();
  }catch(e){toast('Κλειδί: '+e.message,'err');}}
function copyAccessKey(){const t=($('#akValue')||{}).textContent||'';
  navigator.clipboard.writeText(t).then(()=>toast('Αντιγράφηκε','ok'),()=>toast('Αντέγραψέ το με το ποντίκι','warn'));}
async function revokeAccessKey(id){
  if(!confirm('Ανάκληση του κλειδιού;\n\nΟ υπολογιστής που το χρησιμοποιεί θα χάσει τη σύνδεση.'))return;
  try{const d=await apost({auth:'access_key_revoke',key_id:id});
    if(!d.success)throw new Error('απέτυχε');toast('Ανακλήθηκε','ok');loadAccessKeys();
  }catch(e){toast('Κλειδί: '+e.message,'err');}}
// --- Email notification preferences (staff) ----------------------------------
async function loadNotifPrefs(){if(!IS_STAFF)return;
  try{const d=await apost({auth:'notif_prefs_get'});if(!d.success)return;
    const p=d.prefs||{},comps=d.companies||[];
    $('#npEnabled').checked=p.email_enabled!==false;
    const allComp=(p.companies||['*']).includes('*');
    $('#npCompAll').checked=allComp;
    $('#npCompanies').innerHTML=comps.map(c=>`<label class="np-check"><input type="checkbox" class="np-comp" value="${esc(c.vat)}"${(allComp||(p.companies||[]).includes(c.vat))?' checked':''}> ${esc(c.label)} <span class="muted">(${esc(c.vat)})</span></label>`).join('')||'<span class="muted">Καμία εταιρία.</span>';
    const allType=(p.types||['*']).includes('*');
    $('#npTypeAll').checked=allType;
    document.querySelectorAll('.np-type').forEach(cb=>cb.checked=allType||(p.types||[]).includes(cb.value));
    npSyncDisabled();
  }catch(e){}}
function npToggleAll(which){const all=$(which==='comp'?'#npCompAll':'#npTypeAll').checked;
  document.querySelectorAll(which==='comp'?'.np-comp':'.np-type').forEach(cb=>{cb.checked=all;cb.disabled=all;});}
function npSyncDisabled(){document.querySelectorAll('.np-comp').forEach(cb=>cb.disabled=$('#npCompAll').checked);
  document.querySelectorAll('.np-type').forEach(cb=>cb.disabled=$('#npTypeAll').checked);}
async function saveNotifPrefs(){
  const enabled=$('#npEnabled').checked;
  const companies=$('#npCompAll').checked?'*':[...document.querySelectorAll('.np-comp:checked')].map(c=>c.value).join(',');
  const types=$('#npTypeAll').checked?'*':[...document.querySelectorAll('.np-type:checked')].map(c=>c.value).join(',');
  if(enabled){
    if(companies!=='*'&&!companies){$('#npResult').textContent='Επίλεξε τουλάχιστον μία εταιρία (ή «Όλες»).';return;}
    if(types!=='*'&&!types){$('#npResult').textContent='Επίλεξε τουλάχιστον μία κίνηση (ή «Όλες»).';return;}
  }
  $('#npResult').textContent='Αποθήκευση…';
  try{const d=await apost({auth:'notif_prefs_set',email_enabled:enabled?'1':'0',companies,types});
    if(d.success){$('#npResult').innerHTML='<span class="pill ok">Αποθηκεύτηκε</span>';toast('Οι προτιμήσεις email αποθηκεύτηκαν','ok');}
    else $('#npResult').textContent=d.error||'Αποτυχία';
  }catch(e){$('#npResult').textContent='Σφάλμα δικτύου';}}
// --- 2FA (authenticator) -----------------------------------------------------
let TWOFA_ENABLED=null;
async function load2fa(){try{const d=await apost({auth:'me'});TWOFA_ENABLED=!!(d.user&&d.user.totp_enabled);render2fa();}catch(e){}}
function render2fa(){const on=TWOFA_ENABLED;
  $('#twofaState').innerHTML=on?'<span class="pill ok">ενεργό</span>':'<span class="pill">ανενεργό</span>';
  $('#twofaDisabled').style.display=on?'none':'';
  $('#twofaEnabled').style.display=on?'':'none';
  $('#twofaSetup').style.display='none';$('#twofaResult').textContent='';}
async function start2fa(){$('#twofaResult').textContent='';
  try{const d=await apost({auth:'totp_setup'});
    if(!d.success){$('#twofaResult').textContent=d.error||'Αποτυχία';return;}
    $('#twofaSecret').textContent=d.secret;$('#twofaCode').value='';
    $('#twofaDisabled').style.display='none';$('#twofaSetup').style.display='';
    const box=$('#twofaQr');box.innerHTML='';
    if(window.QRCode){QRCode.toCanvas(d.otpauth,{width:176,margin:1},(err,cv)=>{if(!err){box.appendChild(cv);}else{box.innerHTML='<span class="muted" style="font-size:11px">QR σφάλμα — χρησιμοποίησε το κλειδί</span>';}});}
    else{box.innerHTML='<span class="muted" style="font-size:11px">Χρησιμοποίησε το κλειδί δεξιά</span>';}
    setTimeout(()=>$('#twofaCode').focus(),60);
  }catch(e){$('#twofaResult').textContent='Σφάλμα δικτύου';}}
function cancel2fa(){render2fa();}
async function confirm2fa(){const code=$('#twofaCode').value.trim();if(!/^\d{6}$/.test(code)){$('#twofaResult').textContent='Δώσε 6ψήφιο κωδικό.';return;}
  try{const d=await apost({auth:'totp_enable',code});
    if(d.success){toast('Το 2FA ενεργοποιήθηκε','ok');TWOFA_ENABLED=true;render2fa();}
    else $('#twofaResult').textContent=d.error||'Αποτυχία';}catch(e){$('#twofaResult').textContent='Σφάλμα δικτύου';}}
async function disable2fa(){const v=$('#twofaOff').value.trim();if(!v){$('#twofaResult').textContent='Δώσε κωδικό authenticator ή το password σου.';return;}
  try{const d=await apost({auth:'totp_disable',verify:v});
    if(d.success){toast('Το 2FA απενεργοποιήθηκε','ok');TWOFA_ENABLED=false;$('#twofaOff').value='';render2fa();}
    else $('#twofaResult').textContent=d.error||'Αποτυχία';}catch(e){$('#twofaResult').textContent='Σφάλμα δικτύου';}}
async function apost(params){const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(params)});return r.json();}
// Η Διαχείριση δουλεύει και για τον λογιστή, με ΑΛΛΟ περιεχόμενο: ο διαχειριστής
// βλέπει μέλη + κάθε εταιρεία, ο λογιστής μόνο τις δικές του και χωρίς μέλη.
let ADMIN_SCOPE={is_master:false,accounts:[],accountants:[]};
async function loadAdmin(){
  try{
    const s=await apost({auth:'admin_scope'});
    if(s.success)ADMIN_SCOPE=s;
    renderScopeBanner();
    renderBiz(ADMIN_SCOPE.accounts||[]);
    if(ADMIN_SCOPE.is_master){
      const d=await apost({auth:'admin_users'});renderAdmin(d.users||[]);
    }
    loadWorkTime();loadAuditLog();
    enhanceViewTables('admin');
  }catch(e){toast('Διαχείριση: '+e.message,'err');}}

// --- Χρονομέτρηση ------------------------------------------------------------
function hhmm(secs){const h=Math.floor(secs/3600),m=Math.round((secs%3600)/60);
  return h?(h+'ω '+String(m).padStart(2,'0')+'λ'):(m+'λ');}
async function loadWorkTime(){
  const el=$('#wtTable');if(!el)return;
  try{const d=await api({work_report:1,from:di('wtFrom'),to:di('wtTo')});
    const rows=d.rows||[];
    el.querySelector('tbody').innerHTML=rows.map(r=>`<tr>
      <td>${esc(r.company||r.account_vat)}</td><td>${esc(r.user_label)}</td>
      <td class="num">${esc(hhmm(r.seconds))}</td><td>${esc(r.last_at||'')}</td></tr>`).join('')
      ||'<tr><td colspan="4" class="muted">Καμία καταγραφή στο διάστημα.</td></tr>';
  }catch(e){}}
// Ο παλμός: μετρά ΜΟΝΟ όταν η καρτέλα είναι ορατή. Χωρίς αυτό, ένα ανοιχτό tab
// σε άλλη οθόνη θα χρέωνε ώρες που δεν δούλεψε κανείς.
const WORK_PING_SEC=60;
let WORK_ACC=0;
setInterval(()=>{
  if(document.hidden||!ACCOUNT){WORK_ACC=0;return;}
  WORK_ACC+=5;
  if(WORK_ACC>=WORK_PING_SEC){const secs=WORK_ACC;WORK_ACC=0;
    api({work_ping:1,seconds:secs}).catch(()=>{});}
},5000);

// --- Ημερολόγιο ενεργειών ----------------------------------------------------
const AUDIT_LABELS={login:'Σύνδεση',login_2fa:'Σύνδεση (2FA)',logout:'Αποσύνδεση',
  issue:'Έκδοση',payment_update:'Αλλαγή πληρωμής',payment_delete:'Διαγραφή πληρωμής',
  email_sent:'Αποστολή email'};
async function loadAuditLog(){
  const el=$('#alTable');if(!el)return;
  try{const d=await api({audit_log:1,f_action:$('#alAction').value,limit:300});
    el.querySelector('tbody').innerHTML=(d.rows||[]).map(r=>{
      const det=Object.entries(r.detail||{}).filter(([,v])=>v!==''&&v!==null)
        .map(([k,v])=>k+': '+v).join(' · ');
      return `<tr><td>${esc(r.created_at)}</td><td>${esc(r.user_email||('#'+r.user_id))}</td>
        <td>${esc(r.account_vat||'—')}</td>
        <td><span class="pill">${esc(AUDIT_LABELS[r.action]||r.action)}</span></td>
        <td title="${esc(det)}">${esc(det)}</td></tr>`;}).join('')
      ||'<tr><td colspan="5" class="muted">Καμία καταγραφή.</td></tr>';
  }catch(e){}}
function renderScopeBanner(){
  const master=ADMIN_SCOPE.is_master,n=(ADMIN_SCOPE.accounts||[]).length;
  $('#adminIntro').textContent=master
    ? 'Μέλη, ρόλοι, αναθέσεις και διαπιστευτήρια AADE — για ολόκληρη την εγκατάσταση.'
    : 'Οι εταιρείες που σου έχουν ανατεθεί, με τα διαπιστευτήρια AADE τους.';
  const unassigned=(ADMIN_SCOPE.accountants||[]).filter(a=>!(a.account_ids||[]).length);
  $('#adminScope').innerHTML=master
    ? `<div class="scope-row"><span class="pill ok">🛡️ Διαχειριστής</span>
        <span>Βλέπεις <b>όλες</b> τις εταιρείες (${n}) και <b>όλους</b> τους λογιστές (${(ADMIN_SCOPE.accountants||[]).length}).</span></div>`
      + (unassigned.length?`<div class="scope-warn">⚠️ ${unassigned.length} λογιστ${unassigned.length===1?'ής χωρίς καμία ανατεθειμένη εταιρεία':'ές χωρίς καμία ανατεθειμένη εταιρεία'}: ${unassigned.map(a=>esc(a.name||a.email)).join(', ')}. Δεν βλέπουν τίποτα μέχρι να τους αναθέσεις.</div>`:'')
    : `<div class="scope-row"><span class="pill">🧮 Λογιστής</span>
        <span>Βλέπεις <b>${n}</b> εταιρεί${n===1?'α':'ες'} — μόνο όσες σου έχει αναθέσει ο διαχειριστής. Οι υπόλοιπες δεν εμφανίζονται πουθενά στην εφαρμογή.</span></div>`;
}
function renderBiz(accs){const el=$('#adminBiz');if(!el)return;
  const master=ADMIN_SCOPE.is_master;
  const byId={};(ADMIN_SCOPE.accountants||[]).forEach(a=>byId[a.id]=a.name||a.email);
  $('#adminBizCount').textContent=accs.length+(master?' επιχειρήσεις (όλες)':' ανατεθειμένες επιχειρήσεις');
  $('#adminBizNote').textContent=master
    ? 'Κάθε γραμμή ανοίγει τη δική της καρτέλα: διαπιστευτήρια, κάτοχος και ποιοι λογιστές έχουν πρόσβαση.'
    : 'Μπορείς να διορθώσεις τα διαπιστευτήρια AADE των δικών σου εταιρειών. Η ανάθεση γίνεται από τον διαχειριστή.';
  el.querySelector('tbody').innerHTML=accs.map(a=>{
    const mgrs=(a.manager_ids||[]).map(id=>byId[id]).filter(Boolean);
    const who=master?(mgrs.length?mgrs.map(esc).join(', '):'<span class="pill warn">κανένας</span>'):'<span class="muted">εσύ</span>';
    return `<tr>
    <td><b>${esc(a.label||'—')}</b></td><td>${esc(a.vat||'')}</td><td>${esc(a.owner_email||'—')}</td><td>${who}</td>
    <td class="right"><button class="primary sm" onclick="openCompany(${a.id})" data-tip="Άνοιγμα της καρτέλας αυτής της εταιρείας">✎ Επεξεργασία</button></td></tr>`;}).join('')
    ||`<tr><td colspan="5" class="muted">${master?'Καμία συνδεδεμένη επιχείρηση. Πάτησε «+ Νέα επιχείρηση».':'Δεν σου έχει ανατεθεί καμία εταιρεία ακόμη.'}</td></tr>`;}

// --- Μία εταιρεία, μία φόρμα -------------------------------------------------
let CO_ID=0;
// Ο λογιστής ανοίγει δική του εταιρεία χωρίς να περάσει από τον διαχειριστή:
// δημιουργείται με κάτοχο τον ίδιο και ανατίθεται αυτόματα σε αυτόν. Ο
// διαχειριστής τη βλέπει ούτως ή άλλως — δεν φιλτράρεται ποτέ γι' αυτόν.
function openNewCompany(){
  CO_ID=0;
  $('#coTitle').textContent='Νέα εταιρεία';
  $('#coSub').innerHTML=ADMIN_SCOPE.is_master
    ? 'Η εταιρεία θα καταχωρηθεί σε εσένα. Την ανάθεση σε λογιστές τη ρυθμίζεις πιο κάτω.'
    : 'Η εταιρεία καταχωρείται στο γραφείο σου και σου ανατίθεται αμέσως.';
  ['coVat','coLabel','coUser','coKey'].forEach(i=>$('#'+i).value='');
  $('#coKey').placeholder='(υποχρεωτικό)';
  $('#coKeyHint').textContent='Το username και το subscription key τα δίνει το e-timologio της ΑΑΔΕ για τη συγκεκριμένη επιχείρηση.';
  $('#coResult').textContent='';
  const box=$('#coManagers');if(box)box.innerHTML='<span class="muted">Διαθέσιμο μετά την αποθήκευση.</span>';
  const del=$('#coDelete');if(del)del.style.display='none';
  companyModal.showModal();
  setTimeout(()=>$('#coVat').focus(),40);
}
async function openCompany(id){
  CO_ID=id;$('#coResult').textContent='';$('#coKey').value='';
  try{const d=await apost({auth:'admin_account_get',account_id:id});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    const a=d.account||{};
    $('#coTitle').textContent=a.label||a.vat||'Εταιρεία';
    $('#coSub').innerHTML=`Κάτοχος: <b>${esc(a.owner_name||a.owner_email||'—')}</b>`+
      (a.created_at?` · καταχωρήθηκε ${esc(String(a.created_at).slice(0,10))}`:'');
    $('#coVat').value=a.vat||'';$('#coLabel').value=a.label||'';$('#coUser').value=a.username||'';
    $('#coKeyHint').innerHTML=a.subkey_set
      ? 'Το subscription key είναι αποθηκευμένο κρυπτογραφημένα. Άφησέ το κενό για να μείνει ως έχει.'
      : '<span class="pill bad">Δεν έχει οριστεί subscription key</span> — η εταιρεία δεν μπορεί να συνδεθεί στην ΑΑΔΕ.';
    const box=$('#coManagers');
    if(box){const sel=new Set(a.manager_ids||[]);
      box.innerHTML=(ADMIN_SCOPE.accountants||[]).map(m=>
        `<label class="np-check"><input type="checkbox" class="co-mgr" value="${m.id}"${sel.has(m.id)?' checked':''}> ${esc(m.name||m.email)} <span class="muted">${esc(m.email)}</span></label>`
      ).join('')||'<span class="muted">Δεν υπάρχουν λογιστές. Πρόσκαλεσε έναν από τα «Μέλη».</span>';}
    $('#coKey').placeholder='(αμετάβλητο)';
    const del=$('#coDelete');if(del)del.style.display='';
    companyModal.showModal();
  }catch(e){toast('Εταιρεία: '+e.message,'err');}}
let coVatT;
function coVatLookup(){clearTimeout(coVatT);coVatT=setTimeout(async()=>{const vat=$('#coVat').value.trim();
  if(!/^\d{9}$/.test(vat))return;const name=await nameForVat(vat);
  if(name&&!$('#coLabel').value.trim())$('#coLabel').value=name;},400);}
async function saveCompany(){
  const vat=$('#coVat').value.trim();
  if(!/^\d{9}$/.test(vat)){$('#coResult').textContent='ΑΦΜ 9 ψηφίων.';return;}
  if(!CO_ID){
    if(!$('#coUser').value.trim()||!$('#coKey').value){$('#coResult').textContent='Συμπλήρωσε username και subscription key.';return;}
    $('#coResult').textContent='Δημιουργία…';
    try{const d=await apost({auth:'staff_add_company',vat,label:$('#coLabel').value.trim(),
        username:$('#coUser').value.trim(),subkey:$('#coKey').value});
      if(!d.success)throw new Error(d.error||'σφάλμα');
      companyModal.close();toast('Η εταιρεία προστέθηκε','ok');loadAdmin();refreshAccounts();
    }catch(e){$('#coResult').textContent='Εταιρεία: '+e.message;}
    return;
  }
  const p={auth:'admin_account_save',account_id:CO_ID,vat,label:$('#coLabel').value.trim(),
           username:$('#coUser').value.trim(),subkey:$('#coKey').value};
  const box=$('#coManagers');
  if(box)p.manager_ids=[...document.querySelectorAll('.co-mgr:checked')].map(c=>c.value).join(',');
  $('#coResult').textContent='Αποθήκευση…';
  try{const d=await apost(p);
    if(!d.success)throw new Error(d.error||'σφάλμα');
    companyModal.close();toast('Η εταιρεία ενημερώθηκε','ok');loadAdmin();refreshAccounts();
  }catch(e){$('#coResult').textContent='Εταιρεία: '+e.message;}}
async function deleteCompany(){
  if(!confirm('Διαγραφή της εταιρείας και των διαπιστευτηρίων της;\n\nΗ ενέργεια δεν αναιρείται.'))return;
  try{const d=await apost({auth:'admin_delete_account',account_id:CO_ID});
    if(!d.success)throw new Error('απέτυχε');
    companyModal.close();toast('Διαγράφηκε','ok');loadAdmin();refreshAccounts();
  }catch(e){toast('Διαγραφή: '+e.message,'err');}}

// --- Ανάθεση εταιρειών σε λογιστή -------------------------------------------
let AS_USER=0,AS_SEL=new Set();
function openAssign(userId,name){
  AS_USER=userId;$('#asWho').textContent=name;$('#asResult').textContent='';$('#asFilter').value='';
  const acc=(ADMIN_SCOPE.accountants||[]).find(a=>a.id===userId);
  AS_SEL=new Set((acc&&acc.account_ids)||[]);
  renderAssign();assignModal.showModal();}
function renderAssign(){
  const term=($('#asFilter').value||'').toLowerCase().trim();
  const rows=(ADMIN_SCOPE.accounts||[]).filter(a=>!term||((a.label||'')+' '+(a.vat||'')).toLowerCase().includes(term));
  $('#asList').innerHTML=rows.map(a=>
    `<label class="np-check"><input type="checkbox" class="as-cb" value="${a.id}"${AS_SEL.has(a.id)?' checked':''} onchange="asChanged(${a.id},this.checked)"> ${esc(a.label||a.vat)} <span class="muted">(${esc(a.vat)})</span></label>`
  ).join('')||'<span class="muted">Καμία εταιρεία.</span>';}
function asChanged(id,on){on?AS_SEL.add(id):AS_SEL.delete(id);}
function asToggleAll(on){(ADMIN_SCOPE.accounts||[]).forEach(a=>on?AS_SEL.add(a.id):AS_SEL.delete(a.id));renderAssign();}
async function saveAssign(){
  $('#asResult').textContent='Αποθήκευση…';
  try{const d=await apost({auth:'admin_set_managers',user_id:AS_USER,account_ids:[...AS_SEL].join(',')});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    assignModal.close();toast('Η ανάθεση αποθηκεύτηκε','ok');loadAdmin();
  }catch(e){$('#asResult').textContent='Ανάθεση: '+e.message;}}
const ROLE_LABELS={master:'Διαχειριστής',editor:'Λογιστής',business:'Επιχείρηση'};
let ADMIN_ME=ME_ID;
let ADMIN_USERS=[];        // η τελευταία λίστα χρηστών — τη θέλουν και οι επιλογείς των κλειδιών
function renderAdmin(users){ADMIN_USERS=users||[];$('#adminUsers tbody').innerHTML=users.map(u=>{
  const st=u.status==='active'?'<span class="pill ok">ενεργός</span>':u.status==='pending'?'<span class="pill warn">εκκρεμεί</span>':u.status==='invited'?'<span class="pill">προσκεκλημένος</span>':'<span class="pill bad">ανενεργός</span>';
  const staff=u.role==='master'||u.role==='editor';
  const self=u.id===ADMIN_ME;
  const roleCell=self?`<b>${esc(ROLE_LABELS[u.role]||u.role)}</b> 🛡️`
    :`<select class="rolesel" onchange="setRole(${u.id},this.value)">
        ${['master','editor','business'].map(r=>`<option value="${r}"${u.role===r?' selected':''}>${ROLE_LABELS[r]}</option>`).join('')}
      </select>`;
  const twofa=u.totp_enabled?'<span class="pill ok">✔</span>':'<span class="muted">—</span>';
  let act='';
  if(!self){
    if(u.status==='pending'||u.status==='invited')act+=`<button class="primary sm" onclick="approveUser(${u.id})">Έγκριση</button> `;
    if(u.status!=='disabled')act+=`<button class="danger sm" onclick="setStatus(${u.id},'disabled')">Απενεργ.</button> `;
    else act+=`<button class="ghost sm" onclick="setStatus(${u.id},'active')">Ενεργοπ.</button> `;
    act+=`<button class="ghost sm" onclick="resetPw(${u.id})">Reset</button> `;
    act+=`<button class="danger sm" onclick="deleteUser(${u.id},'${q1(u.email)}')">Διαγραφή</button>`;
  }
  // Η στήλη «Εταιρείες» λέει ΠΟΣΕΣ και ανοίγει τον σωστό διάλογο ανά ρόλο:
  // ο διαχειριστής τα βλέπει όλα, ο λογιστής παίρνει ανάθεση, η επιχείρηση
  // έχει δικούς της λογαριασμούς AADE.
  const n=(u.account_ids||[]).length;
  const accBtn=u.role==='master'
    ? '<span class="muted">όλες</span>'
    : u.role==='editor'
      ? `<button class="${n?'ghost':'danger'} sm" onclick="openAssign(${u.id},'${q1(u.business_name||u.email)}')" data-tip="Ποιες εταιρείες βλέπει αυτός ο λογιστής">${n?('🔗 '+n+' εταιρείες'):'⚠️ καμία — ανάθεση'}</button>`
      : `<button class="ghost sm" onclick="openAcctModal(${u.id},'${q1(u.business_name||u.email)}')">${n?(n+' · διαχείριση'):'+ προσθήκη'}</button>`;
  return `<tr><td>${esc(u.business_name||'—')}</td><td>${esc(u.email)}</td><td>${roleCell}</td><td>${st}</td><td>${twofa}</td><td>${accBtn}</td><td class="right">${act}</td></tr>`;
}).join('')||'<tr><td colspan="7" class="muted">Καμία εγγραφή.</td></tr>';}
async function setRole(id,role){const d=await apost({auth:'admin_set_role',user_id:id,role});if(d.success){toast('Ο ρόλος ενημερώθηκε','ok');loadAdmin();}else{toast(d.error||'Αποτυχία','err');loadAdmin();}}
function openInviteModal(){$('#invEmail').value='';$('#invName').value='';$('#invRole').value='editor';$('#invResult').innerHTML='';inviteModal.showModal();}
async function sendInvite(){const email=$('#invEmail').value.trim(),role=$('#invRole').value,name=$('#invName').value.trim();
  if(!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)){$('#invResult').innerHTML='<span class="pill bad">Μη έγκυρο email</span>';return;}
  $('#invResult').innerHTML='<span class="spin"></span> Αποστολή…';
  try{const d=await apost({auth:'admin_invite',email,role,name});
    if(d.success){let h=`<div class="card"><span class="pill ok">${d.emailed?'Στάλθηκε πρόσκληση':'Πρόσκληση δημιουργήθηκε'}</span>`;
      if(!d.emailed)h+=`<div style="margin-top:8px">Δώσε χειροκίνητα τον σύνδεσμο ενεργοποίησης:<br><code style="word-break:break-all">${esc(d.invite_link)}</code></div>`;
      h+='</div>';$('#invResult').innerHTML=h;loadAdmin();}
    else $('#invResult').innerHTML='<span class="pill bad">'+esc(d.error||'Αποτυχία')+'</span>';
  }catch(e){$('#invResult').innerHTML='<span class="pill bad">Σφάλμα δικτύου</span>';}}
async function approveUser(id){if(!confirm('Έγκριση χρήστη;'))return;const d=await apost({auth:'admin_approve',user_id:id});if(d.success){toast('Εγκρίθηκε','ok');loadAdmin();}else toast(d.error||'Αποτυχία','err');}
async function setStatus(id,s){const d=await apost({auth:'admin_set_status',user_id:id,status:s});if(d.success){toast('Ενημερώθηκε','ok');loadAdmin();}else toast(d.error||'Αποτυχία','err');}
async function resetPw(id){const d=await apost({auth:'admin_reset_pw',user_id:id});if(d.success){prompt('Σύνδεσμος επαναφοράς (δώστε τον στον χρήστη — ισχύει 24ω):',d.reset_link);}else toast(d.error||'Αποτυχία','err');}
function openUserModal(){['uVat','uName','uUsername','uKey','uEmail','uPass'].forEach(i=>$('#'+i).value='');$('#uErr').textContent='';userModal.showModal();}
// Look up the company name from the ΑΦΜ (via the admin's AADE session)
async function nameForVat(vat){try{const d=await api({taxis_name:1,vat});return d.success?d.name:'';}catch(e){return'';}}
let uVatT;
function uVatLookup(){clearTimeout(uVatT);uVatT=setTimeout(async()=>{const vat=$('#uVat').value.trim();if(!/^\d{9}$/.test(vat))return;
  const name=await nameForVat(vat);if(name&&!$('#uName').value.trim())$('#uName').value=name;},400);}
async function createUser(){const vat=$('#uVat').value.trim(),name=$('#uName').value.trim(),email=$('#uEmail').value.trim(),pass=$('#uPass').value;
  const username=$('#uUsername').value.trim(),key=$('#uKey').value.trim();
  if(!/^\d{9}$/.test(vat)){$('#uErr').textContent='ΑΦΜ 9 ψηφίων.';return;}
  if(!name||!email||pass.length<8){$('#uErr').textContent='Συμπλήρωσε επωνυμία, email και κωδικό ≥ 8.';return;}
  if(!username||!key){$('#uErr').textContent='Συμπλήρωσε username και subscription key AADE.';return;}
  $('#uErr').textContent='';
  const d=await apost({auth:'admin_create_user',email,password:pass,business_name:name});
  if(!d.success){$('#uErr').textContent=d.error||'Αποτυχία';return;}
  // fetch the new user's id, then link the AADE account
  const users=(await apost({auth:'admin_users'})).users||[];const nu=users.find(u=>u.email===email.toLowerCase());
  if(nu){await apost({auth:'admin_add_account',user_id:nu.id,vat,label:name,username,subkey:key});}
  userModal.close();toast('Η επιχείρηση δημιουργήθηκε','ok');loadAdmin();refreshAccounts();}
let AM_USER=0;
async function openAcctModal(userId,name){AM_USER=userId;$('#amUser').textContent=name;['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');await loadUserAccounts();acctModal.showModal();}
async function loadUserAccounts(){const d=await apost({auth:'admin_user_accounts',user_id:AM_USER});
  $('#amList tbody').innerHTML=(d.accounts||[]).map(a=>`<tr><td>${esc(a.vat)}</td><td>${esc(a.label)}</td><td>${esc(a.username)}</td>
    <td class="right"><button class="ghost sm" onclick="acctModal.close();openCompany(${a.id})" data-tip="Πλήρης καρτέλα εταιρείας">✎ Επεξεργασία</button>
    <button class="danger sm" onclick="delAccount(${a.id})">✕</button></td></tr>`).join('')||'<tr><td colspan="4" class="muted">Κανένας λογαριασμός.</td></tr>';}
let amVatT;
function amVatLookup(){clearTimeout(amVatT);amVatT=setTimeout(async()=>{const vat=$('#amVat').value.trim();if(!/^\d{9}$/.test(vat))return;
  const name=await nameForVat(vat);if(name&&!$('#amLabel').value.trim())$('#amLabel').value=name;},400);}
async function addAccount(){const vat=$('#amVat').value.trim();if(!/^\d{9}$/.test(vat)){toast('ΑΦΜ 9 ψηφίων','err');return;}
  let label=$('#amLabel').value.trim();if(!label)label=await nameForVat(vat);
  const d=await apost({auth:'admin_add_account',user_id:AM_USER,vat,label,username:$('#amUsername').value,subkey:$('#amKey').value});
  if(d.success){['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');toast('Προστέθηκε','ok');loadUserAccounts();refreshAccounts();}else toast(d.error||'Αποτυχία','err');}
// (Υπήρχε δύο φορές, πανομοιότυπη.)
async function delAccount(id){if(!confirm('Διαγραφή λογαριασμού AADE;'))return;
  const d=await apost({auth:'admin_delete_account',account_id:id});
  if(d.success){toast('Διαγράφηκε','ok');loadUserAccounts();refreshAccounts();}else toast(d.error||'Αποτυχία','err');}
// Οριστική διαγραφή χρήστη. Το backend αρνείται τον εαυτό σου και τον τελευταίο
// διαχειριστή — εδώ λέμε μόνο πόσες εταιρείες φεύγουν μαζί, γιατί τα κλειδιά
// ΑΑΔΕ τους σβήνονται μαζί τους και δεν ανακτώνται.
async function deleteUser(id,email){
  let extra='';
  try{const a=await apost({auth:'admin_user_accounts',user_id:id});
    const n=(a.accounts||[]).length;
    if(n)extra=`\n\nΜαζί του διαγράφονται ${n} εταιρείες με τα κλειδιά ΑΑΔΕ τους.`;
  }catch(e){}
  if(!confirm(`Οριστική διαγραφή του «${email}»;${extra}\n\nΗ ενέργεια δεν αναιρείται.`))return;
  const d=await apost({auth:'admin_delete_user',user_id:id});
  if(d.success){toast('Ο χρήστης διαγράφηκε','ok');loadAdmin();refreshAccounts();}
  else toast(d.error||'Αποτυχία','err');}

// Statistics
let STAT_PERIOD='month';
document.querySelectorAll('#statPeriod button').forEach(b=>b.onclick=()=>{document.querySelectorAll('#statPeriod button').forEach(x=>x.classList.remove('on'));b.classList.add('on');STAT_PERIOD=b.dataset.p;loadStats();});
async function loadStats(){
  $('#statCards').innerHTML='<div class="card"><div class="v"><span class="spin"></span></div></div>';
  $('#statTable tbody').innerHTML='';
  try{const d=await api({statistics:1,period:STAT_PERIOD});if(!d.success)throw new Error(d.error||'σφάλμα');
    $('#statCards').innerHTML=
      `<div class="card"><div class="k">Συνολικός τζίρος</div><div class="v money">${fmt(d.total_value)} €</div></div>`+
      `<div class="card"><div class="k">Πλήθος παραστατικών</div><div class="v">${d.total_count}</div></div>`+
      `<div class="card"><div class="k">Κατηγορίες</div><div class="v">${d.breakdown.length}</div></div>`;
    const max=Math.max(1,...d.breakdown.map(b=>b.value));
    $('#statTable tbody').innerHTML=d.breakdown.map(b=>`<tr><td><span class="pill" title="${esc(invName(b.type))}">${esc(b.type)}</span> ${esc(invName(b.type))}</td><td class="num">${b.count}</td><td class="num">${fmt(b.value)}</td><td><div class="bar"><i style="width:${Math.round(b.value/max*100)}%"></i></div></td></tr>`).join('')||'<tr><td colspan="4" class="muted">Δεν υπάρχουν δεδομένα.</td></tr>';
    STAT_DATA=d.breakdown||[];
    renderStatChart();
  }catch(e){$('#statCards').innerHTML='';toast('Στατιστικά: '+e.message,'err');}
}

// --- Γραφήματα στατιστικών ---------------------------------------------------
// Ζωγραφίζονται με σκέτο SVG: καμία βιβλιοθήκη, κανένα CDN — η εφαρμογή
// υπολογιστή τρέχει χωρίς internet και ένα γράφημα που δεν φορτώνει είναι
// χειρότερο από κανένα. Τα χρώματα βγαίνουν από τις μεταβλητές του θέματος.
let STAT_DATA=[],STAT_CHART='table';
const CHART_COLORS=['#38bdf8','#22c55e','#f59e0b','#a78bfa','#f472b6','#14b8a6','#fb7185','#facc15','#60a5fa','#4ade80'];
document.querySelectorAll('#statChart button').forEach(b=>b.onclick=()=>{
  document.querySelectorAll('#statChart button').forEach(x=>x.classList.remove('on'));
  b.classList.add('on');STAT_CHART=b.dataset.c;renderStatChart();});
function renderStatChart(){
  const box=$('#statGraph'),table=$('#statTable');
  if(STAT_CHART==='table'){box.style.display='none';table.style.display='';return;}
  table.style.display='none';box.style.display='';
  const rows=STAT_DATA.filter(b=>Number(b.value)>0);
  if(!rows.length){box.innerHTML='<div class="muted">Δεν υπάρχουν δεδομένα για γράφημα.</div>';return;}
  box.innerHTML=STAT_CHART==='pie'?pieSvg(rows):barSvg(rows);
}
function statLabel(b){const n=invName(b.type);return (b.type||'')+(n?' · '+n:'');}
function chartLegend(rows,total){
  return '<div class="chart-legend">'+rows.map((b,i)=>
    `<span class="cl-item"><i style="background:${CHART_COLORS[i%CHART_COLORS.length]}"></i>${esc(statLabel(b))} — <b>${fmt(b.value)} €</b> <span class="muted">(${(b.value/total*100).toFixed(1)}%)</span></span>`).join('')+'</div>';
}
function barSvg(rows){
  const W=760,rowH=30,pad=8,H=rows.length*rowH+pad*2;
  const max=Math.max(...rows.map(b=>b.value));
  const labelW=210,barW=W-labelW-90;
  const total=rows.reduce((s,b)=>s+Number(b.value),0);
  const bars=rows.map((b,i)=>{
    const y=pad+i*rowH,w=Math.max(2,Math.round(b.value/max*barW));
    const name=statLabel(b);
    return `<text x="0" y="${y+15}" class="cx-lbl">${esc(name.length>32?name.slice(0,31)+'…':name)}</text>`+
      `<rect x="${labelW}" y="${y+3}" width="${w}" height="18" rx="4" fill="${CHART_COLORS[i%CHART_COLORS.length]}"><title>${esc(name)}: ${fmt(b.value)} € (${b.count} παραστατικά)</title></rect>`+
      `<text x="${labelW+w+8}" y="${y+16}" class="cx-val">${fmt(b.value)} €</text>`;
  }).join('');
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Τζίρος ανά τύπο παραστατικού">${bars}</svg>`+chartLegend(rows,total);
}
function pieSvg(rows){
  const total=rows.reduce((s,b)=>s+Number(b.value),0);
  const cx=150,cy=150,r=120;let angle=-Math.PI/2;
  const slices=rows.map((b,i)=>{
    const frac=b.value/total,end=angle+frac*Math.PI*2;
    const x1=cx+r*Math.cos(angle),y1=cy+r*Math.sin(angle);
    const x2=cx+r*Math.cos(end),  y2=cy+r*Math.sin(end);
    const large=frac>0.5?1:0;
    // Ένας μοναδικός τύπος δίνει πλήρη κύκλο: το τόξο εκφυλίζεται σε σημείο και
    // η πίτα βγαίνει ΚΕΝΗ — γι' αυτό ζωγραφίζεται κύκλος.
    const d=frac>=0.999
      ? `M ${cx} ${cy-r} A ${r} ${r} 0 1 1 ${cx-0.01} ${cy-r} Z`
      : `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
    angle=end;
    return `<path d="${d}" fill="${CHART_COLORS[i%CHART_COLORS.length]}" stroke="var(--panel)" stroke-width="1.5"><title>${esc(statLabel(b))}: ${fmt(b.value)} € (${(frac*100).toFixed(1)}%)</title></path>`;
  }).join('');
  return `<svg class="chart pie" viewBox="0 0 300 300" role="img" aria-label="Μερίδιο τζίρου ανά τύπο">${slices}</svg>`+chartLegend(rows,total);
}

// Invoice-type catalogue (verbal labels) — loaded once, used by stats/PDF/issue.
let INVTYPES=[],INVBYCODE={},INVBYVALUE={};
async function loadInvTypes(){if(INVTYPES.length)return INVTYPES;
  const apply=rows=>{INVTYPES=rows||[];INVBYCODE={};INVBYVALUE={};INVTYPES.forEach(t=>{if(t.code)INVBYCODE[t.code]=t;INVBYVALUE[String(t.value)]=t;});};
  try{const c=await api({cached:'invtypes'});if(c.rows&&c.rows.length)apply(c.rows);}catch(e){}    // instant from cache
  if(!INVTYPES.length){try{const d=await api({invoice_types:1});apply(d.invoice_types||[]);}catch(e){}} // fallback live
  return INVTYPES;}
function invName(code){const t=INVBYCODE[code];return t?t.name:'';}          // "Τιμολόγιο Παροχής Υπηρεσιών"
function invLabel(code){const t=INVBYCODE[code];return t?t.label:code;}      // "2.1 - Τιμολόγιο …"
function invLabelByValue(v){const t=INVBYVALUE[String(v)];return t?t.label:String(v);}

// Cache-first loader: render cached snapshot instantly, then sync in background.
async function cachedThenSync(kind,onRows){
  let shown=false;
  try{const c=await api({cached:kind});if(c.rows&&c.rows.length){onRows(c.rows,true);shown=true;}}catch(e){}
  try{const s=await api({sync:kind});onRows(s.rows||[],false);
    if(s.changed&&shown&&s.prev_count>0)toast('Ενημερώθηκε ('+kind+')','ok');
  }catch(e){if(!shown)toast(kind+': '+e.message,'err');}
}

// --- Excel-style per-column dropdown filters ---------------------------------
// A funnel on each header opens a popup with a search box + a checkbox list of
// the column's distinct values (+ «(Όλα)»). State is kept per table+column and
// re-applied after every re-render (non-invasive — only hides rows).
let GRID_FILTERS={}; // { tableId: { colIdx: Set(allowedValues) } }  (missing = no filter)
// Το ίδιο εικονίδιο με το `icons.py` της «Λήψης Παραστατικών» — ένα χωνί.
const FUNNEL_SVG='<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M1.5 2h13a.5.5 0 0 1 .4.8L10 9.2V14a.5.5 0 0 1-.75.43l-2.5-1.5A.5.5 0 0 1 6.5 12.5V9.2L1.1 2.8A.5.5 0 0 1 1.5 2z"/></svg>';
function gridState(id){return GRID_FILTERS[id]||(GRID_FILTERS[id]={});}
function attachColumnFilters(tableId){
  const table=$('#'+tableId);if(!table||!table.tHead||!table.tHead.rows.length)return;
  const hdr=table.tHead.rows[0];
  [...hdr.cells].forEach((th,idx)=>{
    if(th.dataset.lc===undefined)th.dataset.lc=idx;   // λογικός αριθμός στήλης
    if(th.querySelector('.filter-btn'))return;        // already has a funnel
    const logical=+th.dataset.lc;
    const label=(th.textContent||'').trim();
    if(!label||th.classList.contains('nofilter')||th.classList.contains('grid-check'))return;
    const b=document.createElement('span');b.className='filter-btn';b.innerHTML=FUNNEL_SVG;b.title='Φίλτρο στήλης';b.dataset.col=logical;
    th.style.paddingRight='30px';
    b.onclick=(e)=>{e.stopPropagation();openColFilter(tableId,logical,th,label);};
    th.appendChild(b);
    if(gridState(tableId)[logical])b.classList.add('active');
  });
  ensureColsButton(tableId);
  enhanceGrid(tableId);
}

// --- Το κουμπί «Στήλες», σε ΚΑΘΕ πίνακα --------------------------------------
// Ο επιλογέας στηλών (openColumnChooser) υπήρχε ήδη, αλλά το κουμπί του ήταν
// γραμμένο με το χέρι σε ΜΙΑ οθόνη — οπότε παντού αλλού η δυνατότητα ήταν
// αόρατη. Εδώ η μπάρα μπαίνει μόνη της πάνω από κάθε πίνακα που περνά από το
// attachColumnFilters(), άρα κάθε νέα οθόνη τη δικαιούται χωρίς να τη ζητήσει.
function ensureColsButton(tableId){
  const table=$('#'+tableId);if(!table||table.dataset.colsBtn)return;
  const hdr=table.tHead&&table.tHead.rows[0];if(!hdr)return;
  if(![...hdr.cells].some(th=>(th.textContent||'').trim()))return;   // πίνακας χωρίς επικεφαλίδες
  table.dataset.colsBtn='1';
  const bar=document.createElement('div');bar.className='grid-tools';
  const b=document.createElement('button');
  b.type='button';b.className='ghost sm cols-btn';b.textContent='⚙ Στήλες';
  b.title='Ποιες στήλες φαίνονται';
  b.onclick=e=>{e.stopPropagation();openColumnChooser(tableId,b);};
  bar.appendChild(b);table.parentNode.insertBefore(bar,table);
  markColsButton(tableId);
}
// Το κουμπί δείχνει ότι κάτι είναι κρυμμένο — αλλιώς μια στήλη που λείπει
// μοιάζει με σφάλμα και όχι με επιλογή.
function markColsButton(tableId){
  const table=$('#'+tableId);if(!table)return;
  const bar=table.previousElementSibling;
  if(!bar||!bar.classList||!bar.classList.contains('grid-tools'))return;
  const btn=bar.querySelector('.cols-btn');if(!btn)return;
  const n=(gridLayout(tableId).hidden||[]).length;
  btn.classList.toggle('active',n>0);
  btn.title=n?(n===1?'1 κρυμμένη στήλη':n+' κρυμμένες στήλες'):'Ποιες στήλες φαίνονται';
}
// Το κελί μιας ΛΟΓΙΚΗΣ στήλης — όχι το `cells[i]`, που αλλάζει μόλις ο χρήστης
// μετακινήσει στήλη. Κάθε κελί κρατά τον αρχικό του αριθμό στο `data-lc`.
function cellOf(tr,logical){
  const cells=tr.cells;
  for(let i=0;i<cells.length;i++){if(+cells[i].dataset.lc===logical)return cells[i];}
  return cells[logical];
}
function colDistinct(table,col){const set=new Set();
  [...table.tBodies[0].rows].forEach(tr=>{if(tr.cells.length===1)return;const v=(cellOf(tr,col)?.textContent||'').trim();if(v!=='')set.add(v);});
  return [...set].sort((a,b)=>a.localeCompare(b,'el'));}

// --- Πλάτη & σειρά στηλών, αποθηκευμένα ανά χρήστη ---------------------------
// Ό,τι κάνει και ο πίνακας της «Λήψης Παραστατικών»: τραβάς το όριο για πλάτος,
// σέρνεις την κεφαλίδα για σειρά. Η διάταξη ζει στον server (`ui_prefs_*`) και
// όχι στο localStorage, ώστε ο ίδιος χρήστης να τη βρίσκει και από άλλο
// μηχάνημα — ίδια συμπεριφορά σε web και σε εφαρμογή υπολογιστή.
let GRID_LAYOUT={};      // tableId -> {w:{logical:px}, order:[logical…]}
let UI_PREFS_READY=false;
async function loadGridLayouts(){
  try{const d=await apost({auth:'ui_prefs_get'});
    Object.entries(d.prefs||{}).forEach(([k,v])=>{
      if(!k.startsWith('cols.'))return;
      try{GRID_LAYOUT[k.slice(5)]=JSON.parse(v)||{};}catch(e){}
    });
  }catch(e){}
  UI_PREFS_READY=true;
  Object.keys(GRID_LAYOUT).forEach(applyGridLayout);
}
let GRID_SAVE_T={};
function saveGridLayout(tableId){
  // Ο server δεν έχει λόγο να δεχτεί μία κλήση ανά pixel του συρσίματος.
  clearTimeout(GRID_SAVE_T[tableId]);
  GRID_SAVE_T[tableId]=setTimeout(()=>{
    apost({auth:'ui_prefs_set',key:'cols.'+tableId,value:JSON.stringify(GRID_LAYOUT[tableId]||{})}).catch(()=>{});
  },600);
}
function gridLayout(tableId){return GRID_LAYOUT[tableId]||(GRID_LAYOUT[tableId]={w:{},order:null});}
// ⚠️ Η αποθηκευμένη διάταξη δείχνει σε ΑΡΙΘΜΟΥΣ στηλών. Μόλις μια αναβάθμιση
// προσθέσει ή αφαιρέσει στήλη, οι ίδιοι αριθμοί σημαίνουν άλλα πράγματα και ο
// πίνακας ανοίγει με ανακατεμένες στήλες — χωρίς ο χρήστης να καταλαβαίνει
// γιατί. Κρατάμε υπογραφή των επικεφαλίδων: αν αλλάξει, η διάταξη πετιέται.
function gridSignature(table){
  return [...table.tHead.rows[0].cells]
    .map(th=>{const c=th.cloneNode(true);
      c.querySelectorAll('.filter-btn,.col-grip').forEach(x=>x.remove());
      return (c.textContent||'').trim();}).join('|');
}
function gridCheckSignature(tableId,table){
  const L=gridLayout(tableId);
  const sig=gridSignature(table);
  if(L.sig===sig)return;
  if(L.sig!==undefined&&(L.order||Object.keys(L.w||{}).length||(L.hidden||[]).length)){
    GRID_LAYOUT[tableId]={w:{},order:null,hidden:[],sig};
    saveGridLayout(tableId);
    return;
  }
  L.sig=sig;
}
function gridOrder(tableId,count){
  const L=gridLayout(tableId);
  const out=(L.order||[]).map(Number).filter(i=>i>=0&&i<count);
  for(let i=0;i<count;i++)if(!out.includes(i))out.push(i);
  return out;
}
function orderRow(tr,order){
  if(tr.cells.length!==order.length)return;   // γραμμή-μήνυμα («Κανένα…»)
  const byLogical={};
  [...tr.cells].forEach((c,i)=>{if(c.dataset.lc===undefined)c.dataset.lc=i;byLogical[c.dataset.lc]=c;});
  // Το `appendChild` ΜΕΤΑΚΙΝΕΙ τον κόμβο — η εφαρμογή είναι ιδεατή, οπότε μπορεί
  // να ξανατρέξει σε κάθε νέο render χωρίς να «διπλο-αναδιατάξει».
  order.forEach(lc=>{const c=byLogical[lc];if(c)tr.appendChild(c);});
}
function applyGridLayout(tableId){
  const table=$('#'+tableId);if(!table||!table.tHead||!table.tHead.rows.length)return;
  gridCheckSignature(tableId,table);
  const hdr=table.tHead.rows[0];
  const order=gridOrder(tableId,hdr.cells.length);
  orderRow(hdr,order);
  if(table.tBodies[0])[...table.tBodies[0].rows].forEach(tr=>orderRow(tr,order));
  const L=gridLayout(tableId);
  const widths=L.w||{};
  // Σταθερή διάταξη ΜΟΝΟ όταν έχουμε πλάτος για κάθε στήλη· αλλιώς οι στήλες
  // χωρίς τιμή μοιράζονται ό,τι περισσέψει και τα κουμπιά ξεχειλίζουν.
  if(Object.keys(widths).length>=hdr.cells.length)table.style.tableLayout='fixed';
  else table.style.tableLayout='';
  [...hdr.cells].forEach(th=>{
    const px=widths[th.dataset.lc];
    if(px)th.style.width=px+'px';
  });
  applyHidden(tableId);
  markColsButton(tableId);
}
// --- Ποιες στήλες φαίνονται --------------------------------------------------
// Ζητήθηκε για το ΜΑΡΚ (χρήσιμο, αλλά πλατύ και σπάνια αναγνώσιμο), αλλά ο
// μηχανισμός δεν έχει λόγο να ξέρει για ποια στήλη μιλάμε: ισχύει για κάθε
// πίνακα και αποθηκεύεται μαζί με πλάτη και σειρά.
function hiddenSet(tableId){const L=gridLayout(tableId);return new Set((L.hidden||[]).map(Number));}
function applyHidden(tableId){
  const table=$('#'+tableId);if(!table||!table.tHead)return;
  const hide=hiddenSet(tableId);
  const paint=tr=>[...tr.cells].forEach(c=>{
    if(c.dataset.lc===undefined)return;
    c.style.display=hide.has(+c.dataset.lc)?'none':'';});
  paint(table.tHead.rows[0]);
  if(table.tBodies[0])[...table.tBodies[0].rows].forEach(tr=>{
    if(tr.cells.length>1)paint(tr);});
}
function setColumnHidden(tableId,logical,hidden){
  const L=gridLayout(tableId);const set=hiddenSet(tableId);
  hidden?set.add(logical):set.delete(logical);
  L.hidden=[...set];
  applyHidden(tableId);saveGridLayout(tableId);markColsButton(tableId);
}
function openColumnChooser(tableId,anchor){
  if(window.event&&window.event.stopPropagation)window.event.stopPropagation();
  const table=$('#'+tableId);if(!table||!table.tHead)return;
  const pop=$('#colFilterPop');const hide=hiddenSet(tableId);
  const cells=[...table.tHead.rows[0].cells];
  const items=cells.map(th=>{
    const lc=+th.dataset.lc;
    const label=(th.textContent||'').trim()||'(χωρίς τίτλο)';
    if(th.classList.contains('grid-check'))return '';
    return `<label class="cf-item"><input type="checkbox" data-lc="${lc}" ${hide.has(lc)?'':'checked'}> ${esc(label)}</label>`;
  }).join('');
  pop.innerHTML=`<h5>Στήλες</h5><div class="cf-list">${items}</div>
    <div class="cf-actions"><button class="ghost sm cf-clear">Όλες</button><button class="primary sm cf-close">Κλείσιμο</button></div>`;
  pop.querySelector('.cf-list').onchange=e=>{const cb=e.target;
    if(cb&&cb.type==='checkbox')setColumnHidden(tableId,+cb.dataset.lc,!cb.checked);};
  pop.querySelector('.cf-clear').onclick=()=>{gridLayout(tableId).hidden=[];applyHidden(tableId);saveGridLayout(tableId);
    markColsButton(tableId);pop.querySelectorAll('.cf-list input').forEach(cb=>cb.checked=true);};
  pop.querySelector('.cf-close').onclick=closeColFilter;
  const r=(anchor||table).getBoundingClientRect();
  pop.style.left=Math.max(8,Math.min(r.left-120,window.innerWidth-300))+'px';
  pop.style.top=(r.bottom+4)+'px';pop.classList.add('on');
}
// Κρατά το ΤΡΕΧΟΝ πλάτος κάθε στήλης, όπως το υπολόγισε ο browser από το
// περιεχόμενο. Καλείται τη στιγμή που ο πίνακας περνά σε σταθερή διάταξη.
// --- Ταξινόμηση με κλικ στην κεφαλίδα ----------------------------------------
// Μόνο οι Πελάτες είχαν ταξινόμηση, γραμμένη ειδικά γι' αυτούς. Είδη, Σειρές,
// Πρόχειρα, Ακύρωση, Προγραμματισμός και Στατιστικά δεν είχαν καθόλου. Εδώ
// γίνεται ιδιότητα ΤΟΥ ΠΙΝΑΚΑ, όπως το πλάτος και η σειρά στηλών: ό,τι περνά
// από το `enhanceGrid` την αποκτά.
let GRID_SORT={};   // tableId -> {lc, dir}
// Αριθμοί («1.234,56», «-12»), ημερομηνίες («31/12/2026») και κείμενο, με τη
// σειρά που τα αναγνωρίζουμε. Χωρίς αυτό το «100» ερχόταν πριν το «20».
function sortValue(text){
  const t=(text||'').trim();
  if(!t)return {n:null,s:''};
  const d=/^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(t);
  if(d)return {n:+(d[3]+d[2].padStart(2,'0')+d[1].padStart(2,'0')),s:t};
  const iso=/^(\d{4})-(\d{2})-(\d{2})/.exec(t);
  if(iso)return {n:+(iso[1]+iso[2]+iso[3]),s:t};
  // Καθαρός αριθμός (επιτρέπονται € και κενά), σε ελληνική ή αγγλική μορφή.
  if(/^[-+]?[\d.,\s]+(€|%)?$/.test(t)){
    const n=elNum(t.replace(/[€%\s]/g,''));
    if(!isNaN(n))return {n,s:t};
  }
  return {n:null,s:t};
}
function sortGrid(tableId,logical){
  const table=$('#'+tableId);if(!table||!table.tBodies[0])return;
  const cur=GRID_SORT[tableId];
  const dir=(cur&&cur.lc===logical)?-cur.dir:1;
  GRID_SORT[tableId]={lc:logical,dir};
  const body=table.tBodies[0];
  const rows=[...body.rows].filter(r=>r.cells.length>1);
  if(rows.length<2){markSortIndicator(tableId);return;}
  rows.sort((a,b)=>{
    const x=sortValue((cellOf(a,logical)||{}).textContent),
          y=sortValue((cellOf(b,logical)||{}).textContent);
    if(x.n!==null&&y.n!==null)return (x.n-y.n)*dir;
    if(x.s===''&&y.s!=='')return 1;      // τα κενά πάντα τελευταία
    if(y.s===''&&x.s!=='')return -1;
    return x.s.localeCompare(y.s,'el',{numeric:true})*dir;
  });
  rows.forEach(r=>body.appendChild(r));
  markSortIndicator(tableId);
}
function markSortIndicator(tableId){
  const table=$('#'+tableId);if(!table||!table.tHead)return;
  const st=GRID_SORT[tableId];
  [...table.tHead.rows[0].cells].forEach(th=>{
    let ind=th.querySelector('.grid-sort');
    if(!ind){ind=document.createElement('span');ind.className='grid-sort';th.appendChild(ind);}
    ind.textContent=(st&&+th.dataset.lc===st.lc)?(st.dir>0?' ▲':' ▼'):'';
  });
}
function freezeWidths(tableId,table){
  const L=gridLayout(tableId);L.w=L.w||{};
  [...table.tHead.rows[0].cells].forEach(th=>{
    if(L.w[th.dataset.lc])return;                 // ο χρήστης το έχει ήδη ορίσει
    const w=Math.round(th.getBoundingClientRect().width);
    if(w>0)L.w[th.dataset.lc]=w;
  });
}
function enhanceGrid(tableId){
  const table=$('#'+tableId);if(!table||!table.tHead||!table.tHead.rows.length)return;
  const hdr=table.tHead.rows[0];
  if(!table.dataset.gridReady){
    table.dataset.gridReady='1';
    // Κάθε νέο render γράφει το tbody από την αρχή, σε λογική σειρά — άρα η
    // διάταξη πρέπει να ξαναμπαίνει τότε, όχι μόνο μία φορά στην αρχή.
    if(table.tBodies[0]){
      new MutationObserver(()=>{
        const ord=gridOrder(tableId,hdr.cells.length);
        [...table.tBodies[0].rows].forEach(tr=>orderRow(tr,ord));
        applyHidden(tableId);
      }).observe(table.tBodies[0],{childList:true});
    }
  }
  [...hdr.cells].forEach(th=>{
    if(th.dataset.gridCol)return;
    th.dataset.gridCol='1';
    th.draggable=true;
    // Κλικ = ταξινόμηση. Εξαιρούνται όσες κεφαλίδες έχουν ήδη δικό τους
    // χειριστή (Πελάτες) και η στήλη με τα checkbox.
    if(!th.getAttribute('onclick')&&!th.classList.contains('grid-check')
       &&(th.textContent||'').trim()){
      th.classList.add('sortable-th');
      th.addEventListener('click',e=>{
        if(e.target.closest('.filter-btn,.col-grip,input,button'))return;
        sortGrid(tableId,+th.dataset.lc);});
    }
    th.addEventListener('dragstart',e=>{GRID_DRAG={tableId,lc:+th.dataset.lc};
      try{e.dataTransfer.setData('text/plain',th.dataset.lc);e.dataTransfer.effectAllowed='move';}catch(_){}});
    th.addEventListener('dragover',e=>{if(GRID_DRAG&&GRID_DRAG.tableId===tableId){e.preventDefault();th.classList.add('col-drop');}});
    th.addEventListener('dragleave',()=>th.classList.remove('col-drop'));
    th.addEventListener('drop',e=>{e.preventDefault();th.classList.remove('col-drop');
      if(!GRID_DRAG||GRID_DRAG.tableId!==tableId)return;
      const order=gridOrder(tableId,hdr.cells.length);
      const from=order.indexOf(GRID_DRAG.lc),to=order.indexOf(+th.dataset.lc);
      if(from<0||to<0||from===to)return;
      order.splice(to,0,order.splice(from,1)[0]);
      gridLayout(tableId).order=order;applyGridLayout(tableId);saveGridLayout(tableId);
      GRID_DRAG=null;});
    const grip=document.createElement('span');grip.className='col-grip';
    grip.addEventListener('mousedown',e=>{e.preventDefault();e.stopPropagation();
      const startX=e.clientX,startW=th.getBoundingClientRect().width;
      // ⚠️ «Πάγωμα» ΟΛΩΝ των στηλών πριν το `table-layout:fixed`. Αλλιώς το
      // fixed μοιράζει το πλάτος εξίσου και η στήλη με τα κουμπιά — που
      // χρειάζεται όσο ακριβώς πιάνουν — στένευε, με τα κουμπιά να ΚΑΒΑΛΑΝΕ τη
      // διπλανή. Κρατώντας το φυσικό πλάτος κάθε στήλης, μόνο αυτή που σέρνει
      // ο χρήστης αλλάζει.
      freezeWidths(tableId,table);
      table.style.tableLayout='fixed';
      const move=ev=>{const w=Math.max(48,Math.round(startW+ev.clientX-startX));
        th.style.width=w+'px';gridLayout(tableId).w[th.dataset.lc]=w;};
      const up=()=>{document.removeEventListener('mousemove',move);document.removeEventListener('mouseup',up);
        saveGridLayout(tableId);};
      document.addEventListener('mousemove',move);document.addEventListener('mouseup',up);});
    // Το σύρσιμο του ορίου δεν πρέπει να ξεκινά μετακίνηση στήλης.
    grip.addEventListener('dragstart',e=>{e.preventDefault();e.stopPropagation();});
    th.appendChild(grip);
  });
  if(UI_PREFS_READY)applyGridLayout(tableId);
}
let GRID_DRAG=null;
function openColFilter(tableId,col,th,label){
  const table=$('#'+tableId),pop=$('#colFilterPop');
  const values=colDistinct(table,col);const st=gridState(tableId);
  const isAllowed=v=>!st[col]||st[col].has(v);
  pop.innerHTML=`<h5>Φίλτρο: ${esc(label)}</h5>
    <input class="cf-search" placeholder="Αναζήτηση τιμής…" autocomplete="off">
    <div class="cf-list"></div>
    <div class="cf-actions"><button class="ghost sm cf-clear">Καθαρισμός</button>
      <button class="ghost sm cf-hide" title="Κρύβει τη στήλη· επαναφορά από το «⚙ Στήλες»">🚫 Απόκρυψη</button>
      <button class="primary sm cf-close">Κλείσιμο</button></div>`;
  const listEl=pop.querySelector('.cf-list');
  pop.querySelector('.cf-hide').onclick=()=>{setColumnHidden(tableId,col,true);closeColFilter();};
  function render(term){term=(term||'').toLowerCase();
    const shown=values.filter(v=>!term||v.toLowerCase().includes(term));
    listEl.innerHTML=`<label class="cf-item" data-all="1"><input type="checkbox" ${!st[col]?'checked':''}> <b>(Όλα)</b></label>`+
      shown.map(v=>`<label class="cf-item"><input type="checkbox" data-v="${esc(v)}" ${isAllowed(v)?'checked':''}> ${esc(v)}</label>`).join('')
      ||'<div class="muted" style="padding:6px">—</div>';
  }
  render('');
  pop.querySelector('.cf-search').oninput=function(){render(this.value);};
  listEl.onchange=function(e){const cb=e.target;if(!cb||cb.type!=='checkbox')return;
    if(cb.parentElement.dataset.all){
      if(cb.checked)delete st[col]; else st[col]=new Set();      // all vs none
    }else{
      if(!st[col])st[col]=new Set(values);                       // start from "all"
      if(cb.checked)st[col].add(cb.dataset.v);else st[col].delete(cb.dataset.v);
      if(st[col].size===values.length)delete st[col];            // all selected → no filter
    }
    applyColumnFilters(tableId);
    const btn=th.querySelector('.filter-btn');if(btn)btn.classList.toggle('active',!!st[col]);
    render(pop.querySelector('.cf-search').value);
  };
  pop.querySelector('.cf-clear').onclick=()=>{delete st[col];applyColumnFilters(tableId);
    const btn=th.querySelector('.filter-btn');if(btn)btn.classList.remove('active');render(pop.querySelector('.cf-search').value);};
  pop.querySelector('.cf-close').onclick=closeColFilter;
  const r=th.getBoundingClientRect();
  pop.style.left=Math.max(8,Math.min(r.left,window.innerWidth-300))+'px';
  pop.style.top=(r.bottom+4)+'px';pop.classList.add('on');
  setTimeout(()=>pop.querySelector('.cf-search').focus(),30);
}
function closeColFilter(){$('#colFilterPop').classList.remove('on');}
document.addEventListener('click',e=>{const pop=$('#colFilterPop');
  if(pop&&pop.classList.contains('on')&&!e.target.closest('#colFilterPop')
     &&!e.target.closest('.filter-btn')&&!e.target.closest('.cols-btn'))closeColFilter();});
function applyColumnFilters(tableId){
  const table=$('#'+tableId);if(!table||!table.tBodies.length)return;const st=gridState(tableId);
  [...table.tBodies[0].rows].forEach(tr=>{
    if(tr.cells.length===1){tr.style.display='';return;} // placeholder ("Κανένα…") row
    let show=true;
    for(const col in st){const allowed=st[col];if(!allowed)continue;const v=(cellOf(tr,+col)?.textContent||'').trim();if(!allowed.has(v)){show=false;break;}}
    tr.style.display=show?'':'none';});
  // keep funnel active-state in sync after re-renders
  const hdr=table.tHead&&table.tHead.rows[0];
  if(hdr)[...hdr.querySelectorAll('.filter-btn')].forEach(b=>b.classList.toggle('active',!!st[b.dataset.col]));
}

// Customers (cached + instant client-side filter)
let ALL_CUSTOMERS=[];
$('#custSearch').addEventListener('input',renderCustomers);
function custFields(c){return {vat:c.vat||c.customer_vat||'',name:c.name||c.customer_name||'',code:c.code||c.customer_code||'',city:c.city||'',address:c.address||'',zip:c.zip||'',
  // «Ημεδαπή επιχείρηση» / «Ιδιώτης» — το γράφει η ΙΔΙΑ η ΑΑΔΕ στη λίστα πελατών.
  type:c.type||'', job:c.job_description||c.job||''};}
let CUST_SORT={key:'name',dir:1};
function sortCustomers(key){
  if(CUST_SORT.key===key)CUST_SORT.dir*=-1;else{CUST_SORT.key=key;CUST_SORT.dir=1;}
  renderCustomers();
}
function renderCustomers(){
  const term=($('#custSearch').value||'').toLowerCase().trim();
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.code+' '+c.city).toLowerCase().includes(term));
  // sort by the active column (numeric for code/vat, locale-aware for text)
  const k=CUST_SORT.key,dir=CUST_SORT.dir;
  rows.sort((a,b)=>{let x=a[k]||'',y=b[k]||'';
    if(k==='code'||k==='vat'){const nx=parseFloat(x)||0,ny=parseFloat(y)||0;if(nx!==ny)return(nx-ny)*dir;}
    return String(x).localeCompare(String(y),'el')*dir;});
  // header sort indicators — update a dedicated span so the ▾ funnel button
  // (added by attachColumnFilters) is never clobbered by textContent writes.
  ['code','vat','name','city'].forEach(c=>{const si=document.getElementById('si-'+c);if(si)si.textContent=(CUST_SORT.key===c?(CUST_SORT.dir>0?' ▲':' ▼'):'');});
  $('#custCount').textContent=rows.length+' / '+ALL_CUSTOMERS.length+' πελάτες';
  $('#custTable tbody').innerHTML=rows.slice(0,500).map(c=>
    `<tr class="clickable" onclick="openCard('${q1(c.vat)}','${q1(c.name)}')"><td>${esc(c.code)}</td><td>${esc(c.vat)}</td><td>${esc(c.name)}</td><td>${esc(c.city)}</td>
      <td class="right"><button class="primary sm" title="Έκδοση παραστατικού" onclick="event.stopPropagation();issueFor('${q1(c.vat)}','${q1(c.name)}')">🧾 Έκδοση</button>
      <button class="ghost sm" title="Επεξεργασία πελάτη" onclick="event.stopPropagation();editCustomer('${q1(c.vat)}')">✎</button>
      <button class="ghost sm" onclick="event.stopPropagation();openCard('${q1(c.vat)}','${q1(c.name)}')">Καρτέλα →</button></td></tr>`).join('')||'<tr><td colspan="5" class="muted">Κανένα αποτέλεσμα.</td></tr>';
  applyColumnFilters('custTable');
}
async function loadCustomers(){await cachedThenSync('customers',rows=>{ALL_CUSTOMERS=rows;renderCustomers();});}

// Customer modal (create/edit)
let CUST_ONSAVED=null;
function custTab(t){$('#custTabAfm').style.display=t==='afm'?'':'none';$('#custTabPersonal').style.display=t==='personal'?'':'none';document.querySelectorAll('#custTabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));}
function openCustomerModal(onSaved,prefillAfm){CUST_ONSAVED=(typeof onSaved==='function')?onSaved:null;$('#custModalTitle').textContent='Νέος πελάτης';['cmAfm','cmName','cmAddress','cmCity','cmZip','cmEmail','cmPhone1','cmPhone2','cpName','cpAddress','cpCity','cpZip','cpEmail','cpPhone'].forEach(id=>$('#'+id).value='');$('#cpJob').value='ΙΔΙΩΤΗΣ';custTab('afm');if(prefillAfm)$('#cmAfm').value=prefillAfm;$('#custModal').showModal();}
// Επεξεργασία = δική της φόρμα, με ό,τι κρατά η ΑΑΔΕ για τον πελάτη.
let CE_VAT='';
function editCustomer(vat){
  const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===String(vat))||{vat:String(vat)};
  const raw=ALL_CUSTOMERS.find(x=>(x.vat||x.customer_vat)===String(vat))||{};
  CE_VAT=c.vat;
  $('#ceVatLbl').textContent=c.vat||'—';
  $('#ceCode').value=c.code||'';$('#ceName').value=c.name||'';
  $('#ceAddress').value=c.address||'';$('#ceCity').value=c.city||'';$('#ceZip').value=c.zip||'';
  $('#ceJob').value=c.job||'';$('#ceDoy').value=raw.doy||raw.doy_description||'';
  $('#ceEmail').value=raw.email||'';$('#cePhone1').value=raw.phone1||raw.phone||'';$('#cePhone2').value=raw.phone2||'';
  $('#ceResult').textContent='';
  $('#custEditModal').showModal();
}
function ceOpenCard(){custEditModal.close();openCard(CE_VAT,$('#ceName').value);}
async function ceLookup(){if(!/^\d{9}$/.test(CE_VAT)){toast('Ο πελάτης δεν έχει ΑΦΜ','err');return;}
  try{const d=await api({afm:CE_VAT});const c=d.customer||d.info||d;
    if(c.name||c.customer_name)$('#ceName').value=c.name||c.customer_name;
    if(c.address)$('#ceAddress').value=c.address;
    if(c.city)$('#ceCity').value=c.city;
    if(c.zip)$('#ceZip').value=c.zip;
    if(c.doy)$('#ceDoy').value=c.doy;
    toast('Στοιχεία αντλήθηκαν','ok');
  }catch(e){toast('Taxisnet: '+e.message,'err');}}
async function saveCustomerEdit(){
  if(!$('#ceName').value.trim()){$('#ceResult').textContent='Η επωνυμία είναι υποχρεωτική.';return;}
  $('#ceResult').textContent='Αποθήκευση…';
  try{const d=await api({update_customer:1,update_customer_vat:CE_VAT,
      update_customer_code:$('#ceCode').value,update_name:$('#ceName').value,
      update_address:$('#ceAddress').value,update_city:$('#ceCity').value,update_zip:$('#ceZip').value,
      update_doy:$('#ceDoy').value,update_email:$('#ceEmail').value,
      update_phone1:$('#cePhone1').value,update_phone2:$('#cePhone2').value,
      update_job_description:$('#ceJob').value});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    custEditModal.close();toast('Ο πελάτης ενημερώθηκε','ok');loadCustomers(true);
  }catch(e){$('#ceResult').textContent='Πελάτης: '+e.message;}}
async function cmLookup(){const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}
  try{const d=await api({afm});const c=d.customer||d.info||d;$('#cmName').value=c.name||c.customer_name||'';$('#cmAddress').value=c.address||'';$('#cmCity').value=c.city||'';$('#cmZip').value=c.zip||'';toast('Στοιχεία αντλήθηκαν','ok');}catch(e){toast('Taxisnet: '+e.message,'err');}}
async function saveCustomer(){
  try{let d,saved=null;
    // Η επεξεργασία έχει δική της φόρμα (`custEditModal`) — εδώ μόνο νέοι πελάτες.
    if($('#custTabPersonal').style.display!=='none'){
      if(!$('#cpName').value||!$('#cpCity').value||!$('#cpZip').value){toast('Συμπλήρωσε όνομα/πόλη/ΤΚ','err');return;}
      d=await api({create_personal_customer:1,cust_name:$('#cpName').value,cust_address:$('#cpAddress').value,cust_city:$('#cpCity').value,cust_zip:$('#cpZip').value,cust_job_description:$('#cpJob').value,cust_email:$('#cpEmail').value,cust_phone1:$('#cpPhone').value});
      saved={vat:'',name:$('#cpName').value,address:$('#cpAddress').value,city:$('#cpCity').value,zip:$('#cpZip').value};
    }else{const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}d=await api({afm});
      const c=(d&&(d.info||d.customer))||{};saved={vat:afm,name:c.name||$('#cmName').value||'',address:c.address||'',city:c.city||'',zip:c.zip||''};
      // Το `?afm` δημιουργεί τον πελάτη από το Taxisnet αλλά ΔΕΝ ξέρει email ή
      // τηλέφωνο. Αν τα συμπλήρωσε ο χρήστης, τα γράφουμε αμέσως μετά —
      // αλλιώς θα έπρεπε να ανοίξει ξανά την καρτέλα για να τα βάλει.
      const extra={email:$('#cmEmail').value.trim(),p1:$('#cmPhone1').value.trim(),p2:$('#cmPhone2').value.trim()};
      if(extra.email||extra.p1||extra.p2){
        try{await api({update_customer:1,update_customer_vat:afm,update_name:saved.name,
          update_email:extra.email,update_phone1:extra.p1,update_phone2:extra.p2});}catch(e){}
        saved.email=extra.email;
      }}
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    $('#custModal').close();toast('Αποθηκεύτηκε','ok');loadCustomers(true);
    if(CUST_ONSAVED){const cb=CUST_ONSAVED;CUST_ONSAVED=null;cb(saved);}
  }catch(e){toast('Πελάτης: '+e.message,'err');}
}

// Customer card
// Dates are shown to the user as dd/mm/yyyy (text inputs) but stored & sent to the
// API as ISO yyyy-mm-dd. isoToDmy=display, di=read-as-ISO, dset=write, dtMask=typing.
function isoToDmy(v){if(!v)return'';const m=/^(\d{4})-(\d{1,2})-(\d{1,2})/.exec(v);return m?String(m[3]).padStart(2,'0')+'/'+String(m[2]).padStart(2,'0')+'/'+m[1]:v;}
function di(id){const el=$('#'+id);const v=((el&&el.value)||'').trim();if(/^\d{4}-\d{2}-\d{2}/.test(v))return v.slice(0,10);const m=/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(v);return m?m[3]+'-'+String(m[2]).padStart(2,'0')+'-'+String(m[1]).padStart(2,'0'):'';}
function dset(id,iso){const el=$('#'+id);if(el)el.value=isoToDmy(iso);}
function dtMask(el){let v=el.value.replace(/[^\d]/g,'').slice(0,8);if(v.length>4)v=v.slice(0,2)+'/'+v.slice(2,4)+'/'+v.slice(4);else if(v.length>2)v=v.slice(0,2)+'/'+v.slice(2);el.value=v;}
function defaultRange(){const y=new Date().getFullYear();if(!$('#cardFrom').value)dset('cardFrom',y+'-01-01');if(!$('#cardTo').value)dset('cardTo',y+'-12-31');}
function openCard(vat,name){showView('card');$('#cardVat').value=vat;$('#cardCust').value=name||vat;defaultRange();loadCard();}
// Customer selector on the Καρτέλα tab (search by name/ΑΦΜ)
function cardAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=$('#cardAcPanel');
  if(!ALL_CUSTOMERS.length)loadCustomers();
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  if(!rows.length){panel.classList.remove('open');return;}
  panel.innerHTML=rows.map(c=>`<div class="ac-row" onmousedown="pickCardCust('${q1(c.vat)}','${q1(c.name)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function pickCardCust(vat,name){$('#cardVat').value=vat;$('#cardCust').value=name||vat;$('#cardAcPanel').classList.remove('open');loadCard();}
document.addEventListener('click',e=>{const p=$('#cardAcPanel');if(p&&!e.target.closest('#cardAcPanel')&&e.target!==$('#cardCust'))p.classList.remove('open');});

// ---- BANK IMPORT (extrait → local payments) --------------------------------
let BI_TX=[]; // parsed transactions (with .customer selection attached)
// POST helper that carries the active account (needed to resolve COMPANY_VAT)
async function apostAcc(params){const b=new URLSearchParams(params);if(ACCOUNT)b.set('account',ACCOUNT);
  let r;
  try{r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body:b});}
  catch(e){if(netIsFetchFailure(e))netSetOffline(true,'Ο υπολογιστής δεν έχει σύνδεση στο internet.');throw e;}
  const t=await r.text();
  let d;try{d=JSON.parse(t);}catch(e){throw new Error(t.slice(0,200));}
  netNoteReply(d);
  return d;}
function biStrip(s){return (s||'').toString().toUpperCase()
  .replace(/[ΆΑ]/g,'Α').replace(/[ΈΕ]/g,'Ε').replace(/[ΉΗ]/g,'Η').replace(/[ΊΪΙ]/g,'Ι')
  .replace(/[ΌΟ]/g,'Ο').replace(/[ΎΫΥ]/g,'Υ').replace(/[ΏΩ]/g,'Ω').replace(/[^Α-ΩA-Z0-9 ]/g,' ').replace(/\s+/g,' ').trim();}
// Guess the best customer for a transaction from its ΑΦΜ or description text
function biGuess(tx){const custs=ALL_CUSTOMERS.map(custFields);
  if(tx.guess_vat){const byVat=custs.find(c=>c.vat===tx.guess_vat);if(byVat)return byVat;}
  const desc=biStrip(tx.description);if(!desc)return null;
  let best=null,bestScore=0;
  for(const c of custs){const nm=biStrip(c.name);if(!nm||nm.length<4)continue;
    // full-name substring, else count matching name-words (≥4 chars) found in desc
    let score=0;if(desc.includes(nm))score=100+nm.length;
    else{const w=nm.split(' ').filter(x=>x.length>=4);let hit=0;for(const x of w)if(desc.includes(x))hit++;
      if(w.length&&hit>=Math.max(1,Math.ceil(w.length/2)))score=hit*10;}
    if(score>bestScore){bestScore=score;best=c;}}
  return bestScore>=10?best:null;}
async function biPreview(){const f=$('#biFile').files[0];if(!f){toast('Επίλεξε αρχείο','err');return;}
  if(!ALL_CUSTOMERS.length)await loadCustomers();
  $('#biInfo').innerHTML='<span class="spin"></span> Ανάλυση αρχείου…';
  try{const b64=await new Promise((res,rej)=>{const rd=new FileReader();
      rd.onload=()=>res(rd.result.split(',')[1]);rd.onerror=rej;rd.readAsDataURL(f);});
    const d=await apostAcc({bank_preview:1,filename:f.name,bank:$('#biBank').value,file_b64:b64});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    BI_TX=(d.transactions||[]).map(tx=>{const g=biGuess(tx);return{...tx,
      cust:g?{vat:g.vat,name:g.name,code:g.code}:null,
      include:tx.direction==='credit',
      pay_date:tx.date||new Date().toISOString().slice(0,10)};});
    const cr=BI_TX.filter(t=>t.direction==='credit').length,matched=BI_TX.filter(t=>t.cust).length;
    $('#biInfo').innerHTML=`Βρέθηκαν <b>${BI_TX.length}</b> κινήσεις · <b>${cr}</b> εισπράξεις · αυτόματη αντιστοίχιση: <b>${matched}</b>${d.bank?' · τράπεζα: '+esc(d.bank):''}`;
    $('#biBar').style.display='flex';biRender();
  }catch(e){$('#biInfo').textContent='Σφάλμα: '+e.message;toast('Ανάλυση: '+e.message,'err');}}
function biRender(){const onlyCr=$('#biOnlyCredit').checked;
  const rows=BI_TX.map((t,i)=>({t,i})).filter(o=>!onlyCr||o.t.direction==='credit');
  $('#biTable tbody').innerHTML=rows.map(({t,i})=>{
    const dir=t.direction==='credit'?'<span class="pill ok">Είσπραξη</span>':'<span class="pill">Πληρωμή</span>';
    const amtCls=t.amount<0?'style="color:#f87171"':'style="color:#86efac"';
    const cval=t.cust?esc(t.cust.name||t.cust.vat):'';
    return `<tr>
      <td><input type="checkbox" ${t.include?'checked':''} onchange="BI_TX[${i}].include=this.checked;biSelInfo()"></td>
      <td>${esc(t.date)}</td>
      <td title="${esc(t.description)}">${esc((t.description||'').slice(0,60))}</td>
      <td class="num" ${amtCls}>${fmt(Math.abs(t.amount))}</td>
      <td>${dir}</td>
      <td style="position:relative"><input class="biCust" value="${cval}" placeholder="Αναζήτηση πελάτη…" autocomplete="off"
           oninput="biAc(this,${i})" onfocus="biAc(this,${i})"><div class="ac-panel" id="biAc${i}"></div></td>
    </tr>`;}).join('')||'<tr><td colspan="6" class="muted">Καμία κίνηση.</td></tr>';
  biSelInfo();}
function biAc(inp,i){const term=biStrip(inp.value);const panel=$('#biAc'+i);
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>biStrip(c.vat+' '+c.name+' '+c.city).includes(term));
  rows=rows.slice(0,20);
  if(!rows.length){panel.classList.remove('open');return;}
  panel.innerHTML=rows.map(c=>`<div class="ac-row" onmousedown="biPick(${i},'${q1(c.vat)}','${q1(c.name)}','${q1(c.code)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function biPick(i,vat,name,code){BI_TX[i].cust={vat,name,code};BI_TX[i].include=true;$('#biAc'+i).classList.remove('open');biRender();}
document.addEventListener('click',e=>{if(e.target.closest&&!e.target.closest('#biTable td'))document.querySelectorAll('#biTable .ac-panel.open').forEach(p=>p.classList.remove('open'));});
function biToggleAll(on){const onlyCr=$('#biOnlyCredit').checked;
  BI_TX.forEach(t=>{if(!onlyCr||t.direction==='credit')t.include=!!on;});$('#biAll').checked=!!on;biRender();}
function biSelInfo(){const sel=BI_TX.filter(t=>t.include);const withCust=sel.filter(t=>t.cust).length;
  const sum=sel.reduce((a,t)=>a+Math.abs(t.amount),0);
  $('#biSel').innerHTML=`Επιλεγμένες: <b>${sel.length}</b> (με πελάτη: ${withCust}) · σύνολο <b>${fmt(sum)} €</b>`;}
async function biImport(){const sel=BI_TX.filter(t=>t.include);
  if(!sel.length){toast('Δεν επέλεξες κινήσεις','err');return;}
  const noCust=sel.filter(t=>!t.cust);
  if(noCust.length&&!confirm(`${noCust.length} κινήσεις δεν έχουν πελάτη και θα καταχωρηθούν χωρίς αντιστοίχιση. Συνέχεια;`))return;
  const items=sel.map(t=>({customer_vat:t.cust?t.cust.vat:'',customer_name:t.cust?t.cust.name:'',customer_code:t.cust?t.cust.code:'',
    amount:Math.abs(t.amount),pay_date:t.pay_date||t.date,method:1,
    notes:(t.direction==='debit'?'[ΠΛΗΡΩΜΗ] ':'')+(t.description||'').slice(0,180)}));
  $('#biInfo').innerHTML='<span class="spin"></span> Καταχώρηση…';
  try{const d=await apostAcc({bank_import:1,items:JSON.stringify(items)});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    toast(`Καταχωρήθηκαν ${d.ok}/${d.total} πληρωμές`,'ok');
    $('#biInfo').innerHTML=`✅ Καταχωρήθηκαν <b>${d.ok}</b>${d.failed?` · αποτυχίες: ${d.failed}`:''}. Δες τις στην <b>Καρτέλα</b> κάθε πελάτη.`;
    BI_TX=BI_TX.filter(t=>!t.include);biRender();if(!BI_TX.length)$('#biBar').style.display='none';
  }catch(e){toast('Καταχώρηση: '+e.message,'err');$('#biInfo').textContent='Σφάλμα: '+e.message;}}

let CARD={};
async function loadCard(){const vat=$('#cardVat').value.trim();if(!vat){toast('Επίλεξε πελάτη','err');return;}defaultRange();
  $('#cardCards').innerHTML='<div class="card"><div class="v"><span class="spin"></span></div></div>';$('#cardTable tbody').innerHTML='';
  try{const d=await api({ledger:1,buyer_vat:vat,issue_date_from:di('cardFrom'),issue_date_to:di('cardTo')});if(!d.success)throw new Error(d.error||'σφάλμα');CARD=d;
    // Τα παραστατικά της καρτέλας, για μαζική εκτύπωση/ZIP.
    window.CARD_INVOICES=(d.entries||[]).filter(e=>e.kind==='invoice'&&e.mark)
      .map(e=>({mark:e.mark,issue_date:e.date,series:e.series||'',aa:e.aa||''}));
    const balCls=d.balance>0.005?'pos':'zero';
    $('#cardHead').innerHTML=`<strong>${esc(d.customer_name||vat)}</strong> <span class="muted">ΑΦΜ ${esc(vat)}</span>`;
    $('#cardCards').innerHTML=`<div class="card"><div class="k">Τζίρος</div><div class="v">${fmt(d.total_invoiced)} €</div></div>`+
      `<div class="card"><div class="k">Πληρωμές</div><div class="v" style="color:#86efac">${fmt(d.total_paid)} €</div></div>`+
      `<div class="card"><div class="k">Υπόλοιπο</div><div class="v balance ${balCls}">${fmt(d.balance)} €</div></div>`;
    $('#cardTable tbody').innerHTML=d.entries.map(e=>{
      if(e.kind==='invoice')return `<tr><td>${esc(e.date)}</td><td><span class="pill" title="${esc(invName(e.type))}">${esc(e.type||'')}</span> ${esc(invName(e.type))}</td><td>ΜΑΡΚ ${esc(e.mark)}</td><td class="num">${fmt(e.debit)}</td><td class="num"></td><td class="num">${fmt(e.balance)}</td>
        <td class="right">${e.mark?`${docBtn(e.mark)} <button class="danger sm" title="Ακύρωση με πιστωτικό" onclick="cancelFromCard('${q1(e.mark)}')">↩ Ακύρωση</button>`:''}</td></tr>`;
      // Διπλό κλικ = επεξεργασία, όπως στην εφαρμογή υπολογιστή. Μέχρι τώρα ο
      // μόνος δρόμος για μια λάθος πληρωμή ήταν διαγραφή και ξαναγράψιμο.
      return `<tr class="clickable" title="Διπλό κλικ για επεξεργασία" ondblclick="editPayment(${e.payment_id})"><td>${esc(e.date)}</td><td><span class="pill ok">Πληρωμή</span> ${esc(payMethod(e.method))}</td><td>${esc(e.notes||'')}</td><td class="num"></td><td class="num">${fmt(e.credit)}</td><td class="num">${fmt(e.balance)}</td><td class="right"><button class="ghost sm" title="Επεξεργασία" onclick="event.stopPropagation();editPayment(${e.payment_id})">✎</button><button class="danger sm" onclick="event.stopPropagation();delPayment(${e.payment_id})">✕</button></td></tr>`;
    }).join('')||'<tr><td colspan="7" class="muted">Καμία κίνηση.</td></tr>';
  }catch(e){$('#cardCards').innerHTML='';toast('Καρτέλα: '+e.message,'err');}
}
async function cancelFromCard(mark){showView('cancel');$('#cxVat').value=CARD.customer_vat||'';$('#cxCust').value=CARD.customer_name||CARD.customer_vat||'';
  await cxLoadInvoices();const idx=CX_INV.findIndex(i=>String(i.mark)===String(mark));if(idx>=0)cxPick(idx);toast('Επιλέχθηκε για πίστωση/ακύρωση','ok');}

// Payments
// Δύο δρόμοι για την ίδια φόρμα: από την Καρτέλα (ο πελάτης είναι δεδομένος) και
// μεμονωμένα από την Εισαγωγή πληρωμών (τον διαλέγεις). Το `PM_MODE` κρατά ποιος
// από τους δύο, ώστε η αποθήκευση να ξέρει τι να ανανεώσει.
let PM_MODE='card', PM_NAME='', PM_EDIT=null;
function pmReset(){['pmAmount','pmNotes'].forEach(i=>$('#'+i).value='');$('#pmResult').textContent='';
  PM_EDIT=null;$('#pmHead').textContent='💶 Καταχώρηση πληρωμής';
  dset('pmDate',new Date().toISOString().slice(0,10));pmCardBtn();}
// Επεξεργασία υπάρχουσας πληρωμής — ίδια φόρμα, άλλη κατάληξη.
function editPayment(id){
  const e=(CARD.entries||[]).find(x=>x.payment_id===id);
  if(!e){toast('Η πληρωμή δεν βρέθηκε','err');return;}
  PM_MODE='card';PM_NAME=CARD.customer_name||'';
  $('#pmPickRow').style.display='none';$('#pmRepeatWrap').style.display='none';$('#pmRepeat').checked=false;
  pmReset();
  PM_EDIT=id;$('#pmHead').textContent='✎ Επεξεργασία πληρωμής';
  $('#pmVat').value=$('#cardVat').value.trim();
  $('#pmAmount').value=(Number(e.credit)||0).toFixed(2);
  $('#pmMethod').value=String(e.method||3);
  $('#pmNotes').value=e.notes||'';
  dset('pmDate',e.date_iso||e.date||'');
  $('#payModal').showModal();
}
// Το κουμπί «καρτέλα» εμφανίζεται μόλις υπάρχει πελάτης: στη μεμονωμένη
// καταχώρηση ο χρήστης θέλει να δει το υπόλοιπο ΠΡΙΝ γράψει ποσό, χωρίς να
// χάσει τη φόρμα.
function pmCardBtn(){
  const btn=$('#pmCardBtn');if(!btn)return;
  const vat=($('#pmVat').value||'').trim();
  btn.style.display=(PM_MODE==='manual'&&vat)?'':'none';
}
function openPaymentModal(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  PM_MODE='card';PM_NAME=CARD.customer_name||'';
  $('#pmPickRow').style.display='none';$('#pmRepeatWrap').style.display='none';$('#pmRepeat').checked=false;
  pmReset();$('#pmVat').value=vat;$('#pmAmount').value=CARD.balance>0?CARD.balance.toFixed(2):'';
  $('#payModal').showModal();}
// Μεμονωμένη καταχώρηση, χωρίς να χρειάζεται πρώτα καρτέλα.
function openManualPayment(){
  PM_MODE='manual';
  if(!ALL_CUSTOMERS.length)loadCustomers();
  $('#pmPickRow').style.display='';$('#pmRepeatWrap').style.display='';
  // Ο πελάτης ΔΕΝ καθαρίζεται όταν είναι ήδη επιλεγμένος: αυτό ακριβώς κρατά η
  // «επαναλαμβανόμενη εισαγωγή» ανάμεσα σε δύο πληρωμές.
  if(!$('#pmRepeat').checked){$('#pmCust').value='';$('#pmVat').value='';PM_NAME='';}
  pmReset();$('#payModal').showModal();
  setTimeout(()=>$((!$('#pmVat').value)?'#pmCust':'#pmAmount').focus(),40);}
function pmAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=$('#pmAcPanel');
  if(!ALL_CUSTOMERS.length)loadCustomers();
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  if(!rows.length){panel.classList.remove('open');return;}
  panel.innerHTML=rows.map(c=>`<div class="ac-row" onmousedown="pmPick('${q1(c.vat)}','${q1(c.name)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function pmPick(vat,name){$('#pmVat').value=vat;$('#pmCust').value=name||vat;PM_NAME=name||'';
  $('#pmAcPanel').classList.remove('open');pmCardBtn();$('#pmAmount').focus();}
// Η τρέχουσα καρτέλα του επιλεγμένου πελάτη, σε αναδυόμενο — χωρίς να φύγει ο
// χρήστης από την καταχώρηση.
async function pmShowCard(){
  const vat=($('#pmVat').value||'').trim();if(!vat)return;
  const box=$('#pmCardBody');
  $('#pmCardTitle').textContent=PM_NAME||vat;
  box.innerHTML='<span class="spin"></span> Φόρτωση…';
  pmCardModal.showModal();
  const y=new Date().getFullYear();
  try{const d=await api({ledger:1,buyer_vat:vat,issue_date_from:y+'-01-01',issue_date_to:y+'-12-31'});
    if(!d.success)throw new Error(d.error||'σφάλμα');
    const rows=(d.entries||[]).slice(-12).reverse();
    box.innerHTML=`<div class="cards">
        <div class="card"><div class="k">Τζίρος</div><div class="v">${fmt(d.total_invoiced)} €</div></div>
        <div class="card"><div class="k">Πληρωμές</div><div class="v" style="color:#86efac">${fmt(d.total_paid)} €</div></div>
        <div class="card"><div class="k">Υπόλοιπο</div><div class="v balance ${d.balance>0.005?'pos':'zero'}">${fmt(d.balance)} €</div></div>
      </div>
      <table style="margin-top:10px"><thead><tr><th>Ημ/νία</th><th>Κίνηση</th><th class="num">Χρέωση</th><th class="num">Πίστωση</th></tr></thead><tbody>`+
      (rows.map(e=>`<tr><td>${esc(e.date)}</td><td>${e.kind==='invoice'?('ΜΑΡΚ '+esc(e.mark||'')):('Πληρωμή '+esc(payMethod(e.method)))}</td><td class="num">${e.debit?fmt(e.debit):''}</td><td class="num">${e.credit?fmt(e.credit):''}</td></tr>`).join('')
        ||'<tr><td colspan="4" class="muted">Καμία κίνηση φέτος.</td></tr>')+'</tbody></table>';
    // Το ποσό του υπολοίπου είναι σχεδόν πάντα αυτό που θα εισπραχθεί.
    if(d.balance>0.005&&!$('#pmAmount').value)$('#pmAmount').value=d.balance.toFixed(2);
  }catch(e){box.innerHTML='<span class="pill bad">'+esc(e.message)+'</span>';}
}
document.addEventListener('click',e=>{const p=$('#pmAcPanel');if(p&&!e.target.closest('#pmAcPanel')&&e.target!==$('#pmCust'))p.classList.remove('open');});
async function savePayment(ev){ev.preventDefault();
  const vat=($('#pmVat').value||'').trim();
  if(!vat){$('#pmResult').textContent='Διάλεξε πελάτη.';return;}
  const name=PM_MODE==='card'?(CARD.customer_name||''):PM_NAME;
  const p={buyer_vat:vat,customer_name:name,pay_amount:$('#pmAmount').value,
           pay_method:$('#pmMethod').value,pay_date:di('pmDate'),pay_notes:$('#pmNotes').value};
  if(PM_EDIT){p.update_payment=1;p.payment_id=PM_EDIT;}else{p.add_payment=1;}
  try{const d=await api(p);
    if(!d.success)throw new Error(d.error||'σφάλμα');
    if(PM_EDIT){$('#payModal').close();toast('Η πληρωμή ενημερώθηκε','ok');loadCard();return;}
    toast('Πληρωμή καταχωρήθηκε','ok');
    pmRecent(name||vat,$('#pmAmount').value);
    if(PM_MODE==='card'){$('#payModal').close();loadCard();return;}
    if($('#pmRepeat').checked){
      // Ίδιος πελάτης, καθαρό ποσό: η επόμενη είσπραξη είναι ένα πεδίο μακριά.
      $('#pmAmount').value='';$('#pmNotes').value='';
      $('#pmResult').innerHTML='<span class="pill ok">Καταχωρήθηκε</span> — έτοιμο για την επόμενη.';
      $('#pmAmount').focus();
    }else $('#payModal').close();
  }catch(e){$('#pmResult').textContent='Πληρωμή: '+e.message;toast('Πληρωμή: '+e.message,'err');}}
// Μικρό ιστορικό συνεδρίας, ώστε να φαίνεται τι μόλις μπήκε χωρίς άνοιγμα καρτέλας.
let PM_LOG=[];
function pmRecent(who,amount){PM_LOG.unshift({who,amount:elFmt(elNum(amount))});PM_LOG=PM_LOG.slice(0,8);
  const el=$('#pmRecent');if(el)el.innerHTML=PM_LOG.length?('Καταχωρήθηκαν: '+PM_LOG.map(p=>`<b>${esc(p.who)}</b> ${esc(p.amount)} €`).join(' · ')):'';}
async function delPayment(id){if(!confirm('Διαγραφή πληρωμής;'))return;try{const d=await api({delete_payment_id:id});if(!d.success)throw new Error('απέτυχε');toast('Διαγράφηκε','ok');loadCard();}catch(e){toast(e.message,'err');}}

// Products
let PRODUCTS=[],CATEGORIES=[];
async function loadProducts(){await cachedThenSync('products',rows=>{PRODUCTS=rows;renderProducts();});}
function renderProducts(){const f=($('#prodFilter').value||'').toLowerCase();
  const rows=PRODUCTS.filter(p=>!f||JSON.stringify(p).toLowerCase().includes(f));
  $('#prodTable tbody').innerHTML=rows.map(p=>{const code=p.product_code||p.code||'',desc=p.description||'',cat=p.category||'',vat=p.vat||p.vat_category||'',price=p.unit_price||p.price||'';
    return `<tr><td>${esc(code)}</td><td>${esc(desc)}</td><td>${esc(cat)}</td><td>${esc(vat)}</td><td class="num">${price!==''?fmt(price):''}</td>
      <td class="right"><button class="ghost sm" onclick="editProduct('${q1(code)}','${q1(desc)}')">✎</button> <button class="danger sm" onclick="delProduct('${q1(code)}')">✕</button></td></tr>`;}).join('')||'<tr><td colspan="6" class="muted">Κανένα είδος.</td></tr>';
  applyColumnFilters('prodTable');}
async function loadCategories(){try{const d=await api({list_product_categories:1});CATEGORIES=d.product_categories||d.categories||d.items||[];const sel=$('#pdCategory');if(sel){sel.innerHTML='<option value="">—</option>'+CATEGORIES.map(c=>`<option value="${esc(c.id||c.category_id||'')}">${esc(c.name||c.category||c.category_name||'')}</option>`).join('');}}catch(e){}}
let PRODMAP={};
const VATPCT={1:24,2:13,3:6,4:17,5:9,6:4,7:0,8:0};
// Accepts a myDATA VAT category (1-8), a percent string ("24%"), or a plain number.
function vatPct(v){if(v===undefined||v===null||v==='')return 24;const s=String(v);if(s.includes('%'))return parseFloat(s)||0;const n=parseInt(s,10);if(n>=1&&n<=8)return VATPCT[n];return isNaN(n)?24:n;}
// Build PRODMAP + the <datalist> from a product rows array
function buildProdMap(products){const dl=$('#prodList');if(dl)dl.innerHTML='';PRODMAP={};
  (products||[]).forEach(p=>{const code=p.product_code||p.code;if(!code)return;const desc=p.description||'';const vat=p.vat||p.vat_category||'';const price=parseFloat(p.unit_price||p.price||0)||0;
    const good=String(p.type||'').trim()!=='Υπηρεσία';  // delivery notes accept goods only
    PRODMAP[code]={desc,vat,price,good};if(dl){const o=document.createElement('option');o.value=code;o.textContent=desc;dl.appendChild(o);}});}
async function loadProductList(){
  // cache-first: build the picker instantly from cached products, then refresh
  try{const c=await api({cached:'products'});if(c.rows&&c.rows.length)buildProdMap(c.rows);}catch(e){}
  try{const d=await api({list_products:1});buildProdMap(d.products||[]);}catch(e){}}
let PROD_EDIT=null,PROD_ONSAVED=null;
// Services carry no unit of measurement — hide the field for type=2 (Υπηρεσία).
function pdTypeChange(){$('#pdUnitField').style.display=$('#pdType').value==='2'?'none':'';
  const goods=$('#pdType').value==='1';const el=$('#pdClsSuggest');
  // Repo firebed/aade-mydata: goods sales (1.x) → «Έσοδα Πώλησης Εμπορευμάτων»
  // (category1_1); services (2.x) → «Έσοδα Παροχής Υπηρεσιών» (category1_3). Income
  // code E3_561_001 for χονδρική/B2B, E3_561_003 for λιανική (11.x). Διακίνηση=category3.
  if(el)el.innerHTML=goods
    ? '💡 Προτεινόμενος χαρακτηρισμός για <b>αγαθό</b>: «Έσοδα Πώλησης Εμπορευμάτων» (category1_1) — <b>E3_561_001</b> χονδρική / <b>E3_561_003</b> λιανική.'
    : '💡 Προτεινόμενος χαρακτηρισμός για <b>υπηρεσία</b>: «Έσοδα Παροχής Υπηρεσιών» (category1_3) — <b>E3_561_001</b> χονδρική / <b>E3_561_003</b> λιανική.';}
// Build a new product category pre-filled with the type-appropriate income
// classification for every active invoice type (validated against AADE cls_options).
async function suggestCatClsFromProduct(){
  const goods=$('#pdType').value==='1';
  if(!INV_TYPES.length){await loadCatCls();}
  toast('Φόρτωση προτεινόμενων χαρακτηρισμών…','');
  // Fetch every invoice type's options IN PARALLEL (was sequential → ~24 slow
  // round-trips). Server-side cache makes repeats near-instant.
  const opts=await Promise.all(INV_TYPES.map(async t=>({t,code:String(t.value||''),o:await clsOptions(String(t.value||''))})));
  const rows=[];
  for(const {t,code,o} of opts){
    const cats=o.categories||[];if(!cats.length)continue;
    const want=goods?['category1_1','category1_2','category1_3']:['category1_3','category1_1'];
    const cat=want.map(w=>cats.find(c=>c.category===w)).find(Boolean)||cats[0];
    if(!cat)continue;
    const retail=/(^|\s)11\./.test(t.label||'')||['57','58','59','60','61'].includes(code);
    const avail=(cat.codes||[]).map(x=>x.code);
    const pick=(retail?['E3_561_003','E3_561_006']:['E3_561_001','E3_561_002']).find(c=>avail.includes(c))||avail[0]||'';
    rows.push({invoice_type:code,category:cat.category,code:pick});
  }
  openCatClsModal();
  $('#catClsTitle').textContent='Νέα κατηγορία (προτεινόμενος χαρακτηρισμός)';
  $('#ccName').value=((goods?'ΑΓΑΘΑ ':'ΥΠΗΡΕΣΙΕΣ ')+($('#pdDesc').value||'')).trim().slice(0,40);
  $('#ccRows tbody').innerHTML='';
  if(rows.length){rows.forEach(r=>addCatClsRow(r));}else addCatClsRow();
  toast('Συμπληρώθηκε προτεινόμενος χαρακτηρισμός για '+(rows.length||0)+' τύπους — έλεγξε & αποθήκευσε','ok');
}
function openProductModal(prefillCode,onSaved,forceType){PROD_EDIT=null;PROD_ONSAVED=onSaved||null;$('#prodModalTitle').textContent='Νέο είδος';['pdCode','pdDesc'].forEach(i=>$('#'+i).value='');$('#pdPrice').value='0';$('#pdCode').readOnly=false;if(typeof prefillCode==='string')$('#pdCode').value=prefillCode;$('#pdType').value=forceType==='good'?'1':'2';pdTypeChange();loadCategories();$('#prodModal').showModal();}
function editProduct(code,desc){PROD_EDIT=code;PROD_ONSAVED=null;$('#prodModalTitle').textContent='Επεξεργασία είδους';$('#pdCode').value=code;$('#pdCode').readOnly=true;$('#pdDesc').value=desc;pdTypeChange();loadCategories();$('#prodModal').showModal();}
async function saveProduct(){if(!$('#pdCode').value||!$('#pdDesc').value){toast('Κωδικός & περιγραφή απαιτούνται','err');return;}
  // e-timologio requires a category on every product (empty → «The value '' is invalid»).
  if(!$('#pdCategory').value){toast('Χρειάζεται Κατηγορία. Πάτα «🏷️ Νέα κατηγορία με προτεινόμενο χαρακτηρισμό» ή διάλεξε υπάρχουσα.','err');
    $('#pdCategory').style.outline='2px solid #ef4444';setTimeout(()=>{$('#pdCategory').style.outline='';},2600);$('#pdCategory').focus();return;}
  const isService=$('#pdType').value==='2';
  const base={product_type:$('#pdType').value,product_description:$('#pdDesc').value,product_category:$('#pdCategory').value,vat_category:$('#pdVat').value,unit:isService?'':$('#pdUnit').value,unit_price:$('#pdPrice').value};
  const code=$('#pdCode').value;
  try{let d;if(PROD_EDIT)d=await api({update_product_code:PROD_EDIT,...base});else d=await api({new_product:1,product_code:code,...base});
    if(d.success===false)throw new Error(d.error||'σφάλμα');$('#prodModal').close();toast('Αποθηκεύτηκε','ok');
    await loadProductList();loadProducts();
    if(PROD_ONSAVED){const cb=PROD_ONSAVED;PROD_ONSAVED=null;cb(code);}
  }catch(e){toast('Είδος: '+e.message,'err');}}
async function delProduct(code){if(!confirm('Διαγραφή είδους '+code+';'))return;try{const d=await api({delete_product_code:code});if(d.success===false)throw new Error(d.error||'');toast('Διαγράφηκε','ok');loadProducts();}catch(e){toast(e.message,'err');}}

// Category-level classifications (χαρακτηρισμοί ανά κατηγορία, myDATA §9)
let CAT_CLS=[],INV_TYPES=[],CLS_OPTS={};
async function loadCatCls(){
  // cache-first: show cached categories + invoice types instantly, then refresh
  try{const cc=await api({cached:'categories'}),ci=await api({cached:'invtypes'});
    if(cc.rows&&cc.rows.length){CAT_CLS=cc.rows;if(ci.rows&&ci.rows.length)INV_TYPES=ci.rows;renderCatCls();}}catch(e){}
  try{const d=await api({category_cls:1});CAT_CLS=d.categories||[];INV_TYPES=d.invoice_types||[];renderCatCls();}catch(e){if(!CAT_CLS.length)toast('Χαρακτηρισμοί: '+e.message,'err');}}
function renderCatCls(){$('#catClsTable tbody').innerHTML=CAT_CLS.map(c=>{
  const chips=(c.classifications||[]).map(x=>`<span class="pill" title="${esc(x.invoice_type_label)} · ${esc(x.category_title)} · ${esc(x.code_title)}">${esc(x.invoice_type_label.split(' - ')[0]||x.invoice_type)} → ${esc(x.category)}/${esc(x.code)}</span>`).join(' ')||'<span class="muted">—</span>';
  return `<tr><td>${esc(c.name)}</td><td>${chips}</td><td class="right"><button class="ghost sm" onclick='editCatCls(${JSON.stringify(c.category_id)},${JSON.stringify(c.name)})'>✎ Χαρακτηρισμοί</button></td></tr>`;
}).join('')||'<tr><td colspan="3" class="muted">Καμία κατηγορία.</td></tr>';}
// options for an invoice type (cached): {categories:[{category,title,codes:[{code,title}]}]}
async function clsOptions(t){if(!t)return{categories:[]};if(CLS_OPTS[t])return CLS_OPTS[t];const d=await api({cls_options:1,type:t});CLS_OPTS[t]=d.success?d:{categories:[]};return CLS_OPTS[t];}
function ccRowHtml(){const opts='<option value="">Επίλεξε…</option>'+INV_TYPES.map(t=>`<option value="${esc(t.value)}">${esc(t.label)}</option>`).join('');
  return `<tr>
    <td><select class="cc-type" onchange="ccTypeChange(this.closest('tr'))" style="width:100%">${opts}</select></td>
    <td><select class="cc-cat" onchange="ccCatChange(this.closest('tr'))" style="width:100%"><option value="">—</option></select></td>
    <td><select class="cc-code" style="width:100%"><option value="">—</option></select></td>
    <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove()">✕</button></td></tr>`;}
function addCatClsRow(pre){const tb=$('#ccRows tbody');tb.insertAdjacentHTML('beforeend',ccRowHtml());const row=tb.lastElementChild;
  if(pre){row.querySelector('.cc-type').value=pre.invoice_type;ccTypeChange(row,pre.category,pre.code);}}
async function ccTypeChange(row,preCat,preCode){const t=row.querySelector('.cc-type').value;const catSel=row.querySelector('.cc-cat'),codeSel=row.querySelector('.cc-code');
  catSel.innerHTML='<option value="">…</option>';codeSel.innerHTML='<option value="">—</option>';
  const o=await clsOptions(t);row._opts=o;
  catSel.innerHTML='<option value="">—</option>'+(o.categories||[]).map(c=>`<option value="${esc(c.category)}">${esc(c.title)}</option>`).join('');
  if(preCat){catSel.value=preCat;ccCatChange(row,preCode);}}
function ccCatChange(row,preCode){const cat=row.querySelector('.cc-cat').value;const codeSel=row.querySelector('.cc-code');const o=row._opts||{categories:[]};
  const found=(o.categories||[]).find(c=>c.category===cat);
  codeSel.innerHTML='<option value="">—</option>'+((found&&found.codes)||[]).map(c=>`<option value="${esc(c.code)}">${esc(c.title)} (${esc(c.code)})</option>`).join('');
  if(preCode)codeSel.value=preCode;}
function openCatClsModal(){CATCLS_EDIT=0;$('#catClsTitle').textContent='Νέα κατηγορία';$('#ccName').value='';$('#ccName').readOnly=false;$('#ccErr').textContent='';$('#ccRows tbody').innerHTML='';addCatClsRow();$('#catClsModal').showModal();}
let CATCLS_EDIT=0;
function editCatCls(id,name){CATCLS_EDIT=id;$('#catClsTitle').textContent='Χαρακτηρισμοί: '+name;$('#ccName').value=name;$('#ccName').readOnly=true;$('#ccErr').textContent='';$('#ccRows tbody').innerHTML='';
  const c=CAT_CLS.find(x=>String(x.category_id)===String(id));const cls=(c&&c.classifications)||[];
  if(cls.length)cls.forEach(x=>addCatClsRow(x));else addCatClsRow();
  $('#catClsModal').showModal();}
function collectCatCls(){const out=[];document.querySelectorAll('#ccRows tbody tr').forEach(r=>{const t=r.querySelector('.cc-type').value,cat=r.querySelector('.cc-cat').value,code=r.querySelector('.cc-code').value;
  if(t&&cat)out.push({invoice_type:t,category:cat,code:code});});return out;}
async function saveCatCls(){const name=$('#ccName').value.trim();if(!name){$('#ccErr').textContent='Λείπει η ονομασία.';return;}
  const cls=collectCatCls();
  // guard: one classification per invoice type
  const seen={};for(const c of cls){if(seen[c.invoice_type]){$('#ccErr').textContent='Επιτρέπεται ένας χαρακτηρισμός ανά τύπο παραστατικού.';return;}seen[c.invoice_type]=1;}
  $('#ccErr').textContent='';
  try{const d=await api({save_category_cls:1,category_id:CATCLS_EDIT||0,category_name:name,cls:JSON.stringify(cls)});
    if(!d.success)throw new Error(d.error||'σφάλμα');$('#catClsModal').close();toast('Χαρακτηρισμοί αποθηκεύτηκαν','ok');loadCatCls();loadCategories();
  }catch(e){$('#ccErr').textContent=e.message;}}

// Issue — invoice types limited to the account's ACTIVE series (series is mandatory)
let SERIES=[];
// Rebuild the issue #iType dropdown from the current SERIES array
function applyIssueSeries(){const seen=new Set(),opts=[];
  SERIES.forEach(s=>{const v=String(s.invoice_type_code||'').trim();if(v&&!seen.has(v)){seen.add(v);opts.push({v,label:invLabelByValue(v)!==v?invLabelByValue(v):(s.invoice_type||v)});}});
  const sel=$('#iType');const cur=sel.value;
  if(opts.length){sel.innerHTML=opts.map(o=>`<option value="${esc(o.v)}">${esc(o.label)}</option>`).join('');
    if(opts.some(o=>o.v===cur))sel.value=cur;sel.title='';}
  else sel.innerHTML='<option value="">— καμία ενεργή σειρά —</option>';
  fillSeries();showIssueCls();}
async function loadIssueTypes(){await loadInvTypes();
  // cache-first: render instantly from cached series, then refresh in background
  try{const c=await api({cached:'series'});if(c.rows&&c.rows.length){SERIES=c.rows;applyIssueSeries();}}catch(e){}
  try{const d=await api({sync:'series'});SERIES=d.rows||[];applyIssueSeries();
    if(!SERIES.length)toast('Δεν υπάρχει ενεργή σειρά. Δημιούργησε σειρά για να εκδώσεις.','err');
  }catch(e){}}
function issueTypeChange(){fillSeries();sumTotals();}
// Populate the Σειρά dropdown for the selected invoice type (+ "new series" option).
function fillSeries(){const t=$('#iType').value;const sel=$('#iSeries');const cur=sel.value;
  const list=SERIES.filter(s=>String(s.invoice_type_code||'')===t);
  sel.innerHTML=list.map(s=>`<option value="${esc(s.series_code)}">${esc(s.series_code)}${s.description?(' — '+esc(s.description)):''}</option>`).join('')
    +'<option value="__new">➕ Νέα σειρά…</option>';
  if(list.some(s=>s.series_code===cur))sel.value=cur;else if(list[0])sel.value=list[0].series_code;}
async function seriesChange(){const sel=$('#iSeries');if(sel.value!=='__new')return;
  const t=$('#iType').value;if(!t){toast('Επίλεξε πρώτα τύπο','err');fillSeries();return;}
  const code=prompt('Κωδικός νέας σειράς για '+invLabelByValue(t)+' (π.χ. Α, ΤΠΥ):','');
  if(!code){fillSeries();return;}
  try{const d=await api({new_series:1,series_invoice_type:t,series_code:code.trim(),series_start_aa:'1',series_description:''});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    toast('Η σειρά δημιουργήθηκε','ok');await loadIssueTypes();$('#iType').value=t;fillSeries();$('#iSeries').value=code.trim();
  }catch(e){toast('Σειρά: '+e.message,'err');fillSeries();}}

// --- Guided Έκδοση wizard (doc type → πελάτης) --------------------------------
let WIZ_DONE=false;
function wizShow(on){const w=$('#issueWizard'),f=$('#issueFormPanel');if(!w||!f)return;
  w.style.display=on?'':'none';f.style.display=on?'none':'';
  if(on){$('#wizStep1').style.display='';$('#wizStep2').style.display='none';}}
function wizReset(){WIZ_DONE=false;ISSUE_WHO='';wizShow(true);}
// Έχει αρχίσει να συμπληρώνεται το παραστατικό; Τότε δεν το διακόπτουμε με τον
// οδηγό όταν ο χρήστης γυρίζει πίσω στην Έκδοση.
function issueHasContent(){
  if(($('#iAfm').value||'').trim()||($('#iName').value||'').trim())return true;
  if(window.__issueTempId)return true;
  return [...document.querySelectorAll('#iLines tbody tr')].some(tr=>{
    const code=tr.querySelector('.ln-code'), price=tr.querySelector('.ln-price');
    return (code&&code.value.trim())||(price&&parseFloat(price.value||'0')>0);
  });
}
function wizDoc(kind){
  if(kind==='delivery'){wizReset();showView('delivery');return;}
  $('#wizStep1').style.display='none';$('#wizStep2').style.display='';}
async function wizWho(who){WIZ_DONE=true;wizShow(false);ISSUE_WHO=who||'';
  if(!$('#iType').value)await loadIssueTypes();
  wizPickType(who);
  $('#issueMode').innerHTML=who==='pro'
    ?'🏢 <b>Τιμολόγιο</b> προς επαγγελματία — συμπλήρωσε ΑΦΜ (αυτόματη άντληση στοιχείων).'
    :'👤 <b>Απόδειξη λιανικής</b> προς ιδιώτη — ο ΑΦΜ είναι προαιρετικός.';
  setTimeout(()=>{const el=who==='idiot'?$('#iName'):$('#iAfm');if(el)el.focus();},60);}
// Pick the most suitable registered invoice type for the chosen customer kind
function wizPickType(who){const sel=$('#iType');const opts=[...sel.options].filter(o=>o.value);
  if(!opts.length)return;
  const nm=o=>((invLabelByValue(o.value)||o.textContent)||'').toLowerCase();
  let pick=who==='idiot'
    ?opts.find(o=>/λιανικ|αποδειξη|απόδειξη/.test(nm(o)))
    :opts.find(o=>/τιμολ/.test(nm(o)));
  if(pick){sel.value=pick.value;issueTypeChange();}
  else toast(who==='idiot'
    ?'Δεν υπάρχει σειρά λιανικής — δημιούργησέ την στις «Σειρές».'
    :'Δεν υπάρχει σειρά τιμολογίου — δημιούργησέ την στις «Σειρές».','err');}
// Called by prefill flows (Πελάτες→Έκδοση, φωνητικό) to bypass the wizard
function wizSkip(who){WIZ_DONE=true;wizShow(false);ISSUE_WHO=who||'';
  const m=$('#issueMode');if(m)m.innerHTML=who==='idiot'?'👤 <b>Απόδειξη λιανικής</b>':'🏢 <b>Τιμολόγιο</b> προς επαγγελματία';}
// Ποιον διάλεξε ο οδηγός: 'pro' (επιχείρηση) ή 'idiot' (ιδιώτης). Φιλτράρει τη
// λίστα πελατών στην Έκδοση — ένα τιμολόγιο σε ιδιώτη και μια απόδειξη σε
// επιχείρηση είναι και τα δύο λάθος, και φαίνονται μόνο όταν τα κόψει η ΑΑΔΕ.
let ISSUE_WHO='';
// Ιδιώτης ή επιχείρηση το κρίνει η **ιδιότητα**, όχι το ΑΦΜ: ένας ιδιώτης
// μπορεί κάλλιστα να έχει ΑΦΜ. Η λίστα πελατών της ΑΑΔΕ φέρνει έτοιμο το είδος
// («Ημεδαπή επιχείρηση» / «Ιδιώτης»)· αν λείπει, κοιτάμε το επάγγελμα, που για
// τους ιδιώτες συμπληρώνεται με κάτι που το δηλώνει.
function custIsPrivate(c){
  const t=((c.type||'')+' '+(c.job||'')).toLowerCase();
  return /ιδιωτ|ιδιώτ|private/.test(t);
}
function custIsBusiness(c){
  const t=((c.type||'')+' '+(c.job||'')).toLowerCase();
  if(custIsPrivate(c))return false;
  if(/επιχειρ|επιχείρ|εταιρ|company|business/.test(t))return true;
  // Άγνωστη ιδιότητα: πέφτουμε πίσω στο ΑΦΜ, που είναι ένδειξη — όχι απόδειξη.
  const v=(c.vat||'').replace(/\D/g,'');
  return v.length===9&&v!=='000000000';
}

// --- Μαζική έκδοση (bulk) ------------------------------------------------------
async function loadBulkView(){await loadInvTypes();
  try{if(!SERIES||!SERIES.length){const d=await api({list_series:1});SERIES=d.series||[];}
    const seen=new Set(),opts=[];
    SERIES.forEach(s=>{const v=String(s.invoice_type_code||'').trim();if(v&&!seen.has(v)){seen.add(v);opts.push({v,label:invLabelByValue(v)!==v?invLabelByValue(v):(s.invoice_type||v)});}});
    const sel=$('#blkType');
    sel.innerHTML=opts.length?opts.map(o=>`<option value="${esc(o.v)}">${esc(o.label)}</option>`).join(''):'<option value="">— καμία ενεργή σειρά —</option>';
    blkFillSeries();
  }catch(e){}
  if(!ALL_CUSTOMERS.length)loadCustomers();
  if(!Object.keys(PRODMAP).length)loadProductList();
  if(!$('#blkTable tbody').children.length)blkAddRow();
}
function blkFillSeries(){const t=$('#blkType').value;const sel=$('#blkSeries');
  const list=(SERIES||[]).filter(s=>String(s.invoice_type_code||'')===t);
  sel.innerHTML=list.length?list.map(s=>`<option value="${esc(s.series_code)}">${esc(s.series_code)}${s.description?(' — '+esc(s.description)):''}</option>`).join(''):'<option value="">—</option>';}
// --- Interactive bulk rows (customer/product pickers) -------------------------
function blkAddRow(vat='',name='',code='',qty=1,price=''){
  const tb=$('#blkTable tbody');const tr=document.createElement('tr');
  tr.innerHTML=`
    <td style="position:relative"><input class="blk-cust" value="${esc(name||vat)}" data-vat="${esc(vat)}" placeholder="Αναζήτηση πελάτη…" autocomplete="off" oninput="blkCustAc(this)" onfocus="blkCustAc(this)" style="width:100%"><div class="ac-panel"></div></td>
    <td style="position:relative"><input class="blk-code" value="${esc(prodText(code))}" data-code="${esc(code)}" placeholder="Αναζήτηση είδους…" autocomplete="off" oninput="blkProdAc(this)" onfocus="blkProdAc(this)" style="width:100%"><div class="ac-panel"></div></td>
    <td><input class="blk-qty" type="number" step="0.01" min="0" value="${esc(qty)}" oninput="blkCountUpd()" style="width:80px;text-align:right"></td>
    <td><input class="blk-price" type="text" inputmode="decimal" value="${esc(price)}" onblur="elFmtField(this,4)" placeholder="0,00" style="width:110px;text-align:right"></td>
    <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove();blkCountUpd()">✕</button></td>`;
  tb.appendChild(tr);blkCountUpd();}
function blkCustAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=inp.parentElement.querySelector('.ac-panel');
  if(!ALL_CUSTOMERS.length)loadCustomers();
  let rows=ALL_CUSTOMERS.map(custFields);if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.city).toLowerCase().includes(term));rows=rows.slice(0,30);
  const newRow=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="blkNewCust(this)">➕ Νέος πελάτης…</div>`;
  panel.innerHTML=newRow+rows.map(c=>`<div class="ac-row" onmousedown="blkPickCust(this,'${q1(c.vat)}','${q1(c.name)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function blkPickCust(el,vat,name){const td=el.closest('td');const inp=td.querySelector('.blk-cust');inp.value=name||vat;inp.dataset.vat=vat;td.querySelector('.ac-panel').classList.remove('open');blkCountUpd();}
function blkNewCust(el){const td=el.closest('td');const inp=td.querySelector('.blk-cust');td.querySelector('.ac-panel').classList.remove('open');
  const typed=(inp.value||'').trim();
  openCustomerModal(c=>{if(c){inp.value=c.name||c.vat||'';inp.dataset.vat=c.vat||'';blkCountUpd();}},/^\d{9}$/.test(typed)?typed:'');}
function blkProdAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=inp.parentElement.querySelector('.ac-panel');
  let items=Object.keys(PRODMAP).map(code=>({code,desc:PRODMAP[code].desc||'',vat:PRODMAP[code].vat}));
  if(term)items=items.filter(x=>(x.code+' '+x.desc).toLowerCase().includes(term));items=items.slice(0,40);
  const newRow=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="blkNewProd(this)">➕ Νέο είδος…</div>`;
  panel.innerHTML=newRow+items.map(x=>`<div class="ac-row" onmousedown="blkPickProd(this,'${q1(x.code)}')"><b>${esc(x.code)}</b> <small>${esc(x.desc)}${x.vat!==undefined&&x.vat!==''?' · ΦΠΑ '+vatPct(x.vat)+'%':''}</small></div>`).join('');
  panel.classList.add('open');}
function blkPickProd(el,code){const td=el.closest('td');const inp=td.querySelector('.blk-code');inp.value=prodText(code);inp.dataset.code=code;td.querySelector('.ac-panel').classList.remove('open');
  const tr=el.closest('tr');const priceInp=tr.querySelector('.blk-price');const p=PRODMAP[code];if(p&&p.price&&!elNum(priceInp.value))priceInp.value=elFmt(p.price,4);blkCountUpd();}
function blkNewProd(el){const td=el.closest('td');const inp=td.querySelector('.blk-code');td.querySelector('.ac-panel').classList.remove('open');
  const typed=(inp.value||'').trim();
  openProductModal(/^[\w.-]{1,20}$/.test(typed)&&!PRODMAP[typed]?typed:'',code=>{inp.value=prodText(code);inp.dataset.code=code;
    const tr=td.closest('tr');const priceInp=tr.querySelector('.blk-price');const p=PRODMAP[code];if(p&&p.price&&!elNum(priceInp.value))priceInp.value=elFmt(p.price,4);blkCountUpd();});}
document.addEventListener('click',e=>{if(!e.target.closest('#blkTable td'))document.querySelectorAll('#blkTable .ac-panel.open').forEach(p=>p.classList.remove('open'));});
function blkCountUpd(){const n=document.querySelectorAll('#blkTable tbody tr').length;$('#blkCount').textContent=n?(n+' γραμμές'):'';}
// Collect the interactive rows into bulk items using the common type/series/pay/lang
function blkCollectRows(announce){
  const type=$('#blkType').value,series=$('#blkSeries').value,pay=$('#blkPay').value,lang=$('#blkLang').value;
  if(!type){toast('Επίλεξε τύπο παραστατικού','err');return null;}
  if(!series){toast('Επίλεξε σειρά','err');return null;}
  const items=[],errs=[];
  document.querySelectorAll('#blkTable tbody tr').forEach((tr,i)=>{
    const vat=(tr.querySelector('.blk-cust').dataset.vat||'').trim();
    const code=(tr.querySelector('.blk-code').dataset.code||'').trim();
    const q=parseFloat((tr.querySelector('.blk-qty').value||'').replace(',','.'))||0;
    const pr=elNum(tr.querySelector('.blk-price').value);
    if(!vat&&!code&&!q)return; // skip empty row
    if(!/^\d{9}$/.test(vat)){errs.push(`Γραμμή ${i+1}: επίλεξε πελάτη`);return;}
    if(!code){errs.push(`Γραμμή ${i+1}: επίλεξε είδος`);return;}
    if(q<=0){errs.push(`Γραμμή ${i+1}: μη έγκυρη ποσότητα`);return;}
    items.push({afm:vat,type,series,payment:pay,issue_lang:lang,lines:[{code,qty:q,price:pr}]});
  });
  if(announce){let html=`<div class="card"><span class="pill ${errs.length?'warn':'ok'}">${items.length} έγκυρα</span>`;
    if(errs.length)html+=`<div style="margin-top:8px;color:#c0392b">${errs.map(esc).join('<br>')}</div>`;html+='</div>';$('#blkResult').innerHTML=html;}
  return {items,errs};
}
// Advanced: import the CSV textarea into interactive rows
function blkImportCsv(){const raw=($('#blkCsv').value||'').split(/\r?\n/);let added=0;
  raw.forEach(ln=>{const s=ln.trim();if(!s||s.startsWith('#'))return;const p=s.split(/[;,\t]/).map(x=>x.trim());if(p.length<4)return;
    const [afm,code,qty,price]=p;const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===afm);
    blkAddRow(afm,c?c.name:'',code,parseFloat((qty||'').replace(',','.'))||1,price?elFmt(parseFloat(price.replace(',','.'))||0,4):'');added++;});
  if(added){toast(added+' γραμμές προστέθηκαν','ok');$('#blkCsv').value='';}else toast('Καμία έγκυρη γραμμή στο κείμενο','err');}
async function bulkRun(live){
  const parsed=blkCollectRows(false);if(!parsed)return;
  const {items,errs}=parsed;
  if(!items.length){toast('Καμία έγκυρη γραμμή'+(errs.length?' — δες μηνύματα':''),'err');blkCollectRows(true);return;}
  if(errs.length&&!confirm(`${errs.length} γραμμές έχουν σφάλμα και θα παραλειφθούν. Συνέχεια με ${items.length};`)){blkCollectRows(true);return;}
  if(live&&!confirm(`ΟΡΙΣΤΙΚΗ μαζική έκδοση ${items.length} παραστατικών στην ΑΑΔΕ — καθένα θα λάβει ΜΑΡΚ και ΔΕΝ αναιρείται. Συνέχεια;`))return;
  $('#blkResult').innerHTML='<span class="spin"></span> '+(live?'Μαζική έκδοση…':'Δημιουργία προχείρων…')+' ('+items.length+')';
  try{
    // POST — the items payload can be large (GET would truncate).
    const body=new URLSearchParams();body.set('bulk_issue','1');body.set('items',JSON.stringify(items));if(live)body.set('live','1');if(ACCOUNT)body.set('account',ACCOUNT);
    const resp=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body});
    const txt=await resp.text();let d;try{d=JSON.parse(txt);}catch(e){throw new Error(txt.slice(0,200));}
    if(!d||d.success===false){$('#blkResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc((d&&d.error)||'')+'</div>';return;}
    const rows=(d.results||[]).map(r=>`<tr><td>${r.index+1}</td><td>${esc(r.afm||'')}</td><td>${esc(invLabelByValue(r.type)||r.type||'')}</td>
      <td>${r.success?`<span class="pill ok">${live?'ΜΑΡΚ '+esc(r.mark||''):'Πρόχειρο'}</span>${!live&&r.temp_id?` <span class="muted">${esc(r.temp_id.slice(0,8))}</span>`:''}`:`<span class="pill bad">Σφάλμα</span> <span class="muted">${esc(r.error||'')}</span>`}</td>
      <td class="num">${r.amount_total!=null?fmt(r.amount_total)+' €':''}</td></tr>`).join('');
    $('#blkResult').innerHTML=`<div class="card"><div class="row" style="justify-content:space-between"><b>${live?'Μαζική έκδοση':'Πρόχειρα'}</b><span><span class="pill ok">${d.ok} επιτυχή</span> ${d.failed?`<span class="pill bad">${d.failed} απέτυχαν</span>`:''}</span></div>
      <table style="margin-top:8px"><thead><tr><th>#</th><th>ΑΦΜ</th><th>Τύπος</th><th>Αποτέλεσμα</th><th class="num">Σύνολο</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    toast(`${d.ok}/${d.total} ${live?'εκδόθηκαν':'πρόχειρα'}`,d.failed?'warn':'ok');
  }catch(e){$('#blkResult').innerHTML='';toast('Μαζική: '+e.message,'err');}
}

// --- Σειρές: dedicated management view (list + create per type + delete) -------
function renderSeriesTable(rows){$('#srTable tbody').innerHTML=(rows||[]).map(s=>`<tr>
    <td>${esc(s.invoice_type||s.invoice_type_code||'')}</td>
    <td><strong>${esc(s.series_code||'')}</strong></td>
    <td>${esc(s.start_aa||'')}</td>
    <td class="muted">${esc(s.description||'')}</td>
    <td class="right"><button class="danger sm" onclick="delSeries('${q1(s.series_id||s.delete_id||'')}','${q1(s.series_code||'')}')">✕ Διαγραφή</button></td>
  </tr>`).join('')||'<tr><td colspan="5" class="muted">Καμία σειρά. Δημιούργησε μία με το κουμπί «➕ Νέα σειρά».</td></tr>';}
async function loadSeriesView(){
  const sel=$('#srType');
  // invoice-type dropdown for the "new series" popup (cache-first)
  try{const ci=await api({cached:'invtypes'});const types=(ci.rows&&ci.rows.length)?ci.rows:null;
    if(types)sel.innerHTML=types.map(t=>`<option value="${esc(t.value||t.code)}">${esc(t.label||((t.code||'')+' - '+(t.name||'')))}</option>`).join('');}catch(e){}
  if(!sel.options.length){try{const it=await api({invoice_types:1});const types=it.invoice_types||[];
    sel.innerHTML=types.map(t=>`<option value="${esc(t.value||t.code)}">${esc(t.label||((t.code||'')+' - '+(t.name||'')))}</option>`).join('');}catch(e){}}
  // series table (cache-first, then refresh)
  let shown=false;
  try{const c=await api({cached:'series'});if(c.rows&&c.rows.length){SERIES=c.rows;renderSeriesTable(c.rows);shown=true;}}catch(e){}
  if(!shown)$('#srTable tbody').innerHTML='<tr><td colspan="5"><span class="spin"></span></td></tr>';
  try{const d=await api({sync:'series'});SERIES=d.rows||[];renderSeriesTable(SERIES);}
  catch(e){if(!shown){$('#srTable tbody').innerHTML='';toast('Σειρές: '+e.message,'err');}}
}
// Open the "new series" popup (populates the type dropdown if needed)
async function openSeriesModal(){
  const sel=$('#srType');
  if(!sel.options.length){try{const it=await api({invoice_types:1});const types=it.invoice_types||[];
    sel.innerHTML=types.map(t=>`<option value="${esc(t.value||t.code)}">${esc(t.label||((t.code||'')+' - '+(t.name||'')))}</option>`).join('');}catch(e){}}
  $('#srCode').value='';$('#srAa').value='1';$('#srDesc').value='';$('#srModalResult').innerHTML='';
  seriesModal.showModal();
}
async function createSeriesUI(){
  const t=$('#srType').value;const code=$('#srCode').value.trim();
  if(!t){toast('Επίλεξε τύπο παραστατικού','err');return;}
  if(!code){toast('Δώσε κωδικό σειράς','err');return;}
  $('#srModalResult').innerHTML='<span class="spin"></span> Δημιουργία…';
  try{const d=await api({new_series:1,series_invoice_type:t,series_code:code,series_start_aa:$('#srAa').value||'1',series_description:$('#srDesc').value.trim()});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    seriesModal.close();toast(`Η σειρά «${code}» δημιουργήθηκε`,'ok');
    $('#srResult').innerHTML=`<div class="card"><span class="pill ok">Η σειρά «${esc(code)}» δημιουργήθηκε</span></div>`;
    SERIES=[];loadSeriesView();
  }catch(e){$('#srModalResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(e.message)+'</div>';}
}
async function delSeries(id,code){if(!id){toast('Λείπει το id σειράς','err');return;}
  if(!confirm('Διαγραφή σειράς '+(code||'')+';'))return;
  try{const d=await api({delete_series_id:id});if(d.success===false)throw new Error(d.error||'');
    toast('Η σειρά διαγράφηκε','ok');SERIES=[];loadSeriesView();
  }catch(e){toast('Διαγραφή: '+e.message,'err');}}

// Customer autocomplete on the issue form (searchable + fills all fields)
let acEl=null;
function custAc(el){acEl=el;const term=(el.value||'').toLowerCase().trim();const panel=$('#iCustAc');
  if(!ALL_CUSTOMERS.length){loadCustomers();}
  let rows=ALL_CUSTOMERS.map(custFields);
  // Επαγγελματίας → μόνο επιχειρήσεις· Ιδιώτης → μόνο ιδιώτες.
  if(ISSUE_WHO==='pro')rows=rows.filter(custIsBusiness);
  else if(ISSUE_WHO==='idiot')rows=rows.filter(c=>!custIsBusiness(c));   // ιδιώτης ή άγνωστο
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.code+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  const newRow=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="newCustFromIssue()">➕ Νέος πελάτης…</div>`;
  const note=(!rows.length&&ISSUE_WHO)?`<div class="ac-row muted">Κανένας ${ISSUE_WHO==='pro'?'επαγγελματίας':'ιδιώτης'} — άλλαξε επιλογή ή φτιάξε νέο πελάτη.</div>`:'';
  panel.innerHTML=newRow+note+rows.map(c=>`<div class="ac-row" onmousedown="pickCust('${q1(c.vat)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function pickCust(vat){const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===vat);if(!c)return;
  $('#iAfm').value=c.vat;$('#iName').value=c.name;$('#iAddress').value=c.address||'';$('#iCity').value=c.city||'';$('#iZip').value=c.zip||'';
  $('#iCustAc').classList.remove('open');showIssueCls();}
// Create a new customer from within the issue form; on save, fill the form with it.
function newCustFromIssue(){$('#iCustAc').classList.remove('open');const typed=($('#iAfm').value||'').trim();
  openCustomerModal(c=>{if(c){$('#iAfm').value=c.vat||$('#iAfm').value;$('#iName').value=c.name||'';$('#iAddress').value=c.address||'';$('#iCity').value=c.city||'';$('#iZip').value=c.zip||'';}},/^\d{9}$/.test(typed)?typed:'');}
document.addEventListener('click',e=>{const p=$('#iCustAc');if(p&&!e.target.closest('#iCustAc')&&e.target!==$('#iAfm')&&e.target!==$('#iName'))p.classList.remove('open');});
// Pre-fill the issue form for a specific customer (from the Πελάτες list)
function issueFor(vat,name){showView('issue');wizSkip(/^\d{9}$/.test(vat)?'pro':'idiot');$('#iAfm').value=vat;$('#iName').value=name||'';
  if(/^\d{9}$/.test(vat))lookupAfm();toast('Έκδοση για '+(name||vat),'ok');}

let afmTimer;
function lookupAfm(){clearTimeout(afmTimer);afmTimer=setTimeout(async()=>{const afm=$('#iAfm').value.trim();if(!/^\d{9}$/.test(afm))return;
  try{const d=await api({afm});const c=d.customer||d.info||d;if(c){$('#iName').value=c.name||c.customer_name||$('#iName').value;$('#iAddress').value=c.address||$('#iAddress').value;$('#iCity').value=c.city||$('#iCity').value;$('#iZip').value=c.zip||$('#iZip').value;toast('Στοιχεία πελάτη OK','ok');}}catch(e){}},400);}
// Lines editor (multi-line). Each line has a searchable product combobox that shows
// "code - description" in the field; the dropdown offers "➕ Νέο είδος" first, then items.
function prodText(code){const p=PRODMAP[code];return code?(code+(p&&p.desc?' - '+p.desc:'')):'';}
// Effective VAT rate (fraction) for a line: 0 for zero-VAT invoice types, else the
// product's VAT category, else 24%.
function rowRate(row){if(['22','23'].includes($('#iType').value))return 0;const code=(row.querySelector('.ln-code').dataset.code||'');const p=PRODMAP[code];return p&&p.vat!==undefined&&p.vat!==''?vatPct(p.vat)/100:0.24;}
function rowVatLabel(row){if(['22','23'].includes($('#iType').value))return '0%';const code=(row.querySelector('.ln-code').dataset.code||'');const p=PRODMAP[code];return p&&p.vat!==undefined&&p.vat!==''?vatPct(p.vat)+'%':'24%';}
function lineRowHtml(code,qty,price,disc){return `<tr>
  <td style="position:relative"><input class="ln-code" value="${esc(prodText(code))}" data-code="${esc(code||'')}" oninput="prodAc(this)" onfocus="prodAc(this)" placeholder="Επιλογή / αναζήτηση είδους…" autocomplete="off" style="width:100%"><div class="ac-panel ln-ac"></div></td>
  <td><input class="ln-qty" type="number" step="0.01" min="0" value="${esc(qty)}" oninput="lineFromInputs(this.closest('tr'))" style="width:72px"></td>
  <td class="num"><input class="ln-price" type="text" inputmode="decimal" value="${esc(price)}" oninput="lineFromInputs(this.closest('tr'))" onblur="elFmtField(this,4);lineFromInputs(this.closest('tr'))" placeholder="0,00" style="width:100px;text-align:right"></td>
  <td class="num"><input class="ln-disc" type="number" step="0.01" min="0" max="100" value="${esc(disc||'')}" oninput="lineFromInputs(this.closest('tr'))" placeholder="0" style="width:70px;text-align:right"></td>
  <td class="num ln-vat">—</td>
  <td class="num"><input class="ln-gross" type="text" inputmode="decimal" oninput="lineFromGross(this.closest('tr'))" onblur="elFmtField(this,2);sumTotals()" placeholder="0,00" style="width:110px;text-align:right"></td>
  <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove();sumTotals()">✕</button></td></tr>`;}
function addLine(code='',qty=1,price='',disc=''){$('#iLines tbody').insertAdjacentHTML('beforeend',lineRowHtml(code,qty,price,disc));sumTotals();}
// Product combobox dropdown for a line's code input
function prodAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=inp.parentElement.querySelector('.ln-ac');
  let items=Object.keys(PRODMAP).map(code=>({code,desc:PRODMAP[code].desc||'',vat:PRODMAP[code].vat}));
  const sel=inp.dataset.code||'';const showAll=!term||term===prodText(sel).toLowerCase();
  if(!showAll)items=items.filter(x=>(x.code+' '+x.desc).toLowerCase().includes(term));
  items=items.slice(0,50);
  const rowsHtml=items.map(x=>`<div class="ac-row" onmousedown="pickProd(this,'${q1(x.code)}')"><b>${esc(x.code)}</b> <small>${esc(x.desc)}${x.vat!==undefined&&x.vat!==''?' · ΦΠΑ '+vatPct(x.vat)+'%':''}</small></div>`).join('');
  panel.innerHTML=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="newProdForLine(this)">➕ Νέο είδος…</div>`+rowsHtml;
  panel.classList.add('open');}
function pickProd(el,code){const row=el.closest('tr');const inp=row.querySelector('.ln-code');const p=PRODMAP[code]||{};
  inp.value=prodText(code);inp.dataset.code=code;
  if(p.price&&!elNum(row.querySelector('.ln-price').value))row.querySelector('.ln-price').value=elFmt(elNum(p.price),4);
  row.querySelector('.ln-ac').classList.remove('open');lineFromInputs(row);}
function newProdForLine(el){const row=el.closest('tr');const inp=row.querySelector('.ln-code');row.querySelector('.ln-ac').classList.remove('open');
  const typed=(inp.value||'').trim();
  openProductModal(/^[\w.-]{1,20}$/.test(typed)&&!PRODMAP[typed]?typed:'',code=>{pickProd(el,code);});}
document.addEventListener('click',e=>{if(!e.target.closest('.ln-code')&&!e.target.closest('.ln-ac'))document.querySelectorAll('.ln-ac.open').forEach(p=>p.classList.remove('open'));});
// Recompute a line from unit price / qty / discount → gross (source of truth = unit price).
function lineFromInputs(row){const u=elNum(row.querySelector('.ln-price').value);const q=parseFloat(row.querySelector('.ln-qty').value)||0;const d=Math.min(parseFloat(row.querySelector('.ln-disc').value)||0,100);const r=rowRate(row);
  const net=u*q*(1-d/100);const gross=net*(1+r);
  const g=row.querySelector('.ln-gross');if(document.activeElement!==g)g.value=net?elFmt(gross,2):'';
  sumTotals();}
// User typed the gross (with VAT) directly → derive unit price / discount.
// If the item's list unit price is higher than the implied one, express the gap as a discount %.
function lineFromGross(row){const G=elNum(row.querySelector('.ln-gross').value);const q=parseFloat(row.querySelector('.ln-qty').value)||0;const r=rowRate(row);
  const netFromG=G/(1+r);const priceInp=row.querySelector('.ln-price');const discInp=row.querySelector('.ln-disc');
  const u=elNum(priceInp.value);
  if(q>0&&u>0){const baseNet=u*q;
    if(baseNet>0&&netFromG<baseNet-0.005){discInp.value=((1-netFromG/baseNet)*100).toFixed(2);}      // list price higher ⇒ discount
    else{discInp.value='';priceInp.value=elFmt(netFromG/q,4);}
  }else if(q>0){priceInp.value=elFmt(netFromG/q,4);discInp.value='';}
  sumTotals();}
function collectLines(){const out=[];document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const code=(r.querySelector('.ln-code').dataset.code||'').trim();const qty=parseFloat(r.querySelector('.ln-qty').value)||0;const price=elNum(r.querySelector('.ln-price').value);const disc=parseFloat(r.querySelector('.ln-disc').value)||0;
  if(code&&price>0&&qty>0){const o={code,qty,price};if(disc>0)o.disc=disc;out.push(o);}});return out;}
// Totals: net + VAT (per-line rate) − withholding = payable.
function sumTotals(){let net=0,vat=0;document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const u=elNum(r.querySelector('.ln-price').value);const q=parseFloat(r.querySelector('.ln-qty').value)||0;const d=Math.min(parseFloat(r.querySelector('.ln-disc').value)||0,100);const rate=rowRate(r);
  const ln=u*q*(1-d/100);net+=ln;vat+=ln*rate;
  r.querySelector('.ln-vat').textContent=rowVatLabel(r);
  const g=r.querySelector('.ln-gross');if(document.activeElement!==g)g.value=ln?elFmt(ln*(1+rate),2):'';});
  // Taxes: withheld(1) & deductions(5) reduce payable; fees(2)/other(3)/digital(4) add.
  let plus=0,minus=0;(ITAXES||[]).forEach(t=>{if(t.type===1||t.type===5)minus+=t.amount;else plus+=t.amount;});
  $('#iNet').textContent=fmt(net);$('#iVat').textContent=fmt(vat);
  $('#iTaxPlus').textContent=fmt(plus);$('#iTaxMinus').textContent=fmt(minus);
  $('#iPayable').textContent=fmt(net+vat+plus-minus);
  showIssueCls();}
const recalcLines=sumTotals;   // back-compat alias

// --- Invoice taxes / withholdings / fees (Νέος Φόρος) ---
let TAXCATS=null,ITAXES=[];
const TAXTYPE_NAMES={1:'Παρακρατούμενοι',2:'Τέλη',3:'Άλλοι φόροι',4:'Ψηφιακό Τέλος',5:'Κρατήσεις'};
const TAXTYPE_KEY={1:'withheld',2:'fees',3:'other',4:'digital',5:'deductions'};
async function loadTaxCats(){if(TAXCATS)return TAXCATS;try{TAXCATS=await api({tax_categories:1});}catch(e){TAXCATS={};}return TAXCATS;}
function isServiceType(){return ['20','21','22','58','59'].includes($('#iType').value)||/2\.|11\.[25]/.test(invLabelByValue($('#iType').value));}
function openTaxModal(){['txAmount','txNotes'].forEach(i=>$('#'+i).value='');$('#txType').value='';$('#txCat').innerHTML='<option value="">Επιλέξτε…</option>';$('#txWarn').textContent='';$('#txErr').textContent='';loadTaxCats();$('#taxModal').showModal();}
async function txTypeChange(){const t=$('#txType').value;const sel=$('#txCat');$('#txWarn').textContent='';$('#txErr').textContent='';
  await loadTaxCats();
  // Παρακράτηση φόρου (type 1) applies only to provision of services.
  if(t==='1'&&!isServiceType()){$('#txWarn').textContent='Η παρακράτηση φόρου αφορά μόνο παροχή υπηρεσιών.';}
  const list=(TAXCATS&&TAXCATS[TAXTYPE_KEY[t]])||[];
  sel.innerHTML='<option value="">Επιλέξτε…</option>'+list.map(c=>`<option value="${esc(c.code)}">${esc(c.label)}</option>`).join('')
    +(t==='5'?'<option value="__new">➕ Νέα κράτηση…</option>':'');}
// Extract a percentage rate from a tax-category label ("… 3%" / "1,5%") → 0.03
function taxRateFromLabel(label){const m=(label||'').match(/(\d+(?:[.,]\d+)?)\s*%/);return m?parseFloat(m[1].replace(',','.'))/100:0;}
// Current net (pre-VAT) total of the issue lines — the base for withholdings.
function issueNetTotal(){let net=0;document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const u=elNum(r.querySelector('.ln-price').value);const q=parseFloat(r.querySelector('.ln-qty').value)||0;
  const d=Math.min(parseFloat(r.querySelector('.ln-disc').value)||0,100);net+=u*q*(1-d/100);});return net;}
$('#txCat')&&$('#txCat').addEventListener('change',function(){
  const t=$('#txType').value;$('#txWarn').textContent='';
  if(this.value==='__new'){createNewDeduction();return;}
  if(t==='1'&&this.value==='3')$('#txWarn').textContent='«Αμοιβές Συμβούλων Διοίκησης 20%»: μόνο για ατομικές επιχειρήσεις.';
  // Auto-compute the amount from the category's % over the current net total
  const list=(TAXCATS&&TAXCATS[TAXTYPE_KEY[t]])||[];const c=list.find(x=>x.code===this.value);
  const rate=taxRateFromLabel(c&&c.label);
  if(rate>0){const net=issueNetTotal();const amt=Math.round(net*rate*100)/100;
    $('#txAmount').value=amt.toFixed(2);
    $('#txWarn').textContent=`Αυτόματο ποσό: ${(rate*100).toLocaleString('el-GR')}% × καθαρή ${fmt(net)} € = ${fmt(amt)} € (μπορείς να το αλλάξεις).`;}
});
// Create a new custom deduction (κράτηση) and refresh the dropdown selecting it.
async function createNewDeduction(){
  const name=prompt('Ονομασία νέας κράτησης:','');
  if(!name){$('#txCat').value='';return;}
  $('#txErr').textContent='';
  try{const d=await api({new_deduction:1,deduction_description:name.trim(),deduction_amount_type:'1',deduction_amount:'0',deduction_decrease_total_paid:'0'});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    TAXCATS=null;await loadTaxCats();await txTypeChange();
    const list=(TAXCATS&&TAXCATS.deductions)||[];const made=list.find(c=>(c.label||'').trim()===name.trim());
    if(made)$('#txCat').value=made.code;
    toast('Η κράτηση «'+name.trim()+'» δημιουργήθηκε','ok');
  }catch(e){$('#txErr').textContent='Κράτηση: '+e.message;$('#txCat').value='';}
}
async function saveTax(){const t=parseInt($('#txType').value,10);let cat=$('#txCat').value;const amt=parseFloat($('#txAmount').value)||0;const notes=$('#txNotes').value.trim();
  if(!t){$('#txErr').textContent='Επίλεξε είδος φόρου.';return;}
  if(t===1&&!isServiceType()){$('#txErr').textContent='Παρακράτηση φόρου μόνο σε παροχή υπηρεσιών.';return;}
  if(cat==='__new'){await createNewDeduction();return;}
  if(!cat){$('#txErr').textContent='Επίλεξε κατηγορία.';return;}
  if(amt<=0){$('#txErr').textContent='Δώσε ποσό > 0.';return;}
  const list=(TAXCATS&&TAXCATS[TAXTYPE_KEY[t]])||[];const clabel=(list.find(c=>c.code===cat)||{}).label||cat;
  ITAXES.push({type:t,category:cat,amount:amt,notes,label:clabel});renderTaxes();sumTotals();taxModal.close();}
function renderTaxes(){$('#iTaxes tbody').innerHTML=ITAXES.map((t,i)=>
  `<tr><td>${esc(TAXTYPE_NAMES[t.type]||t.type)}</td><td>${esc(t.label||t.category)}</td><td class="num">${fmt(t.amount)}</td><td>${esc(t.notes||'')}</td><td class="right"><button class="danger sm" onclick="removeTax(${i})">✕</button></td></tr>`
).join('')||'<tr><td colspan="5" class="muted">Καμία εγγραφή.</td></tr>';
  $('#iTaxHint').textContent=ITAXES.length?(ITAXES.length+' εγγραφές'):'';}
function removeTax(i){ITAXES.splice(i,1);renderTaxes();sumTotals();}

// Confirmation dialog before issuing (πρόχειρο ή LIVE) — replaces the old confirm().
function confirmIssue(){const lines=collectLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
  const ser=$('#iSeries').value;if(!ser||ser==='__new'){toast('Επίλεξε σειρά παραστατικού','err');return;}
  sumTotals();const tot=$('#iPayable').textContent;
  $('#icHead').textContent='⚠ ΟΡΙΣΤΙΚΗ έκδοση στην ΑΑΔΕ';
  $('#icBody').innerHTML='<b style="color:#fca5a5">Θα υποβληθεί ΟΡΙΣΤΙΚΑ στην ΑΑΔΕ και θα λάβει ΜΑΡΚ. Δεν αναιρείται.</b><br>'
    +'Τύπος: '+esc(invLabelByValue($('#iType').value))+' · Σειρά '+esc(ser)+'<br>Γραμμές: '+lines.length+' · Τελικό πληρωτέο: '+esc(tot)+' €';
  $('#icOk').textContent='📤 Ναι, έκδοση στην ΑΑΔΕ';
  issueConfirm.showModal();}
// Προεπισκόπηση: αποθηκεύει το παραστατικό ως πρόχειρο στο e-timologio (και ζητά το AADE preview).
async function previewInvoice(){const lines=collectLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή','err');return;}
  const ser=$('#iSeries').value;if(!ser||ser==='__new'){toast('Επίλεξε σειρά παραστατικού','err');return;}
  const p={preview:1,lines:JSON.stringify(lines),type:$('#iType').value,issue_series:ser,payment:$('#iPay').value,issue_lang:$('#iLang').value,afm:$('#iAfm').value.trim(),name:$('#iName').value,address:$('#iAddress').value,city:$('#iCity').value,zip:$('#iZip').value};
  if(ITAXES.length)p.taxes=JSON.stringify(ITAXES.map(t=>({type:t.type,category:t.category,amount:t.amount,notes:t.notes})));
  const notes=$('#iNotes').value.trim();if(notes)p.notes=notes;
  // Reuse the same draft on repeated previews so we don't pile up new drafts in Πρόχειρα.
  if(window.__issueTempId)p.temp_id=window.__issueTempId;
  $('#issueResult').innerHTML='<span class="spin"></span> Αποθήκευση προχείρου & προεπισκόπηση…';
  try{const d=await api(p);
    if(d.success){if(d.temp_id)window.__issueTempId=d.temp_id;
      $('#issueResult').innerHTML=`<div class="card"><span class="pill warn">Πρόχειρο (ενημερώθηκε)</span><div style="margin-top:8px">Αποθηκεύτηκε στο e-timologio · Temp ID <strong>${esc(d.temp_id||'')}</strong> <span class="muted">(ίδιο πρόχειρο — «🆕 Νέο» για νέο)</span></div></div>`;
      if(d.pdf_b64){cbOpenPdfB64(d.pdf_b64);toast('Προεπισκόπηση ΑΑΔΕ έτοιμη','ok');}
      else if(d.preview_error){$('#issueResult').innerHTML+=`<div class="card" style="margin-top:8px"><span class="pill bad">Η προεπισκόπηση απέτυχε</span> <span class="muted">${esc(d.preview_error)}</span> — το πρόχειρο αποθηκεύτηκε κανονικά.</div>`;toast('Αποθηκεύτηκε (χωρίς προεπισκόπηση)','warn');}
      else toast('Αποθηκεύτηκε ως πρόχειρο','ok');}
    else $('#issueResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#issueResult').innerHTML='';toast('Προεπισκόπηση: '+e.message,'err');}}
// Open a base64 PDF (from the AADE preview) in a new tab.
function cbOpenPdfB64(b64){try{const bin=atob(b64);const arr=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)arr[i]=bin.charCodeAt(i);
  const url=URL.createObjectURL(new Blob([arr],{type:'application/pdf'}));window.open(url,'_blank');}catch(e){}}
// Goods sale → offer to also create a Δελτίο Αποστολής for the goods lines.
function offerDelivery(lines){const goods=lines.filter(l=>PRODMAP[l.code]&&PRODMAP[l.code].good);
  if(!goods.length)return;
  window.__dnFromInv={afm:$('#iAfm').value.trim(),name:$('#iName').value,lines:goods.map(l=>({code:l.code,qty:l.qty,price:l.price}))};
  $('#issueResult').insertAdjacentHTML('beforeend',`<div class="card" style="margin-top:8px"><span class="pill">Αγαθά</span> Το παραστατικό περιέχει αγαθά — θέλεις να δημιουργήσεις και <strong>Δελτίο Αποστολής</strong>; <button class="add sm" style="margin-left:6px" onclick="deliveryFromInvoice()">🚚 Δελτίο με τα αγαθά</button></div>`);}
async function deliveryFromInvoice(){const o=window.__dnFromInv;if(!o)return;
  showView('delivery');await new Promise(r=>setTimeout(r,350));
  if(o.afm){dnPickCust(o.afm);await new Promise(r=>setTimeout(r,600));if(!$('#dnAfm').value){$('#dnAfm').value=o.afm;$('#dnName').value=o.name||'';$('#dnCust').value=o.name||o.afm;}}
  $('#dnLines tbody').innerHTML='';
  o.lines.forEach(l=>{addDnLine('',l.qty);const row=$('#dnLines tbody tr:last-child');dnPickProd(row.querySelector('.dl-code'),l.code);});
  toast('Το Δελτίο συμπληρώθηκε με τα αγαθά — έλεγξέ το','ok');}

// Start a fresh draft: the next «Αποθήκευση & Προεπισκόπηση» creates a new draft ID.
function issueNewDraft(){window.__issueTempId=null;$('#issueResult').innerHTML='<div class="card"><span class="pill">Νέο πρόχειρο</span> Το επόμενο Αποθήκευση θα δημιουργήσει νέο πρόχειρο.</div>';toast('Νέο πρόχειρο','ok');}
async function submitInvoice(viaIssue){const live=viaIssue===true;
  const lines=collectLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
  const ser=$('#iSeries').value;if(!ser||ser==='__new'){toast('Επίλεξε σειρά παραστατικού','err');return;}
  const p={lines:JSON.stringify(lines),type:$('#iType').value,issue_series:ser,payment:$('#iPay').value,issue_lang:$('#iLang').value,afm:$('#iAfm').value.trim(),name:$('#iName').value,address:$('#iAddress').value,city:$('#iCity').value,zip:$('#iZip').value};
  if(ITAXES.length)p.taxes=JSON.stringify(ITAXES.map(t=>({type:t.type,category:t.category,amount:t.amount,notes:t.notes})));
  const notes=$('#iNotes').value.trim();if(notes)p.notes=notes;
  if(live)p.live=1;
  $('#issueResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success){$('#issueResult').innerHTML=d.live?`<div class="card"><span class="pill ok">Εκδόθηκε</span><div style="margin-top:8px">ΜΑΡΚ <strong>${esc(d.mark)}</strong> · ΑΑ ${esc(d.aa)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € · ${docBtn(d.mark)}</div></div>`:`<div class="card"><span class="pill warn">Πρόχειρο</span><div style="margin-top:8px">Temp ID ${esc(d.temp_id)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € <span class="muted">(δεν υποβλήθηκε)</span></div></div>`;toast(d.live?'Εκδόθηκε':'Πρόχειρο OK','ok');if(d.live)window.__issueTempId=null;ITAXES=[];renderTaxes();sumTotals();offerDelivery(lines);}
    else $('#issueResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#issueResult').innerHTML='';toast('Έκδοση: '+e.message,'err');}}

// Classifications hint in Έκδοση (based on the first line's product)
let clsTimer;
function showIssueCls(){clearTimeout(clsTimer);clsTimer=setTimeout(async()=>{
  const first=document.querySelector('#iLines .ln-code');const prod=first?(first.dataset.code||'').trim():'';const type=$('#iType').value;
  if(!prod){$('#iCls').textContent='';return;}
  try{const d=await api({classifications:1,product:prod,type});
    if(d.success&&d.classifications.length)$('#iCls').innerHTML='🏷️ '+d.classifications.map(c=>`<span class="pill">${esc(c.code)} · ${esc(c.category_name)}</span>`).join(' ');
    else $('#iCls').innerHTML='<span class="muted">Χωρίς ορισμένο χαρακτηρισμό (θα χρησιμοποιηθεί ο προεπιλεγμένος).</span>';
  }catch(e){$('#iCls').textContent='';}
},300);}

// ==== Delivery / return note (goods, 9.x) ====================================
// dn invoice-type value → myDATA code (for matching registered series)
const DN_CODE={'503':'9.3','504':'9.1','505':'9.2'};
function dnInit(){loadProductList();if(!ALL_CUSTOMERS.length)loadCustomers();
  (SERIES.length?Promise.resolve():loadDnSeries()).then(dnFillSeries);
  dnLoadLoad();}
async function loadDnSeries(){try{const d=await api({list_series:1});SERIES=d.series||[];}catch(e){}}
// Series dropdown for the selected delivery type (+ new-series option)
function dnFillSeries(){const code=DN_CODE[$('#dnType').value]||'';const sel=$('#dnSeries');const cur=sel.value;
  const list=SERIES.filter(s=>String(s.invoice_type_code||'')===code);
  let html=list.map(s=>`<option value="${esc(s.series_code)}">${esc(s.series_code)}${s.description?(' — '+esc(s.description)):''}</option>`).join('');
  if(!list.length)html='<option value="Α">Α</option>';
  html+='<option value="__new">➕ Νέα σειρά…</option>';
  sel.innerHTML=html;
  if(list.some(s=>s.series_code===cur))sel.value=cur;else if(list[0])sel.value=list[0].series_code;}
async function dnSeriesChange(){const sel=$('#dnSeries');if(sel.value!=='__new')return;
  const code=DN_CODE[$('#dnType').value]||'';const c=prompt('Κωδικός νέας σειράς δελτίου (π.χ. Α):','');
  if(!c){dnFillSeries();return;}
  try{const d=await api({new_series:1,series_invoice_type:code,series_code:c.trim(),series_start_aa:'1',series_description:''});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    toast('Η σειρά δημιουργήθηκε','ok');await loadDnSeries();dnFillSeries();sel.value=c.trim();
  }catch(e){toast('Σειρά: '+e.message,'err');dnFillSeries();}}

// --- Customer autocomplete (fills ΑΦΜ/επωνυμία + saved delivery place) -------
let dnTimer;
function dnCustAc(el){const term=(el.value||'').toLowerCase().trim();const panel=$('#dnCustAcPanel');
  if(!ALL_CUSTOMERS.length)loadCustomers();
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  const nw=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="dnNewCust()">➕ Νέος πελάτης…</div>`;
  panel.innerHTML=nw+rows.map(c=>`<div class="ac-row" onmousedown="dnPickCust('${q1(c.vat)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function dnPickCust(vat){const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===vat);if(!c)return;
  $('#dnAfm').value=c.vat;$('#dnName').value=c.name;$('#dnCust').value=c.name||c.vat;$('#dnCustAcPanel').classList.remove('open');
  dnLoadCustDeliv(vat,c);}
function dnNewCust(){$('#dnCustAcPanel').classList.remove('open');
  openCustomerModal(c=>{if(c){$('#dnAfm').value=c.vat||'';$('#dnName').value=c.name||'';$('#dnCust').value=c.name||c.vat||'';dnLoadCustDeliv(c.vat,c);}});}
document.addEventListener('click',e=>{const p=$('#dnCustAcPanel');if(p&&!e.target.closest('#dnCustAcPanel')&&e.target!==$('#dnCust'))p.classList.remove('open');});
// Load the customer's saved delivery place; fall back to the customer's own address.
async function dnLoadCustDeliv(vat,cust){cust=cust||{};
  try{const d=await api({cust_deliv:1,buyer_vat:vat});const m=d.deliv||{};
    $('#dnDStreet').value=m.street||cust.address||'';
    $('#dnDNumber').value=m.number||'';
    $('#dnDCity').value=m.city||cust.city||'';
    $('#dnDZip').value=m.zip||cust.zip||'';
    $('#dnDBranch').value=(m.branch!==undefined&&m.branch!=='')?m.branch:'0';
  }catch(e){$('#dnDStreet').value=cust.address||'';$('#dnDCity').value=cust.city||'';$('#dnDZip').value=cust.zip||'';}}
function dnLookup(){clearTimeout(dnTimer);dnTimer=setTimeout(async()=>{const afm=$('#dnAfm').value.trim();if(!/^\d{9}$/.test(afm))return;
  try{const d=await api({afm});const c=d.customer||d.info||d;if(c){$('#dnName').value=c.name||c.customer_name||$('#dnName').value;$('#dnCust').value=$('#dnName').value;dnLoadCustDeliv(afm,{address:c.address,city:c.city,zip:c.zip});}}catch(e){}},400);}

// --- Loading place: company base (via profile) + localStorage reuse ----------
// Loading place is stored server-side in the DB (encrypted), per account, under
// the sentinel key __LOAD__ — so it's shared across devices, not per-browser.
async function dnLoadLoad(){try{const d=await api({cust_deliv:1,buyer_vat:'__LOAD__'});const s=d.deliv||{};
  if(s&&(s.street||s.city||s.zip||(s.branch&&s.branch!=='0'))){$('#dnLStreet').value=s.street||'';$('#dnLNumber').value=s.number||'';$('#dnLCity').value=s.city||'';$('#dnLZip').value=s.zip||'';$('#dnLBranch').value=(s.branch!==undefined&&s.branch!=='')?s.branch:'0';}}catch(e){}}
async function dnSaveLoad(){try{await api({save_cust_deliv:1,buyer_vat:'__LOAD__',deliv_street:$('#dnLStreet').value,deliv_number:$('#dnLNumber').value,deliv_city:$('#dnLCity').value,deliv_zip:$('#dnLZip').value,deliv_branch:$('#dnLBranch').value||'0'});}catch(e){}}
async function dnUseBase(){try{const d=await api({company_profile:1});const co=(d.company)||{};
  const addr=(co.address||'').trim();
  const zipM=addr.match(/(\d{5})/);const zip=zipM?zipM[1]:'';
  let rest=addr.replace(/\bΤ\.?Κ\.?:?/i,'').replace(/\bT\.?K\.?:?/i,'');
  if(zip)rest=rest.replace(zip,'');
  const numM=rest.match(/(\d+[Α-Ωα-ωA-Za-z]?)/);const number=numM?numM[1]:'';
  const r2=(number?rest.replace(number,'|'):rest+'|').split('|');
  const street=(r2[0]||'').replace(/[,\-\s]+$/,'').trim();
  const city=(r2[1]||'').replace(/^[\s,\-]+/,'').replace(/[\s,\-]+$/,'').trim();
  $('#dnLStreet').value=street||addr;$('#dnLNumber').value=number;$('#dnLCity').value=city;$('#dnLZip').value=zip;
  $('#dnLBranch').value='0';dnSaveLoad();toast('Συμπληρώθηκε η έδρα','ok');
}catch(e){toast('Έδρα: '+e.message,'err');}}

// --- Lines editor (product combobox, like the issue form) --------------------
function dnRowRate(row){const code=row.querySelector('.dl-code').dataset.code||'';const p=PRODMAP[code];return p&&p.vat!==undefined&&p.vat!==''?vatPct(p.vat)/100:0.24;}
function dnRowHtml(code,qty){return `<tr>
  <td style="position:relative"><input class="dl-code" value="${esc(prodText(code))}" data-code="${esc(code||'')}" oninput="dnProdAc(this)" onfocus="dnProdAc(this)" placeholder="Επιλογή / αναζήτηση αγαθού…" autocomplete="off" style="width:100%"><div class="ac-panel dl-ac"></div></td>
  <td><input class="dl-qty" type="number" step="0.01" min="0" value="${esc(qty)}" style="width:110px"></td>
  <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove()">✕</button></td></tr>`;}
function addDnLine(code='',qty=1){$('#dnLines tbody').insertAdjacentHTML('beforeend',dnRowHtml(code,qty));}
function dnProdAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=inp.parentElement.querySelector('.dl-ac');
  // Delivery notes move GOODS only — exclude services (type = Υπηρεσία).
  let items=Object.keys(PRODMAP).filter(code=>PRODMAP[code].good).map(code=>({code,desc:PRODMAP[code].desc||'',vat:PRODMAP[code].vat}));
  const sel=inp.dataset.code||'';const showAll=!term||term===prodText(sel).toLowerCase();
  if(!showAll)items=items.filter(x=>(x.code+' '+x.desc).toLowerCase().includes(term));
  items=items.slice(0,50);
  const rowsHtml=items.map(x=>`<div class="ac-row" onmousedown="dnPickProd(this,'${q1(x.code)}')"><b>${esc(x.code)}</b> <small>${esc(x.desc)}${x.vat!==undefined&&x.vat!==''?' · ΦΠΑ '+vatPct(x.vat)+'%':''}</small></div>`).join('')
    ||'<div class="ac-row muted">Κανένα αγαθό — το δελτίο δέχεται μόνο αγαθά</div>';
  panel.innerHTML=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="dnNewProd(this)">➕ Νέο αγαθό…</div>`+rowsHtml;
  panel.classList.add('open');}
function dnPickProd(el,code){const row=el.closest('tr');const inp=row.querySelector('.dl-code');const p=PRODMAP[code]||{};
  if(p&&p.good===false){toast('Το δελτίο δέχεται μόνο αγαθά — το είδος «'+code+'» είναι υπηρεσία','err');return;}
  inp.value=prodText(code);inp.dataset.code=code;
  row.querySelector('.dl-ac').classList.remove('open');}
function dnNewProd(el){const row=el.closest('tr');const inp=row.querySelector('.dl-code');row.querySelector('.dl-ac').classList.remove('open');
  const typed=(inp.value||'').trim();openProductModal(/^[\w.-]{1,20}$/.test(typed)&&!PRODMAP[typed]?typed:'',code=>{dnPickProd(el,code);},'good');}
document.addEventListener('click',e=>{if(!e.target.closest('.dl-code')&&!e.target.closest('.dl-ac'))document.querySelectorAll('.dl-ac.open').forEach(p=>p.classList.remove('open'));});
function collectDnLines(){const out=[];let skippedService=false;document.querySelectorAll('#dnLines tbody tr').forEach(r=>{
  const code=(r.querySelector('.dl-code').dataset.code||'').trim();const qty=parseFloat(r.querySelector('.dl-qty').value)||0;
  // Delivery note carries NO values — only goods code + quantity (price=0).
  if(code&&qty>0){if(PRODMAP[code]&&PRODMAP[code].good===false){skippedService=true;return;}out.push({code,qty,price:0});}});
  if(skippedService)toast('Παραλείφθηκαν υπηρεσίες — το δελτίο δέχεται μόνο αγαθά','err');
  return out;}
function recalcDn(){/* delivery notes carry no monetary values — nothing to total */}

function dnPayload(){return {delivery_note:1,dn_type:$('#dnType').value,dn_series:$('#dnSeries').value==='__new'?'Α':$('#dnSeries').value,
  move_purpose:$('#dnPurpose').value,afm:$('#dnAfm').value.trim(),name:$('#dnName').value,notes:$('#dnNotes').value,
  vehicle:$('#dnVehicle').value,dispatch_date:di('dnDate'),dispatch_time:$('#dnTime').value,
  load_street:$('#dnLStreet').value,load_number:$('#dnLNumber').value,load_city:$('#dnLCity').value,load_zip:$('#dnLZip').value,load_branch:$('#dnLBranch').value||'0',
  deliv_street:$('#dnDStreet').value,deliv_number:$('#dnDNumber').value,deliv_city:$('#dnDCity').value,deliv_zip:$('#dnDZip').value,deliv_branch:$('#dnDBranch').value||'0'};}
function dnNewDraft(){window.__dnTempId=null;$('#dnResult').innerHTML='<div class="card"><span class="pill">Νέο πρόχειρο</span> Το επόμενο Αποθήκευση θα δημιουργήσει νέο πρόχειρο δελτίο.</div>';toast('Νέο πρόχειρο','ok');}
async function submitDelivery(viaIssue){const live=viaIssue===true;
  if(live&&!confirm('ΟΡΙΣΤΙΚΗ έκδοση δελτίου στην ΑΑΔΕ — θα λάβει ΜΑΡΚ και δεν αναιρείται. Συνέχεια;'))return;
  const lines=collectDnLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
  dnSaveLoad();
  const p=dnPayload();p.lines=JSON.stringify(lines);
  if($('#dnPurpose').value==='5')p.reverse=1;
  if(live)p.live=1;
  $('#dnResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success)$('#dnResult').innerHTML=`<div class="card"><span class="pill ${d.live?'ok':'warn'}">${d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο'}</span><div style="margin-top:8px">Τύπος ${esc(d.type)} · σκοπός ${esc($('#dnPurpose option:checked').textContent)} · σύνολο ${fmt(d.amount_total)} €<br>${d.live?`ΜΑΡΚ <strong>${esc(d.mark)}</strong> · ${docBtn(d.mark)}`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`,toast(d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο','ok'),d.live&&(window.__dnTempId=null);
    else $('#dnResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#dnResult').innerHTML='';toast('Δελτίο: '+e.message,'err');}}

// --- Προεπισκόπηση δελτίου: αποθήκευση προχείρου + πραγματικό PDF ΑΑΔΕ --------
// Prefer the genuine AADE preview PDF (same PrintPreviewInvoice2PdfNew flow as
// invoices). Only if AADE declines to render do we fall back to the local jsPDF draft.
async function dnPreviewPdf(){
  const lines=collectDnLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή','err');return;}
  // Προεπισκόπηση = αποθήκευση προχείρου στο e-timologio + PDF
  dnSaveLoad();
  $('#dnResult').innerHTML='<span class="spin"></span> Προεπισκόπηση & αποθήκευση προχείρου…';
  try{const p=dnPayload();p.lines=JSON.stringify(lines);p.preview=1;p.issue_lang=($('#iLang')?$('#iLang').value:'el');if($('#dnPurpose').value==='5')p.reverse=1;
    if(window.__dnTempId)p.temp_id=window.__dnTempId;   // reuse same draft, no new id
    const sv=await api(p);
    if(sv&&sv.success){if(sv.temp_id)window.__dnTempId=sv.temp_id;
      $('#dnResult').innerHTML=`<div class="card"><span class="pill warn">Πρόχειρο δελτίο (ενημερώθηκε)</span><div style="margin-top:8px">Αποθηκεύτηκε στο e-timologio · Temp ID <strong>${esc(sv.temp_id||'')}</strong> <span class="muted">(ίδιο πρόχειρο — «🆕 Νέο» για νέο)</span></div></div>`;
      if(sv.pdf_b64){cbOpenPdfB64(sv.pdf_b64);toast('Προεπισκόπηση ΑΑΔΕ έτοιμη','ok');return;}
      // AADE didn't return a PDF — note it and fall back to the local draft below.
      toast('Η ΑΑΔΕ δεν επέστρεψε PDF — προσωρινό πρόχειρο','warn');
    } else {toast('Αποθήκευση: '+((sv&&sv.error)||'απέτυχε'),'err');}
  }catch(e){toast('Αποθήκευση: '+e.message,'err');}
  if(!window.jspdf){toast('Η βιβλιοθήκη PDF δεν φόρτωσε','err');return;}
  toast('Δημιουργία προχείρου PDF…','ok');
  try{
    await ensureFont();await loadInvTypes();
    const {jsPDF}=window.jspdf;const doc=new jsPDF({unit:'pt',format:'a4'});
    doc.addFileToVFS('DejaVuSans.ttf',FONT_B64);doc.addFont('DejaVuSans.ttf','DejaVu','normal');doc.setFont('DejaVu');
    const W=doc.internal.pageSize.getWidth();const AC=[14,165,233],DK=[35,45,60],MUT=[120,130,145];const L=40,R=W-40;
    doc.setFillColor(...AC);doc.rect(0,0,W,6,'F');
    const typeLbl=$('#dnType option:checked').textContent;
    doc.setTextColor(...DK);doc.setFontSize(16);doc.text('ΔΕΛΤΙΟ ΑΠΟΣΤΟΛΗΣ',L,44);
    doc.setFontSize(9);doc.setTextColor(190,40,40);doc.text('ΠΡΟΧΕΙΡΟ — ΔΕΝ ΑΠΟΤΕΛΕΙ ΠΑΡΑΣΤΑΤΙΚΟ',R,40,{align:'right'});
    doc.setTextColor(...MUT);
    doc.text(typeLbl+'  ·  Σειρά '+($('#dnSeries').value==='__new'?'Α':$('#dnSeries').value),R,56,{align:'right'});
    doc.text('Ημ/νία: '+($('#dnDate').value||'')+($('#dnTime').value?('  '+$('#dnTime').value):''),R,70,{align:'right'});
    // Recipient box
    doc.setDrawColor(...AC);doc.setLineWidth(0.8);doc.roundedRect(L,80,R-L,54,4,4,'S');
    doc.setTextColor(...DK);doc.setFontSize(11);doc.text('Παραλήπτης: '+($('#dnName').value||'—'),L+12,98);
    doc.setFontSize(9);doc.setTextColor(...MUT);
    doc.text('ΑΦΜ: '+($('#dnAfm').value||'—')+'   ·   Σκοπός: '+$('#dnPurpose option:checked').textContent+($('#dnVehicle').value?('   ·   Όχημα: '+$('#dnVehicle').value):''),L+12,114);
    const dAddr=[$('#dnDStreet').value,$('#dnDNumber').value,$('#dnDCity').value,$('#dnDZip').value].filter(Boolean).join(' ');
    doc.text('Παράδοση: '+(dAddr||'—')+'  (Υποκ. '+($('#dnDBranch').value||'0')+')',L+12,128);
    const lAddr=[$('#dnLStreet').value,$('#dnLNumber').value,$('#dnLCity').value,$('#dnLZip').value].filter(Boolean).join(' ');
    doc.setFontSize(9);doc.setTextColor(...MUT);doc.text('Φόρτωση: '+(lAddr||'—')+'  (Υποκ. '+($('#dnLBranch').value||'0')+')',L,150);
    // Lines
    let net=0;const body=lines.map(l=>{const t=l.qty*l.price;net+=t;const p=PRODMAP[l.code]||{};return [l.code+(p.desc?(' - '+p.desc):''),String(l.qty),fmt(l.price),fmt(t)];});
    doc.autoTable({startY:162,
      head:[['Είδος','Ποσότητα','Τιμή μον.','Σύνολο']],body,
      foot:[['','','Καθαρή αξία',fmt(net)]],
      styles:{font:'DejaVu',fontSize:8.5,cellPadding:5,textColor:DK,lineColor:[225,230,238],lineWidth:0.5},
      headStyles:{font:'DejaVu',fillColor:AC,textColor:[255,255,255],halign:'left',fontSize:9},
      footStyles:{font:'DejaVu',fillColor:[240,244,249],textColor:DK,fontSize:9.5},
      columnStyles:{1:{halign:'right',cellWidth:70},2:{halign:'right',cellWidth:80},3:{halign:'right',cellWidth:85}},
      alternateRowStyles:{fillColor:[248,250,252]},
      didParseCell:d=>{if(d.column.index>=1)d.cell.styles.halign='right';}
    });
    let y=doc.lastAutoTable.finalY+20;
    if($('#dnNotes').value){doc.setFontSize(9);doc.setTextColor(...MUT);doc.text('Σχόλια: '+$('#dnNotes').value,L,y);}
    doc.save('deltio-'+($('#dnAfm').value||'draft')+'.pdf');
    toast('Προεπισκόπηση PDF έτοιμη','ok');
  }catch(e){toast('PDF: '+e.message,'err');}
}

// Cancel / credit note
// Ακύρωση/Πιστωτικό: customer picker → their invoices → select → editable credit
function cxRange(){const y=new Date().getFullYear();if(!$('#cxFrom').value)dset('cxFrom',y+'-01-01');if(!$('#cxTo').value)dset('cxTo',y+'-12-31');}
function cxAc(inp){const term=(inp.value||'').toLowerCase().trim();const panel=$('#cxAcPanel');
  if(!ALL_CUSTOMERS.length)loadCustomers();
  let rows=ALL_CUSTOMERS.map(custFields);if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.city).toLowerCase().includes(term));rows=rows.slice(0,30);
  if(!rows.length){panel.classList.remove('open');return;}
  panel.innerHTML=rows.map(c=>`<div class="ac-row" onmousedown="cxPickCust('${q1(c.vat)}','${q1(c.name)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function cxPickCust(vat,name){$('#cxVat').value=vat;$('#cxCust').value=name||vat;$('#cxAcPanel').classList.remove('open');cxLoadInvoices();}
document.addEventListener('click',e=>{const p=$('#cxAcPanel');if(p&&!e.target.closest('#cxAcPanel')&&e.target!==$('#cxCust'))p.classList.remove('open');});
async function cxLoadInvoices(){let vat=$('#cxVat').value.trim();
  // If the user typed the name/AFM without clicking a suggestion, resolve it here.
  if(!vat){const term=($('#cxCust').value||'').trim().toLowerCase();
    if(term){if(!ALL_CUSTOMERS.length)await loadCustomers();
      const m=ALL_CUSTOMERS.map(custFields).find(c=>c.vat===term||c.name.toLowerCase()===term)
        ||(/^\d{9}$/.test(term)?{vat:term}:null);
      if(m){vat=m.vat;$('#cxVat').value=vat;}
      else toast('Ο πελάτης δεν βρέθηκε — αναζήτηση μόνο με το διάστημα','warn');
    }
  }
  cxRange();
  $('#cxTable tbody').innerHTML='<tr><td colspan="8"><span class="spin"></span></td></tr>';$('#cxSel').innerHTML='';
  try{const p={search_invoices:1,issue_date_from:di('cxFrom'),issue_date_to:di('cxTo')};if(vat)p.buyer_vat=vat;
    const d=await api(p);
    const inv=(d.invoices||[]).filter(i=>i.mark);
    CX_INV=inv;
    $('#cxTable tbody').innerHTML=inv.map((i,idx)=>`<tr><td>${esc(i.issue_date||'')}</td><td>${esc(i.type||'')}</td><td>${esc((i.series||'')+' '+(i.aa||''))}</td><td>${esc(i.counterpart_vat||i.buyer_vat||i.counterpart||'—')}</td><td class="num">${esc(i.net_value||'')}</td><td class="num">${esc(i.total||'')}</td><td>${esc(i.mark)}</td><td class="right"><button class="primary sm" onclick="cxPick(${idx})">Επιλογή</button></td></tr>`).join('')||'<tr><td colspan="8" class="muted">Κανένα χρεωστικό στο διάστημα.</td></tr>';
    applyColumnFilters('cxTable');
  }catch(e){$('#cxTable tbody').innerHTML='';toast('Παραστατικά: '+e.message,'err');}}
let CX_INV=[];
function cxPick(idx){const i=CX_INV[idx];if(!i)return;const net=parseGr(i.net_value);window.__cxTempId=null;
  $('#cxSel').innerHTML=`<div class="card"><div class="modal-head" style="font-size:15px">Πιστωτικό για ΜΑΡΚ ${esc(i.mark)}</div>
    <div class="row">
      <div class="field"><label>Καθαρή αξία πιστωτικού (€)</label><input id="cxAmount" type="number" step="0.01" min="0" value="${net.toFixed(2)}"></div>
      <div class="field grow"><label>Αιτιολογία (προαιρετικό)</label><input id="cxReason" placeholder="Λόγος"></div>
    </div>
    <div class="hint" style="margin-top:8px">👁 Προεπισκόπηση & 💾 Πρόχειρο = χωρίς υποβολή/ΜΑΡΚ. Μόνο το κόκκινο <b>Οριστική Έκδοση</b> υποβάλλει το πιστωτικό στην ΑΑΔΕ (ΜΑΡΚ).</div>
    <div class="row" style="margin-top:6px;align-items:center">
      <button class="info" onclick="previewCredit('${q1(i.mark)}')" title="Αποθηκεύει το πρόχειρο ΚΑΙ δείχνει το PDF — χωρίς υποβολή/ΜΑΡΚ. Επαναλαμβανόμενες προεπισκοπήσεις ενημερώνουν το ΙΔΙΟ πρόχειρο.">💾👁 Αποθήκευση &amp; Προεπισκόπηση</button>
      <div class="grow"></div>
      <button class="danger" onclick="doCredit(true,'${q1(i.mark)}')" title="ΟΡΙΣΤΙΚΗ υποβολή πιστωτικού στην ΑΑΔΕ — παίρνει ΜΑΡΚ">📤 Οριστική Έκδοση πιστωτικού (ΜΑΡΚ)</button>
    </div>
    <div id="cxResult" style="margin-top:12px"></div>
    <p class="hint">Πλήρης αξία = ακύρωση· μικρότερη αξία = μερική πίστωση. Τύπος 5.1 (τιμολόγια) ή 11.4 (λιανική) αυτόματα.</p>
  </div>`;
  $('#cxSel').scrollIntoView({behavior:'smooth',block:'nearest'});}
function parseGr(s){s=String(s||'0').replace(/[^0-9,.-]/g,'');if(s.includes(',')){s=s.replace(/\./g,'').replace(',','.');}return parseFloat(s)||0;}
// Προεπισκόπηση πιστωτικού = αποθήκευση προχείρου + πραγματικό PDF ΑΑΔΕ.
async function previewCredit(mark){if(!mark){toast('Επίλεξε παραστατικό','err');return;}
  const p={credit_note:1,cancel_mark:mark,reason:$('#cxReason').value,amount:parseFloat($('#cxAmount').value)||0,preview:1};
  if(window.__cxTempId)p.temp_id=window.__cxTempId;   // reuse same draft, no new id
  $('#cxResult').innerHTML='<span class="spin"></span> Αποθήκευση προχείρου & προεπισκόπηση…';
  try{const d=await api(p);
    if(d.success){if(d.temp_id)window.__cxTempId=d.temp_id;
      $('#cxResult').innerHTML=`<div class="card"><span class="pill warn">Πρόχειρο πιστωτικό (ενημερώθηκε)</span><div style="margin-top:8px">Τύπος ${esc(d.credit_type||'')} · Συσχ. ΜΑΡΚ ${esc(d.correlated_mark||mark)} · Temp ID <strong>${esc(d.temp_id||'')}</strong></div></div>`;
      if(d.pdf_b64){cbOpenPdfB64(d.pdf_b64);toast('Προεπισκόπηση ΑΑΔΕ έτοιμη','ok');}
      else if(d.preview_error){$('#cxResult').innerHTML+=`<div class="card" style="margin-top:8px"><span class="pill bad">Η προεπισκόπηση απέτυχε</span> <span class="muted">${esc(d.preview_error)}</span> — το πρόχειρο αποθηκεύτηκε.</div>`;toast('Αποθηκεύτηκε (χωρίς προεπισκόπηση)','warn');}
      else toast('Αποθηκεύτηκε ως πρόχειρο','ok');}
    else $('#cxResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#cxResult').innerHTML='';toast('Προεπισκόπηση: '+e.message,'err');}}
async function doCredit(viaIssue,mark){if(!mark){toast('Επίλεξε παραστατικό','err');return;}
  const live=viaIssue===true;
  if(live&&!confirm('ΟΡΙΣΤΙΚΗ έκδοση πιστωτικού στην ΑΑΔΕ — θα λάβει ΜΑΡΚ και δεν αναιρείται. Συνέχεια;'))return;
  const p={credit_note:1,cancel_mark:mark,reason:$('#cxReason').value,amount:parseFloat($('#cxAmount').value)||0};if(live)p.live=1;
  $('#cxResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success){const o=d.original||{};$('#cxResult').innerHTML=`<div class="card"><span class="pill ${d.live?'ok':'warn'}">${d.live?'Πιστωτικό εκδόθηκε':'Πρόχειρο πιστωτικό'}</span>
      <div style="margin-top:8px">Τύπος ${esc(d.credit_type)} (5.1/11.4) · Συσχ. ΜΑΡΚ ${esc(d.correlated_mark)}<br>Αρχικό: ${esc(o.type||'')} · ΑΦΜ ${esc(o.buyer_vat||'')} · καθαρή ${fmt(o.net||0)} €<br>${d.live?`Νέο ΜΑΡΚ <strong>${esc(d.mark)}</strong> · ${docBtn(d.mark)}`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`;
      toast(d.live?'Πιστωτικό εκδόθηκε':'Πρόχειρο πιστωτικό OK','ok');if(d.live)window.__cxTempId=null;}
    else $('#cxResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#cxResult').innerHTML='';toast('Πιστωτικό: '+e.message,'err');}}

// Drafts (προσωρινά αποθηκευμένα)
function draftRange(){const y=new Date().getFullYear();if(!$('#dfFrom').value)dset('dfFrom',y+'-01-01');if(!$('#dfTo').value)dset('dfTo',y+'-12-31');}
function renderDrafts(rows){rows=rows||[];$('#dfCount').textContent=rows.length+' πρόχειρα';
  const df=$('#dfAll');if(df)df.checked=false;
  const nameFor=v=>{const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===v);return c?c.name:'';};
  $('#draftsTable tbody').innerHTML=rows.map(t=>{const bv=t.buyer_vat||'';const nm=nameFor(bv);
    return `<tr><td class="grid-check"><input type="checkbox" class="df-chk" data-tid="${esc(t.temp_id||'')}" data-seller="${esc(t.seller_vat||'')}"></td><td>${esc(t.save_date||'')}</td><td>${esc(t.type||'')}</td><td>${esc(t.series||'')}</td><td>${esc(nm||bv||'—')}</td>
    <td class="right"><button class="info sm" onclick="previewDraft('${q1(t.enc_id||t.temp_id)}',this)" title="Φέρε το PDF προεπισκόπησης αυτού του προχείρου (χωρίς νέο πρόχειρο)">👁 Προεπισκόπηση</button>
    <button class="danger sm" onclick="delDraft('${q1(t.temp_id)}','${q1(t.seller_vat||'')}')">✕ Διαγραφή</button></td></tr>`;}).join('')
    ||'<tr><td colspan="6" class="muted">Κανένα πρόχειρο.</td></tr>';
  applyColumnFilters('draftsTable');}
function dfToggleAll(on){document.querySelectorAll('#draftsTable tbody tr').forEach(tr=>{if(tr.style.display==='none')return;const c=tr.querySelector('.df-chk');if(c)c.checked=!!on;});}
async function delSelectedDrafts(){
  const chks=[...document.querySelectorAll('#draftsTable .df-chk:checked')];
  if(!chks.length){toast('Δεν επέλεξες πρόχειρα','err');return;}
  if(!confirm(`Διαγραφή ${chks.length} επιλεγμένων προχείρων;`))return;
  let ok=0,fail=0;
  for(const c of chks){try{const d=await api({delete_temp_id:c.dataset.tid,seller_vat:c.dataset.seller||''});if(d.success===false)throw 0;ok++;}catch(e){fail++;}}
  toast(`Διαγράφηκαν ${ok}${fail?` · ${fail} απέτυχαν`:''}`,fail?'warn':'ok');loadDrafts();}
async function loadDrafts(){draftRange();
  // cache-first: show the last cached drafts snapshot instantly, then refresh
  // (sync:'drafts' both fetches for the selected range AND updates the cache)
  let shown=false;
  try{const c=await api({cached:'drafts'});if(c.rows&&c.rows.length){renderDrafts(c.rows);shown=true;}}catch(e){}
  if(!shown)$('#draftsTable tbody').innerHTML='<tr><td colspan="5"><span class="spin"></span></td></tr>';
  try{const d=await api({sync:'drafts',save_date_from:di('dfFrom'),save_date_to:di('dfTo')});renderDrafts(d.rows||[]);}
  catch(e){if(!shown)$('#draftsTable tbody').innerHTML='';toast('Πρόχειρα: '+e.message,'err');}}
// Preview the PDF of an EXISTING draft by its id — reuses the cached model, no new draft.
async function previewDraft(id,btn){const old=btn?btn.textContent:'';if(btn){btn.disabled=true;btn.textContent='…';}
  try{const d=await api({preview_temp:id});
    if(d&&d.success&&d.pdf_b64){cbOpenPdfB64(d.pdf_b64);toast('Προεπισκόπηση ΑΑΔΕ έτοιμη','ok');}
    else toast('Προεπισκόπηση: '+((d&&d.error)||'απέτυχε'),'err');
  }catch(e){toast('Προεπισκόπηση: '+e.message,'err');}
  finally{if(btn){btn.disabled=false;btn.textContent=old;}}}
async function delDraft(id,seller){if(!confirm('Διαγραφή πρόχειρου παραστατικού;'))return;
  try{const d=await api({delete_temp_id:id,seller_vat:seller});if(d.success===false)throw new Error(d.error||'');toast('Διαγράφηκε','ok');loadDrafts();}catch(e){toast('Διαγραφή: '+e.message,'err');}}

// --- Παραστατικά: όλα τα εκδοθέντα της περιόδου ------------------------------
// Η λίστα υπήρχε μόνο μέσα στην Ακύρωση (για να διαλέξεις ΜΑΡΚ) και μέσα στην
// Καρτέλα (ενός πελάτη). Εδώ είναι αυτοτελής ενότητα, με ό,τι ζητά ο λογιστής:
// επιλογή με checkbox, μαζική εκτύπωση και εξαγωγή ZIP.
let ALL_DOCS=[];
function docsYear(){const y=new Date().getFullYear();dset('docFrom',y+'-01-01');dset('docTo',y+'-12-31');loadDocs();}
function docsInit(){if(!$('#docFrom').value||!$('#docTo').value){docsYear();return;}
  if(!ALL_DOCS.length)loadDocs();}
async function loadDocs(){
  if(!$('#docFrom').value||!$('#docTo').value){const y=new Date().getFullYear();dset('docFrom',y+'-01-01');dset('docTo',y+'-12-31');}
  $('#docTable tbody').innerHTML='<tr><td colspan="11"><span class="spin"></span></td></tr>';
  try{const d=await api({search_invoices:1,issue_date_from:di('docFrom'),issue_date_to:di('docTo')});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    ALL_DOCS=(d.invoices||[]).filter(i=>i.mark);
    renderDocs();
  }catch(e){$('#docTable tbody').innerHTML='';toast('Παραστατικά: '+e.message,'err');}
}
function docRows(){
  const term=($('#docSearch').value||'').toLowerCase().trim();
  if(!term)return ALL_DOCS;
  return ALL_DOCS.filter(i=>[i.mark,i.series,i.aa,i.type,i.counterpart_vat,i.buyer_vat,i.counterpart,i.counterpart_name]
    .join(' ').toLowerCase().includes(term));
}
function renderDocs(){
  const rows=docRows();
  $('#docCount').textContent=rows.length+' / '+ALL_DOCS.length+' παραστατικά · '+
    fmt(rows.reduce((s,i)=>s+elNum(i.total||0),0))+' € σύνολο';
  $('#docTable tbody').innerHTML=rows.map(i=>{
    const who=i.counterpart_name||i.counterpart||i.counterpart_vat||i.buyer_vat||'—';
    // Ο τύπος έρχεται από την ΑΑΔΕ ήδη σαν «11.2 - ΑΠΥ (…)»: δεύτερη φορά το
    // ίδιο κείμενο δίπλα του ήταν σκέτη επανάληψη που φάρδαινε τη στήλη.
    return `<tr><td class="grid-check"><input type="checkbox" class="doc-cb" value="${esc(i.mark)}" onchange="docSelChanged()"></td>
      <td>${esc(i.issue_date||'')}</td>
      <td title="${esc(i.type||'')}">${esc(i.type||'')}</td>
      <td>${esc(i.series||'')}</td>
      <td>${esc(i.aa||'')}</td>
      <td title="${esc(who)}">${esc(who)}</td>
      <td class="num">${esc(i.net_value||'')}</td>
      <td class="num">${esc(i.vat_value||'')}</td>
      <td class="num">${esc(i.total||'')}</td>
      <td>${esc(i.mark)}</td>
      <td class="right">${docBtn(i.mark)}<button class="ghost sm" title="Αποστολή με email" onclick="event.stopPropagation();emailDocument('${q1(i.mark)}')">✉️</button></td></tr>`;}).join('')
    ||'<tr><td colspan="11" class="muted">Κανένα παραστατικό στο διάστημα.</td></tr>';
  applyColumnFilters('docTable');
  docSelChanged();
}
function docToggleAll(on){document.querySelectorAll('#docTable .doc-cb').forEach(cb=>{
  if(cb.closest('tr').style.display!=='none')cb.checked=on;});
  const all=$('#docAll');if(all)all.checked=on;docSelChanged();}
function docSelected(){return [...document.querySelectorAll('#docTable .doc-cb:checked')].map(cb=>cb.value);}
function docSelChanged(){const n=docSelected().length;
  const el=$('#docCount');if(!el)return;
  // Το πλήθος επιλογών γράφεται ΠΑΝΤΑ από την αρχή, αλλιώς το «0 επιλεγμένα»
  // δεν σβήνει ποτέ τον προηγούμενο αριθμό.
  el.textContent=el.textContent.replace(/ · επιλεγμένα.*$/,'')+(n?' · επιλεγμένα '+n:'');}
function docMeta(marks){const meta={};const set=new Set(marks);
  ALL_DOCS.forEach(i=>{if(set.has(i.mark))meta[i.mark]={issue_date:i.issue_date,series:i.series,aa:i.aa};});
  return meta;}
function printSelectedDocs(){const marks=docSelected();
  if(!marks.length){toast('Τσέκαρε πρώτα παραστατικά','err');return;}
  printMarks(marks,docMeta(marks));}
function zipSelectedDocs(){const marks=docSelected();
  if(!marks.length){toast('Τσέκαρε πρώτα παραστατικά','err');return;}
  toast('Λήψη ZIP ('+marks.length+' παραστατικά)…','ok');
  // POST και όχι URL: 200 ΜΑΡΚ μαζί με τα ονόματα αρχείων ξεπερνούν κάθε όριο
  // μήκους διεύθυνσης, και ο server απαντούσε 414 αντί για αρχείο.
  postDownload({bulk_pdf:1,mode:'zip',marks:marks.join(','),meta:JSON.stringify(docMeta(marks))});}
// Κατέβασμα μέσω κρυφής φόρμας: ο browser χειρίζεται το αρχείο, χωρίς να φύγει
// από τη σελίδα και χωρίς όριο μήκους.
function postDownload(params){
  let frame=$('#dlFrame');
  if(!frame){frame=document.createElement('iframe');frame.id='dlFrame';frame.name='dlFrame';
    frame.style.display='none';document.body.appendChild(frame);}
  const f=document.createElement('form');
  f.method='POST';f.action=API;f.target='dlFrame';f.style.display='none';
  const all=Object.assign({},params);if(ACCOUNT)all.account=ACCOUNT;
  Object.entries(all).forEach(([k,v])=>{const i=document.createElement('input');i.type='hidden';i.name=k;i.value=v;f.appendChild(i);});
  document.body.appendChild(f);f.submit();setTimeout(()=>f.remove(),2000);
}

// --- Αποστολή παραστατικού / καρτέλας με email -------------------------------
// Δύο αφετηρίες, ένας διάλογος. Το συνημμένο είτε το κατεβάζει ο server (ΜΑΡΚ)
// είτε ανεβαίνει έτοιμο από εδώ (καρτέλα, φτιαγμένη με jsPDF).
let MM_CTX=null;
function mailDefaults(kind,info){
  const company=($('#account option:checked')||{}).textContent||'';
  const who=(info.name||'').trim();
  const sign='\n\nΜε εκτίμηση,\n'+company;
  const hello=who?(who+','):'Αγαπητέ συνεργάτη,';
  if(kind==='doc'){
    const ref=((info.series||'')+' '+(info.aa||'')).trim();
    return {subject:('Παραστατικό '+ref).trim(),
      body:hello+'\n\nσας αποστέλλουμε συνημμένο το παραστατικό '+ref+
        (info.date?(' με ημερομηνία '+info.date):'')+
        (info.total?(', συνολικής αξίας '+info.total+' €'):'')+'.'+sign};
  }
  // Η καρτέλα έχει δικό της κείμενο: μιλά στην επωνυμία του πελάτη και λέει με
  // λέξεις τι είναι το υπόλοιπο. Το ίδιο κείμενο φτιάχνει και ο server για την
  // προγραμματισμένη αποστολή — μία διατύπωση, τρεις δρόμοι.
  return {subject:'Καρτέλα πελάτη'+(who?(' — '+who):''),
    body:cardMailBody({name:who,period:info.period,balance:info.balance})};
}
function openMailDialog(kind,info,attach){
  MM_CTX={kind,info,attach};
  // Τα IBAN μπαίνουν στο κείμενο, οπότε πρέπει να τα ξέρουμε πριν το γράψουμε.
  if(BANK_VAT!==ACCOUNT)loadBankSettings().then(()=>{if(MM_CTX&&MM_CTX.kind===kind)$('#mmBody').value=mailDefaults(kind,info||{}).body;});
  const d=mailDefaults(kind,info||{});
  $('#mmTitle').textContent=kind==='doc'?'Αποστολή παραστατικού':'Αποστολή καρτέλας';
  $('#mmTo').value=(info&&info.email)||'';
  $('#mmSubject').value=d.subject;
  $('#mmBody').value=d.body;
  // Ο χρήστης πρέπει να βλέπει ΟΛΑ όσα θα φύγουν, όχι μόνο το πρώτο.
  const files=[attach&&attach.name?attach.name:('ΠΑΡΑΣΤΑΤΙΚΟ-'+(info.mark||'')+'.pdf')];
  if(kind==='card'&&(+info.balance||0)>0.005&&BANK_CFG.pdf)files.push(BANK_CFG.pdf.name);
  $('#mmAttach').textContent='📎 '+files.join('  ·  ');
  $('#mmResult').textContent='';
  mailModal.showModal();
  // Το email του πελάτη ζει στην ΑΑΔΕ, όχι στη λίστα πελατών. Αν δεν το ξέρουμε
  // ήδη, το ζητάμε — ο server κρατά αντίγραφο, οπότε γίνεται μία φορά.
  if(!$('#mmTo').value&&info&&info.vat){
    $('#mmResult').innerHTML='<span class="spin"></span> Αναζήτηση email πελάτη…';
    api({customer_email:1,buyer_vat:info.vat}).then(d=>{
      if(d&&d.email&&!$('#mmTo').value)$('#mmTo').value=d.email;
      $('#mmResult').textContent=(d&&d.email)?'':'Ο πελάτης δεν έχει καταχωρημένο email — γράψε τη διεύθυνση.';
      if(!$('#mmTo').value)$('#mmTo').focus();
    }).catch(()=>{$('#mmResult').textContent='';});
  }
  if(!$('#mmTo').value)setTimeout(()=>$('#mmTo').focus(),40);
}
async function sendMailDoc(ev){
  ev.preventDefault();
  if(!MM_CTX)return;
  const p={email_document:1,to:$('#mmTo').value.trim(),
           subject:$('#mmSubject').value.trim(),body:$('#mmBody').value};
  p.kind=MM_CTX.kind;
  if(MM_CTX.info&&MM_CTX.info.vat)p.customer_vat=MM_CTX.info.vat;
  if(MM_CTX.kind==='doc')p.mark=MM_CTX.info.mark;
  else{p.pdf_base64=MM_CTX.attach.base64;p.pdf_name=MM_CTX.attach.name;
    // Το PDF των λογαριασμών μόνο όταν υπάρχει κάτι να πληρωθεί.
    if((+MM_CTX.info.balance||0)>0.005)p.attach_bank=1;}
  $('#mmResult').innerHTML='<span class="spin"></span> Αποστολή…';
  try{const d=await apostAcc(p);
    if(!d.success)throw new Error(d.error||'απέτυχε');
    mailModal.close();toast('Το email στάλθηκε','ok');
  }catch(e){$('#mmResult').textContent='Αποστολή: '+e.message;}
}
// Το email του πελάτη, από ό,τι ξέρουμε ήδη γι' αυτόν.
function customerEmail(vat){
  const c=(ALL_CUSTOMERS||[]).find(x=>(x.vat||x.customer_vat)===String(vat));
  return (c&&(c.email||c.customer_email))||'';
}
function emailDocument(mark){
  const row=(ALL_DOCS||[]).find(i=>i.mark===mark)||{};
  const vat=row.counterpart_vat||row.buyer_vat||'';
  openMailDialog('doc',{mark,series:row.series,aa:row.aa,date:row.issue_date,
    total:row.total,name:row.counterpart_name||row.counterpart||'',
    vat,email:customerEmail(vat)});
}

// ZIP downloads (browser handles the file)
function zipUrl(params){const q=new URLSearchParams(params);if(ACCOUNT)q.set('account',ACCOUNT);return API+'?'+q.toString();}
function zipCustomerInvoices(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε καρτέλα','err');return;}
  toast('Λήψη ZIP παραστατικών…','ok');window.location=zipUrl({invoices_zip:1,buyer_vat:vat,issue_date_from:di('cardFrom'),issue_date_to:di('cardTo')});}

// --- Μαζική εκτύπωση με προεπισκόπηση (web / thin client) --------------------
// Ό,τι κάνει και η εφαρμογή υπολογιστή, από τον browser: το backend κατεβάζει τα
// PDF (μία εξουσιοδοτημένη κλήση, μέσα στο scope του λογαριασμού) και εδώ τα
// ενώνουμε σε ΕΝΑ αρχείο, ώστε ο ενσωματωμένος προβολέας του browser να δώσει
// προεπισκόπηση + εκτύπωση όλων μαζί. Αν η ένωση δεν είναι διαθέσιμη, ανοίγουμε
// το καθένα χωριστά — καλύτερα από το να μη γίνει τίποτα.
let PDFLIB_P=null;
function ensurePdfLib(){
  if(window.PDFLib)return Promise.resolve(true);
  // ΤΟΠΙΚΟ αντίγραφο πρώτα: στην εφαρμογή υπολογιστή δεν υπάρχει internet κατά
  // κανόνα, και με μόνο το CDN η ένωση αποτύγχανε σιωπηλά — άνοιγαν δεκάδες
  // ξεχωριστά PDF αντί για μία προεπισκόπηση. Το CDN μένει ως εφεδρεία.
  if(!PDFLIB_P)PDFLIB_P=new Promise(res=>{
    const load=(src,next)=>{const s=document.createElement('script');
      s.src=src;s.onload=()=>res(true);s.onerror=()=>next?next():res(false);
      document.head.appendChild(s);};
    load('assets/vendor/pdf-lib.min.js',
         ()=>load('https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/dist/pdf-lib.min.js'));
  });
  return PDFLIB_P;
}
const b64ToBytes=b64=>{const bin=atob(b64);const a=new Uint8Array(bin.length);for(let i=0;i<bin.length;i++)a[i]=bin.charCodeAt(i);return a;};

async function printMarks(marks,meta){
  marks=(marks||[]).filter(Boolean);
  if(!marks.length){toast('Δεν επιλέχθηκαν παραστατικά','err');return;}
  if(marks.length>200){toast('Μέγιστο 200 παραστατικά ανά παρτίδα','err');return;}
  toast('Λήψη '+marks.length+' PDF…','ok');
  let d;
  try{ d=await api({bulk_pdf:1,mode:'json',marks:marks.join(','),meta:JSON.stringify(meta||{})}); }
  catch(e){ toast('Μαζική εκτύπωση: '+e.message,'err'); return; }
  const files=d.files||[];
  if(!files.length){toast('Κανένα PDF δεν κατέβηκε','err');return;}
  if(d.failed&&d.failed.length)toast(d.failed.length+' δεν κατέβηκαν','warn');
  const ok=await ensurePdfLib();
  if(!ok){files.forEach(f=>openPdfBlob(b64ToBytes(f.pdf_base64),f.name));return;}
  try{
    const merged=await PDFLib.PDFDocument.create();
    for(const f of files){
      const src=await PDFLib.PDFDocument.load(b64ToBytes(f.pdf_base64));
      const pages=await merged.copyPages(src,src.getPageIndices());
      pages.forEach(p=>merged.addPage(p));
    }
    openPdfBlob(await merged.save(),'ΠΑΡΑΣΤΑΤΙΚΑ.pdf',true);
    toast(files.length+' παραστατικά στην προεπισκόπηση','ok');
  }catch(e){ files.forEach(f=>openPdfBlob(b64ToBytes(f.pdf_base64),f.name)); }
}
function openPdfBlob(bytes,name,print){
  const url=URL.createObjectURL(new Blob([bytes],{type:'application/pdf'}));
  // ⚠️ Στην εφαρμογή υπολογιστή το `window.open` δεν ανοίγει τίποτα: το
  // QtWebEngine δεν φτιάχνει νέο παράθυρο από μόνο του και η κλήση γυρίζει
  // null. Η προεπισκόπηση εκτύπωσης «δεν λειτουργούσε» ακριβώς γι' αυτό.
  // Κατεβάζουμε το αρχείο — ο χειριστής λήψεων το ανοίγει με τον προβολέα του
  // συστήματος, που τυπώνει κανονικά.
  if(isEmbedded()){
    const a=document.createElement('a');
    a.href=url;a.download=name||'ΠΑΡΑΣΤΑΤΙΚΑ.pdf';
    document.body.appendChild(a);a.click();a.remove();
    toast('Το αρχείο κατεβαίνει και θα ανοίξει για εκτύπωση','ok');
    setTimeout(()=>URL.revokeObjectURL(url),120000);
    return;
  }
  const w=window.open(url,'_blank');
  if(!w){toast('Επίτρεψε τα αναδυόμενα παράθυρα για την εκτύπωση','warn');return;}
  // Ο προβολέας χρειάζεται λίγο για να φορτώσει πριν δεχτεί εντολή εκτύπωσης.
  if(print)w.addEventListener('load',()=>{try{w.print();}catch(_){}});
  setTimeout(()=>URL.revokeObjectURL(url),120000);
}
function printCustomerInvoices(){
  const rows=(window.CARD_INVOICES||[]);
  if(!rows.length){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  const meta={};rows.forEach(r=>{meta[r.mark]={issue_date:r.issue_date,series:r.series,aa:r.aa};});
  printMarks(rows.map(r=>r.mark),meta);
}
function zipAllInvoices(){const y=new Date().getFullYear();toast('Λήψη ZIP (έτος '+y+')…','ok');
  window.location=zipUrl({invoices_zip:1,issue_date_from:y+'-01-01',issue_date_to:y+'-12-31'});}

// Customer ledger PDF (χρεώσεις-πιστώσεις) via jsPDF + DejaVu (Greek) font
let FONT_B64=null;
function abToB64(buf){let bin='';const b=new Uint8Array(buf),c=0x8000;for(let i=0;i<b.length;i+=c)bin+=String.fromCharCode.apply(null,b.subarray(i,i+c));return btoa(bin);}
async function ensureFont(){if(FONT_B64)return;const r=await fetch('https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf');FONT_B64=abToB64(await r.arrayBuffer());}
// --- PDF καρτέλας ------------------------------------------------------------
// Ένας κατασκευαστής, τρεις χρήσεις: αποθήκευση, μεμονωμένη αποστολή, και
// μαζική αποστολή. Παλιά ήταν δεμένος με τα πεδία της οθόνης, οπότε η μαζική
// αποστολή δεν είχε πώς να τον καλέσει.
async function ledgerDoc(card,periodLabel,cust){
  await ensureFont();await loadInvTypes();
  const {jsPDF}=window.jspdf;const doc=new jsPDF({unit:'pt',format:'a4'});
  doc.addFileToVFS('DejaVuSans.ttf',FONT_B64);doc.addFont('DejaVuSans.ttf','DejaVu','normal');doc.setFont('DejaVu');
  const W=doc.internal.pageSize.getWidth();const AC=[14,165,233],DK=[35,45,60],MUT=[120,130,145];const L=40,R=W-40;
  // ---- Header band ----
  doc.setFillColor(...AC);doc.rect(0,0,W,6,'F');
  doc.setTextColor(...DK);doc.setFontSize(17);doc.text('ΚΑΡΤΕΛΑ ΠΕΛΑΤΗ',L,44);
  doc.setFontSize(9);doc.setTextColor(...MUT);
  doc.text('Περίοδος: '+(periodLabel||''),R,44,{align:'right'});
  doc.text('Ημ/νία έκδοσης: '+new Date().toLocaleDateString('el-GR'),R,60,{align:'right'});
  // ---- Customer details block ----
  cust=cust||{};
  doc.setDrawColor(...AC);doc.setLineWidth(0.8);doc.roundedRect(L,74,R-L,58,4,4,'S');
  doc.setTextColor(...DK);doc.setFontSize(12);doc.text(card.customer_name||cust.name||'—',L+12,94);
  doc.setFontSize(9);doc.setTextColor(...MUT);
  const addr=[cust.address,cust.city,cust.zip].filter(Boolean).join(', ');
  doc.text('ΑΦΜ: '+(card.customer_vat||'')+(cust.code?('   ·   Κωδ.: '+cust.code):''),L+12,110);
  doc.text('Διεύθυνση: '+(addr||'—'),L+12,124);
  // ---- Movements table (Χρέωση / Πίστωση / Υπόλοιπο) ----
  let totD=0,totC=0;
  const body=(card.entries||[]).map(e=>{totD+=(+e.debit||0);totC+=(+e.credit||0);
    let docLbl;
    if(e.kind==='invoice'){
      const parts=[invLabel(e.type)!==e.type?invLabel(e.type):(e.type||'Παραστατικό')];
      if(e.series)parts.push('Σειρά '+e.series);
      if(e.aa)parts.push('Αρ. '+e.aa);
      if(e.mark)parts.push('ΜΑΡΚ '+e.mark);
      docLbl=parts.join('  ·  ');
    }else docLbl='Πληρωμή'+(e.method?('  ·  '+payMethod(e.method)):'')+(e.notes?('  ·  '+e.notes):'');
    return [e.date||'',docLbl,e.debit?fmt(e.debit):'',e.credit?fmt(e.credit):'',fmt(e.balance)];});
  doc.autoTable({startY:146,
    head:[['Ημ/νία','Παραστατικό','Χρέωση','Πίστωση','Υπόλοιπο']],
    body,
    foot:[['','Σύνολα',fmt(totD),fmt(totC),fmt(card.balance)]],
    styles:{font:'DejaVu',fontSize:8.5,cellPadding:5,textColor:DK,lineColor:[225,230,238],lineWidth:0.5},
    headStyles:{font:'DejaVu',fillColor:AC,textColor:[255,255,255],halign:'left',fontSize:9},
    footStyles:{font:'DejaVu',fillColor:[240,244,249],textColor:DK,fontStyle:'normal',fontSize:9.5},
    columnStyles:{0:{cellWidth:70},2:{halign:'right',cellWidth:75},3:{halign:'right',cellWidth:75},4:{halign:'right',cellWidth:80}},
    alternateRowStyles:{fillColor:[248,250,252]},
    didParseCell:d=>{if(d.section==='foot'||d.column.index>=2)d.cell.styles.halign=d.column.index>=2?'right':'left';},
    didDrawPage:data=>{doc.setFontSize(8);doc.setTextColor(...MUT);
      doc.text('e-Timologio Pro',L,doc.internal.pageSize.getHeight()-24);
      doc.text('Σελίδα '+doc.internal.getNumberOfPages(),R,doc.internal.pageSize.getHeight()-24,{align:'right'});}
  });
  // ---- Summary line ----
  let y=doc.lastAutoTable.finalY+22;doc.setFontSize(10);doc.setTextColor(...DK);
  doc.text('Σύνολο χρεώσεων: '+fmt(totD)+' €',L,y);
  doc.text('Σύνολο πιστώσεων: '+fmt(totC)+' €',L+180,y);
  const bpos=card.balance>0.005;doc.setTextColor(...(bpos?[190,40,40]:[22,120,60]));
  doc.setFontSize(12);doc.text('Υπόλοιπο: '+fmt(card.balance)+' €',R,y,{align:'right'});
  return doc;
}

async function ledgerPdf(forEmail){
  if(!CARD||!CARD.entries){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  if(!window.jspdf){toast('Η βιβλιοθήκη PDF δεν φόρτωσε','err');return;}
  toast('Δημιουργία PDF…','ok');
  try{
    const period=$('#cardFrom').value+' έως '+$('#cardTo').value;
    const cust=(ALL_CUSTOMERS.map(custFields).find(c=>c.vat===CARD.customer_vat))||{};
    const doc=await ledgerDoc(CARD,period,cust);
    const name=ledgerFileName(CARD.customer_name,CARD.customer_vat);
    if(forEmail){
      // Ίδιο PDF, άλλη κατάληξη: αντί να αποθηκευτεί, ταξιδεύει συνημμένο.
      const b64=doc.output('datauristring').split(',')[1];
      openMailDialog('card',{
        vat:CARD.customer_vat,
        name:CARD.customer_name||CARD.customer_vat,
        email:customerEmail(CARD.customer_vat),
        period:isoToDmy(di('cardFrom'))+' – '+isoToDmy(di('cardTo')),
        balance:CARD.balance,
      },{name,base64:b64});
      return;
    }
    doc.save(name);
    toast('PDF καρτέλας έτοιμο','ok');
  }catch(e){toast('PDF: '+e.message,'err');}
}

// Το PDF ενός πελάτη από τα δεδομένα της μαζικής λίστας — χωρίς νέα κλήση στην
// ΑΑΔΕ: οι κινήσεις ήρθαν ήδη μαζί με τα υπόλοιπα.
async function ledgerPdfB64(row,periodLabel){
  let running=+row.opening||0;
  const entries=(row.entries||[]).map(e=>{
    running+=(+e.debit||0)-(+e.credit||0);
    return Object.assign({},e,{balance:Math.round(running*100)/100});
  });
  const cust=((ALL_CUSTOMERS||[]).map(custFields).find(c=>c.vat===row.vat))||{};
  const doc=await ledgerDoc({customer_vat:row.vat,customer_name:row.name,entries,balance:+row.balance||0},periodLabel,cust);
  return doc.output('datauristring').split(',')[1];
}

function emailLedger(){
  if(!CARD||!CARD.customer_vat){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  ledgerPdf(true);
}

// --- Τραπεζικοί λογαριασμοί & ρυθμίσεις αποστολής -----------------------------
// Ένα αντίγραφο στη μνήμη ανά εταιρεία: το χρειάζονται και οι Ρυθμίσεις (για
// επεξεργασία) και ο διάλογος email (για να γράψει τα IBAN μέσα στο μήνυμα).
let BANK_CFG={banks:[],accounts:[],prefs:{},pdf:null,mail_ready:false,smtp_ready:false},BANK_VAT='';

// Έλεγχος IBAN mod-97, ίδιος με τον server. Εδώ σταματά το λάθος όσο ο χρήστης
// κοιτάζει την οθόνη, αντί να το ανακαλύψει από μήνυμα αποτυχίας.
function ibanNorm(v){return String(v||'').toUpperCase().replace(/[^0-9A-Z]/g,'');}
function ibanPretty(v){return ibanNorm(v).replace(/(.{4})/g,'$1 ').trim();}
function ibanValid(v){
  const s=ibanNorm(v);
  if(s.length<15||s.length>34)return false;
  if(!/^[A-Z]{2}[0-9]{2}[0-9A-Z]+$/.test(s))return false;
  if(s.startsWith('GR')&&s.length!==27)return false;
  const moved=s.slice(4)+s.slice(0,4);
  let digits='';
  for(const c of moved)digits+=(c>='0'&&c<='9')?c:String(c.charCodeAt(0)-55);
  let rem=0;
  for(let i=0;i<digits.length;i+=7)rem=Number(String(rem)+digits.substr(i,7))%97;
  return rem===1;
}
function ibanBank(v){
  const s=ibanNorm(v);
  if(!s.startsWith('GR')||s.length<7)return '';
  const code=s.substr(4,3);
  const hit=(BANK_CFG.banks||[]).find(b=>b.code&&b.code===code);
  return hit?hit.name:'';
}

async function loadBankSettings(force){
  if(!ACCOUNT)return;
  if(!force&&BANK_VAT===ACCOUNT)return;
  try{
    const d=await apostAcc({bank_get:1});
    if(!d.success)return;
    BANK_CFG=d;BANK_VAT=ACCOUNT;
    if($('#bkTable'))bkRender();
  }catch(e){}
}

function bkRender(){
  const co=($('#account option:checked')||{}).textContent||'';
  $('#bkCompany').textContent=co?('— '+co):'';
  const tb=$('#bkTable tbody');
  tb.innerHTML=(BANK_CFG.accounts||[]).map((a,i)=>{
    const opts=(BANK_CFG.banks||[]).map(b=>`<option value="${esc(b.name)}"${b.name===a.bank?' selected':''}>${esc(b.name)}</option>`).join('');
    return `<tr>
      <td><select class="bk-bank" data-i="${i}"><option value="">— επιλογή —</option>${opts}</select></td>
      <td><input class="bk-iban" data-i="${i}" value="${esc(ibanPretty(a.iban))}" style="min-width:230px;font-family:Consolas,monospace" oninput="bkIbanTouch(this)"></td>
      <td><input class="bk-holder" data-i="${i}" value="${esc(a.holder||'')}" style="min-width:160px"></td>
      <td style="text-align:center"><input type="checkbox" class="bk-inmail" data-i="${i}"${a.in_email?' checked':''}></td>
      <td class="right"><button class="ghost sm" onclick="bkDelRow(${i})" title="Αφαίρεση">🗑</button></td>
    </tr>`;}).join('')
    ||'<tr><td colspan="5" class="muted">Κανένας λογαριασμός. Πάτα «➕ Λογαριασμός».</td></tr>';
  const p=BANK_CFG.prefs||{};
  $('#bkAutoSend').checked=!!p.auto_send_doc;
  $('#bkAutoBcc').value=p.auto_send_bcc||'';
  $('#bkSchedOn').checked=!!p.sched_enabled;
  $('#bkSchedDay').value=p.sched_day||1;
  $('#bkSchedDebit').checked=p.sched_only_debit!==false;
  $('#bkSchedMin').value=p.sched_min||0;
  const has=!!BANK_CFG.pdf;
  $('#bkPdfState').textContent=has?(BANK_CFG.pdf.name+' ('+Math.round(BANK_CFG.pdf.size/1024)+' KB)'):'δεν έχει ανέβει αρχείο';
  $('#bkPdfView').style.display=has?'':'none';
  $('#bkPdfDel').style.display=has?'':'none';
  // Η προειδοποίηση δεν πατά πάνω σε μήνυμα που μόλις έγραψε μια ενέργεια
  // (π.χ. «Αποθηκεύτηκε») — αλλιώς ο χρήστης δεν βλέπει ποτέ την επιβεβαίωση.
  if(!BANK_CFG.smtp_ready&&$('#bkResult').textContent==='')
    $('#bkResult').textContent='⚠️ Χωρίς SMTP δεν στέλνονται καρτέλες — συμπλήρωσε τον πάροχο email παραπάνω.';
}

// Καθώς πληκτρολογεί: πράσινο/κόκκινο περίγραμμα και αυτόματη επιλογή τράπεζας
// όταν ο κωδικός του IBAN την αναγνωρίζει με βεβαιότητα.
function bkIbanTouch(inp){
  const ok=ibanValid(inp.value);
  inp.style.borderColor=inp.value.trim()===''?'':(ok?'var(--ok)':'var(--bad)');
  if(!ok)return;
  const name=ibanBank(inp.value);
  if(!name)return;
  const sel=$(`.bk-bank[data-i="${inp.dataset.i}"]`);
  if(sel&&!sel.value)sel.value=name;
}

function bkCollect(){
  const rows=[];
  $$('#bkTable tbody tr').forEach(tr=>{
    const iban=tr.querySelector('.bk-iban');if(!iban)return;
    const i=iban.dataset.i;
    rows.push({bank:($(`.bk-bank[data-i="${i}"]`)||{}).value||'',
               iban:ibanNorm(iban.value),
               holder:($(`.bk-holder[data-i="${i}"]`)||{}).value||'',
               in_email:!!($(`.bk-inmail[data-i="${i}"]`)||{}).checked});
  });
  return rows.filter(r=>r.iban!=='');
}

function bkAddRow(){
  BANK_CFG.accounts=bkCollect();
  BANK_CFG.accounts.push({bank:'',iban:'',holder:'',in_email:true});
  bkRender();
}
function bkDelRow(i){
  const rows=bkCollect();rows.splice(i,1);BANK_CFG.accounts=rows;bkRender();
}

async function bkSave(){
  const rows=bkCollect();
  const bad=rows.filter(r=>!ibanValid(r.iban)).map(r=>ibanPretty(r.iban));
  if(bad.length){$('#bkResult').textContent='Άκυρο IBAN: '+bad.join(', ');toast('Έλεγξε τα IBAN','err');return;}
  const prefs={auto_send_doc:$('#bkAutoSend').checked,auto_send_bcc:$('#bkAutoBcc').value.trim(),
    sched_enabled:$('#bkSchedOn').checked,sched_day:+$('#bkSchedDay').value||1,
    sched_only_debit:$('#bkSchedDebit').checked,sched_min:+$('#bkSchedMin').value||0};
  $('#bkResult').innerHTML='<span class="spin"></span> Αποθήκευση…';
  try{
    const d=await apostAcc({bank_save:1,accounts:JSON.stringify(rows),prefs:JSON.stringify(prefs)});
    if(!d.success)throw new Error(d.error||'απέτυχε');
    BANK_CFG.accounts=d.accounts;BANK_CFG.prefs=d.prefs;
    $('#bkResult').textContent='Αποθηκεύτηκε.';toast('Οι ρυθμίσεις αποθηκεύτηκαν','ok');bkRender();
  }catch(e){$('#bkResult').textContent='Αποθήκευση: '+e.message;toast('Αποθήκευση: '+e.message,'err');}
}

async function bkUploadPdf(inp){
  const f=inp.files&&inp.files[0];if(!f)return;
  if(f.size>3*1024*1024){toast('Το PDF ξεπερνά τα 3 MB','err');inp.value='';return;}
  $('#bkPdfState').innerHTML='<span class="spin"></span> Ανέβασμα…';
  try{
    const b64=await new Promise((res,rej)=>{const r=new FileReader();r.onload=()=>res(String(r.result).split(',')[1]);r.onerror=rej;r.readAsDataURL(f);});
    const d=await apostAcc({bank_pdf_up:1,file_b64:b64,filename:f.name});
    if(!d.success)throw new Error(d.error||'απέτυχε');
    BANK_CFG.pdf={name:d.name,size:d.size};bkRender();toast('Το PDF ανέβηκε','ok');
  }catch(e){$('#bkPdfState').textContent='Ανέβασμα: '+e.message;toast('Ανέβασμα: '+e.message,'err');}
  inp.value='';
}
function bkViewPdf(){window.open(zipUrl({bank_pdf_dl:1}),'_blank');}
async function bkDeletePdf(){
  if(!confirm('Να αφαιρεθεί το PDF με τους λογαριασμούς;'))return;
  try{await apostAcc({bank_pdf_del:1});BANK_CFG.pdf=null;bkRender();toast('Αφαιρέθηκε','ok');}
  catch(e){toast('Αφαίρεση: '+e.message,'err');}
}

async function bkDispatchNow(){
  if(!confirm('Να σταλούν τώρα οι καρτέλες με βάση τα παραπάνω φίλτρα;'))return;
  $('#bkResult').innerHTML='<span class="spin"></span> Αποστολή…';
  try{
    const d=await apostAcc({ledger_dispatch:1,force:1,issue_date_from:yearStart(),issue_date_to:todayDmy()});
    if(!d.success)throw new Error(d.error||'απέτυχε');
    const extra=(d.no_email&&d.no_email.length)?(' · χωρίς email: '+d.no_email.length):'';
    $('#bkResult').textContent='Στάλθηκαν '+d.sent+' καρτέλες'+extra+'.';
    toast('Στάλθηκαν '+d.sent+' καρτέλες','ok');
  }catch(e){$('#bkResult').textContent='Αποστολή: '+e.message;toast('Αποστολή: '+e.message,'err');}
}

// Οι λογαριασμοί σε απλό κείμενο — ό,τι βλέπει ο πελάτης μέσα στο μήνυμα.
function bankLinesText(){
  const rows=(BANK_CFG.accounts||[]).filter(a=>a.in_email);
  if(!rows.length)return '';
  return '\n\nτραπεζικοί λογαριασμοί για την εξόφληση:\n'+
    rows.map(a=>'• '+(a.bank||'τράπεζα')+': '+ibanPretty(a.iban)+(a.holder?(' (δικαιούχος: '+a.holder+')'):'')).join('\n');
}

// --- Μαζική αποστολή καρτελών ------------------------------------------------
// Τα υπόλοιπα ΚΑΙ οι κινήσεις έρχονται με μία κλήση, οπότε τα PDF φτιάχνονται
// εδώ χωρίς επιπλέον ταξίδι στην ΑΑΔΕ ανά πελάτη.
let LB_ROWS=[];
function todayDmy(){const d=new Date();return String(d.getDate()).padStart(2,'0')+'/'+String(d.getMonth()+1).padStart(2,'0')+'/'+d.getFullYear();}
function yearStart(){return '01/01/'+new Date().getFullYear();}

async function openLedgerBulk(){
  if(!BANK_CFG.smtp_ready)await loadBankSettings(true);
  $('#lbFrom').value=di('cardFrom')||'';
  $('#lbTo').value=di('cardTo')||'';
  $('#lbResult').textContent='';
  $('#lbTable tbody').innerHTML='';
  ledgerBulkModal.showModal();
  lbLoad();
}

async function lbLoad(){
  $('#lbResult').innerHTML='<span class="spin"></span> Υπολογισμός υπολοίπων…';
  try{
    const d=await api({ledger_targets:1,only_debit:$('#lbOnlyDebit').checked?1:'',
      min:$('#lbMin').value||0,
      issue_date_from:isoToDmy($('#lbFrom').value)||yearStart(),
      issue_date_to:isoToDmy($('#lbTo').value)||todayDmy()});
    if(!d.success)throw new Error(d.error||'απέτυχε');
    LB_ROWS=d.rows||[];
    lbRender();
    const withMail=LB_ROWS.filter(r=>r.email).length;
    $('#lbResult').textContent=LB_ROWS.length+' πελάτες · '+withMail+' με email';
  }catch(e){$('#lbResult').textContent='Φόρτωση: '+e.message;}
}

// Οι διευθύνσεις που λείπουν, μία-μία από την ΑΑΔΕ. Είναι αργό (ένα αίτημα ανά
// πελάτη) γι' αυτό γίνεται με ρητό πάτημα και όχι αυτόματα στο άνοιγμα.
async function lbFindEmails(){
  const missing=LB_ROWS.map((r,i)=>({r,i})).filter(x=>!x.r.email);
  if(!missing.length){toast('Όλοι έχουν ήδη email','ok');return;}
  for(let k=0;k<missing.length;k++){
    const {r,i}=missing[k];
    $('#lbResult').innerHTML='<span class="spin"></span> Εύρεση '+(k+1)+'/'+missing.length+' — '+esc(r.name||r.vat);
    try{const d=await api({customer_email:1,buyer_vat:r.vat});if(d&&d.email)LB_ROWS[i].email=d.email;}catch(e){}
  }
  lbRender();
  const withMail=LB_ROWS.filter(r=>r.email).length;
  $('#lbResult').textContent=LB_ROWS.length+' πελάτες · '+withMail+' με email';
}

function lbRender(){
  $('#lbTable tbody').innerHTML=LB_ROWS.map((r,i)=>`<tr>
      <td style="text-align:center"><input type="checkbox" class="lb-pick" data-i="${i}"${r.email?' checked':''}></td>
      <td>${esc(r.name||r.vat)}</td><td>${esc(r.vat)}</td>
      <td class="right">${fmt(r.balance)}</td>
      <td>${r.email?esc(r.email):'<span class="muted">— χωρίς email —</span>'}</td>
    </tr>`).join('')||'<tr><td colspan="5" class="muted">Κανένας πελάτης με αυτά τα κριτήρια.</td></tr>';
}

async function lbSend(){
  const picks=$$('#lbTable .lb-pick:checked').map(c=>LB_ROWS[+c.dataset.i]).filter(r=>r&&r.email);
  if(!picks.length){toast('Δεν επιλέχθηκε κανείς με email','err');return;}
  if(!confirm('Να σταλούν '+picks.length+' καρτέλες;'))return;
  const period=(isoToDmy($('#lbFrom').value)||yearStart())+' – '+(isoToDmy($('#lbTo').value)||todayDmy());
  let ok=0,fail=0;
  for(let i=0;i<picks.length;i++){
    const r=picks[i];
    $('#lbResult').innerHTML='<span class="spin"></span> '+(i+1)+'/'+picks.length+' — '+esc(r.name||r.vat);
    try{
      const b64=await ledgerPdfB64(r,period);
      const body=cardMailBody({name:r.name||r.vat,period,balance:r.balance});
      const d=await apostAcc({email_document:1,kind:'card',to:r.email,customer_vat:r.vat,
        subject:'Καρτέλα πελάτη — '+(r.name||r.vat),body,
        pdf_base64:b64,pdf_name:ledgerFileName(r.name,r.vat),
        attach_bank:r.balance>0.005?1:''});
      if(d.success)ok++;else fail++;
    }catch(e){fail++;}
  }
  $('#lbResult').textContent='Στάλθηκαν '+ok+(fail?(' · απέτυχαν '+fail):'')+'.';
  toast('Στάλθηκαν '+ok+' καρτέλες'+(fail?(', απέτυχαν '+fail):''),fail?'err':'ok');
}

// Το κείμενο της καρτέλας, με τις ίδιες λέξεις που χρησιμοποιεί ο server:
// «προς πληρωμή» ή «πιστωτικό», ποτέ σκέτο πρόσημο.
function cardMailBody(info){
  const bal=+info.balance||0;
  const label=bal>0.005?'υπόλοιπο προς πληρωμή':bal<-0.005?'πιστωτικό υπόλοιπο':'μηδενικό υπόλοιπο';
  const company=($('#account option:checked')||{}).textContent||'';
  let t=(info.name||'αγαπητέ συνεργάτη')+',\n\nσας αποστέλλουμε συνημμένη την καρτέλα κινήσεων'+
    (info.period?(' για το διάστημα '+info.period):'')+'.'+
    '\n\n'+(Math.abs(bal)<0.005?'το υπόλοιπό σας είναι μηδενικό — δεν εκκρεμεί πληρωμή.':('το τρέχον '+label+' είναι '+fmt(Math.abs(bal))+' €.'));
  if(bal>0.005)t+=bankLinesText();
  if(company)t+='\n\nμε εκτίμηση,\n'+company;
  return t;
}

// Όνομα αρχείου από επωνυμία: ό,τι δεν επιτρέπει το σύστημα αρχείων φεύγει.
// Τα Windows απορρίπτουν \ / : * ? " < > | και τα κενά στο τέλος.
function safeFileName(text,fallback){
  const t=String(text||'').replace(/[\\/:*?"<>|]/g,' ').replace(/\s+/g,' ').trim();
  return t?t.slice(0,80):(fallback||'');
}
// «ΚΑΡΤΕΛΑ (ΕΠΩΝΥΜΙΑ ΠΕΛΑΤΗ).pdf» — το ΑΦΜ δεν λέει σε κανέναν ποιανού είναι
// η καρτέλα όταν κοιτάς τον φάκελο λήψεων.
function ledgerFileName(name,vat){
  const who=safeFileName(name,'')||String(vat||'');
  return 'ΚΑΡΤΕΛΑ ('+(who||'ΠΕΛΑΤΗΣ')+').pdf';
}

// Command palette
let palTimer,palSel=-1,palRows=[];
function openPalette(){$('#palette').classList.add('open');$('#palInput').value='';$('#palResults').innerHTML='';palSel=-1;setTimeout(()=>$('#palInput').focus(),30);}
function closePalette(){$('#palette').classList.remove('open');}
$('#palette').addEventListener('click',e=>{if(e.target.id==='palette')closePalette();});
$('#palInput').addEventListener('input',()=>{clearTimeout(palTimer);palTimer=setTimeout(palSearch,300);});
$('#palInput').addEventListener('keydown',e=>{
  if(e.key==='Escape')closePalette();
  else if(e.key==='ArrowDown'){palSel=Math.min(palSel+1,palRows.length-1);palHi();e.preventDefault();}
  else if(e.key==='ArrowUp'){palSel=Math.max(palSel-1,0);palHi();e.preventDefault();}
  else if(e.key==='Enter'){const r=palRows[palSel]||palRows[0];if(r){closePalette();openCard(r.vat,r.name);}}
});
function palHi(){document.querySelectorAll('.pal-row').forEach((x,i)=>x.classList.toggle('sel',i===palSel));}
async function palSearch(){const term=$('#palInput').value.trim();if(!term){$('#palResults').innerHTML='';palRows=[];return;}
  const p={list_customers:1};if(/^\d{6,}$/.test(term))p.afm=term;else p.customer_name=term;
  try{const d=await api(p);palRows=(d.customers||[]).slice(0,12).map(c=>({vat:c.vat||c.customer_vat||'',name:c.name||c.customer_name||'',city:c.city||''}));
    $('#palResults').innerHTML=palRows.map((r,i)=>`<div class="pal-row" onclick="closePalette();openCard('${q1(r.vat)}','${q1(r.name)}')"><span>👤</span><div><div>${esc(r.name)}</div><small>ΑΦΜ ${esc(r.vat)} · ${esc(r.city)}</small></div></div>`).join('')||'<div class="pal-row muted">Κανένα αποτέλεσμα</div>';palSel=0;palHi();
  }catch(e){$('#palResults').innerHTML='<div class="pal-row">'+esc(e.message)+'</div>';}}
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();openPalette();}});

// ====== Voice assistant / chatbot (Web Speech API, no dependency) ============
// Controlled operation: parses Greek/English commands for issuing a document,
// creating a customer, or creating a product — and ALWAYS produces a preview /
// draft for manual review (never auto-issues live). Also answers navigation/help.
let cbRec=null,cbRecOn=false;
function cbPanelOpen(){const p=$('#cbPanel');return !!(p&&p.classList.contains('open'));}
// Κλείνοντας το παράθυρο, ο βοηθός σωπαίνει ΑΜΕΣΩΣ: ήχος που συνεχίζει αφού
// έφυγες από τη συνομιλία ακούγεται σαν να μιλά μόνος του.
function cbSilence(){
  try{if(CB_AUDIO){CB_AUDIO.pause();CB_AUDIO.currentTime=0;CB_AUDIO=null;}}catch(e){}
  try{if(window.speechSynthesis)speechSynthesis.cancel();}catch(e){}
}
function cbTogglePanel(){const p=$('#cbPanel');p.classList.toggle('open');
  if(!p.classList.contains('open')){
    cbSilence();
    // Και το μικρόφωνο: μια ηχογράφηση που συνεχίζει με κλειστό παράθυρο δεν
    // έχει πού να καταλήξει, και ανάβει το λαμπάκι της κάμερας/μικροφώνου.
    if(cbRecOn){try{cbStopLocalRec();}catch(e){}try{if(cbRec)cbRec.stop();}catch(e){}}
    return;
  }
  {$('#cbInput').focus();cbWarmVoice();if(!$('#cbLog').children.length)cbBot('Γεια! Πες μου π.χ. «έκδοση τιμολογίου στον 802012659 για 2 τεμ κωδ 10 ευρώ», «νέος πελάτης», «νέο είδος», «νέα σειρά», ή «πήγαινε στην καρτέλα». Αποθηκεύω πάντα ΠΡΟΧΕΙΡΟ — ΜΑΡΚ παίρνει το παραστατικό μόνο όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση».');}}
function cbClear(){$('#cbLog').innerHTML='';}
function cbAdd(text,who,actionsHtml){const log=$('#cbLog');const d=document.createElement('div');d.className='cbMsg '+who;d.innerHTML=esc(text).replace(/\n/g,'<br>')+(actionsHtml||'');log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function cbMe(t){cbAdd(t,'me');}
function cbBot(t,actions){cbAdd(t,'bot',actions);cbSpeak(t);}
// Ο βοηθός διάβαζε ΓΡΑΜΜΑ-ΓΡΑΜΜΑ: με σκέτο `u.lang='el-GR'` ο browser δεν
// επιλέγει ελληνική φωνή — παίρνει την προεπιλεγμένη (αγγλική) και εκείνη
// συλλαβίζει τους άγνωστους χαρακτήρες. Η φωνή πρέπει να δοθεί ΡΗΤΑ.
let CB_VOICE=null, CB_VOICE_WARNED=false;
function cbPickVoice(lang){
  const want=(lang||'el-GR').toLowerCase().slice(0,2);
  const voices=speechSynthesis.getVoices()||[];
  return voices.find(v=>(v.lang||'').toLowerCase().startsWith(want))||null;
}
// Η φωνή έρχεται από ΤΟΝ SERVER ΜΑΣ (Piper, εκτός δικτύου): τα Windows δεν
// έχουν ελληνική φωνή από προεπιλογή, οπότε το `speechSynthesis` είτε σωπαίνει
// είτε συλλαβίζει τα ελληνικά με αγγλική φωνή. Ο browser μένει ως εφεδρεία για
// εγκαταστάσεις server χωρίς τη μηχανή (τότε το endpoint απαντά 501).
// `CB_TTS_OFF` σημαίνει «δεν υπάρχει φωνή σε αυτή την εγκατάσταση»· το
// `CB_MUTED` σημαίνει «υπάρχει, αλλά ο χρήστης είπε σώπα». Δύο διαφορετικά
// πράγματα: το πρώτο δεν ξεκλειδώνει ποτέ, το δεύτερο με μία λέξη.
let CB_AUDIO=null, CB_TTS_OFF=false, CB_WARMED=false, CB_MUTED=false;
// Προθέρμανση: η πρώτη σύνθεση φορτώνει το μοντέλο και «τρώει» τις πρώτες
// λέξεις — ο χρήστης το ακούει σαν να μπερδεύεται ο βοηθός. Μία άφωνη κλήση
// μόλις ανοίξει το panel και το πρόβλημα φεύγει.
function cbWarmVoice(){
  if(CB_WARMED)return;CB_WARMED=true;
  const lang=($('#cbLang').value||'el-GR').slice(0,2);
  // Πρώτα ΤΙ υπάρχει, μετά προθέρμανση. Χωρίς αυτό, ο χρήστης του web
  // ηχογραφούσε ολόκληρη πρόταση για να πάρει 501 στο τέλος.
  fetch(API+'?voice_caps=1'+(ACCOUNT?('&account='+encodeURIComponent(ACCOUNT)):''))
    .then(r=>r.json()).then(d=>{
      CB_TTS_OFF=!d.tts;CB_STT_OFF=!d.stt;
      cbMicHint();
      if(d.tts)fetch(API+'?tts=1&warmup=1&lang='+encodeURIComponent(lang)+(ACCOUNT?('&account='+encodeURIComponent(ACCOUNT)):'')).catch(()=>{});
    }).catch(()=>{CB_TTS_OFF=true;CB_STT_OFF=true;cbMicHint();});
}
// Το κουμπί του μικροφώνου λέει ΤΙ θα γίνει αν το πατήσεις.
function cbMicHint(){
  const mic=$('#cbMic');if(!mic)return;
  const browserSR=!cbEmbedded()&&!!(window.SpeechRecognition||window.webkitSpeechRecognition);
  const ok=!CB_STT_OFF||browserSR;
  mic.disabled=!ok;
  mic.style.opacity=ok?'':'.45';
  mic.title=!CB_STT_OFF
    ? 'Φωνητική εντολή — αναγνώριση σε αυτόν τον υπολογιστή, εκτός δικτύου'
    : browserSR
      ? 'Φωνητική εντολή μέσω του browser (χρειάζεται σύνδεση στο internet)'
      : 'Δεν υπάρχει φωνητική αναγνώριση σε αυτή την εγκατάσταση — γράψε την εντολή';
}
function cbSpeak(t){
  // Ο βοηθός μιλά ΜΟΝΟ με ανοιχτό παράθυρο. Μια απάντηση που άργησε (π.χ.
  // αναγνώριση φωνής) δεν πρέπει να ξεκινήσει να μιλά αφού έκλεισες.
  if(!cbPanelOpen())return;
  if(CB_MUTED)return;
  const lang=($('#cbLang').value||'el-GR').slice(0,2);
  const text=t.replace(/[•✔🔇➕📤💾👁⏰💶🧾🚚🏢👤]/gu,'').trim();
  if(!text)return;
  if(!CB_TTS_OFF){
    try{
      if(CB_AUDIO){CB_AUDIO.pause();CB_AUDIO=null;}
      const url=API+'?tts=1&lang='+encodeURIComponent(lang)+'&text='+encodeURIComponent(text.slice(0,600))
        +(ACCOUNT?('&account='+encodeURIComponent(ACCOUNT)):'');
      CB_AUDIO=new Audio(url);
      CB_AUDIO.onerror=()=>{CB_TTS_OFF=true;cbSpeakBrowser(text,lang);};
      CB_AUDIO.play().catch(()=>{CB_TTS_OFF=true;cbSpeakBrowser(text,lang);});
      return;
    }catch(e){CB_TTS_OFF=true;}
  }
  cbSpeakBrowser(text,lang);
}
function cbSpeakBrowser(text,lang){try{
  if(!window.speechSynthesis)return;
  const voice=cbPickVoice(lang);
  if(!voice){
    if(!CB_VOICE_WARNED&&want_greek(lang)){CB_VOICE_WARNED=true;
      cbAdd('🔇 Δεν υπάρχει ελληνική φωνή σε αυτή την εγκατάσταση, οπότε απαντώ μόνο γραπτά.','bot');}
    return;
  }
  const u=new SpeechSynthesisUtterance(text);
  u.voice=voice;u.lang=voice.lang;u.rate=1.0;
  speechSynthesis.cancel();speechSynthesis.speak(u);
}catch(e){}}
function want_greek(lang){return (lang||'').toLowerCase().startsWith('el');}
// Οι φωνές φορτώνονται ασύγχρονα — χωρίς αυτό, η πρώτη απάντηση βρίσκει κενή λίστα.
if(window.speechSynthesis)speechSynthesis.onvoiceschanged=()=>{CB_VOICE=cbPickVoice($('#cbLang').value);};
function cbSubmitText(){const t=$('#cbInput').value.trim();if(!t)return;$('#cbInput').value='';cbMe(t);cbHandle(t);}
// --- Φωνητική εντολή ---------------------------------------------------------
//
// ⚠️ ΠΟΤΕ `webkitSpeechRecognition` μέσα στην εφαρμογή υπολογιστή. Το QtWebEngine
// το εκθέτει, αλλά πίσω του δεν υπάρχει η υπηρεσία της Google: το `start()`
// περιμένει απάντηση που δεν έρχεται ποτέ και **παγώνει ολόκληρη την εφαρμογή**.
// (Ο χρήστης το ανέφερε ακριβώς έτσι: «πατάω να μιλήσω και κολλάει».)
//
// Η μόνιμη λύση είναι η ίδια που δόθηκε και για τη φωνή: αναγνώριση **δική μας**,
// εκτός δικτύου. Ηχογραφούμε εδώ, φτιάχνουμε 16 kHz mono WAV (αυτό ακριβώς
// θέλει η μηχανή), και το στέλνουμε στο `?stt=1` του backend μας, που τρέχει
// whisper.cpp τοπικά. Ίδιος δρόμος για browser και για εφαρμογή υπολογιστή·
// όπου δεν υπάρχει μηχανή, το endpoint απαντά 501 και πέφτουμε στον browser.
let CB_MEDIA=null,CB_CHUNKS=[],CB_CTXA=null,CB_STT_OFF=false;
const cbEmbedded=isEmbedded;   // ίδιος έλεγχος, παλιό όνομα στον βοηθό
function cbInitRec(){
  if(cbEmbedded())return null;                 // βλ. παραπάνω — παγώνει
  const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return null;
  const r=new SR();r.interimResults=false;r.maxAlternatives=1;
  r.onresult=e=>{const t=e.results[0][0].transcript;$('#cbInput').value=t;cbSubmitText();};
  r.onend=()=>{cbRecOn=false;$('#cbMic').classList.remove('rec');};
  r.onerror=()=>{cbRecOn=false;$('#cbMic').classList.remove('rec');};return r;}
function cbToggleMic(){
  if(cbRecOn){cbStopLocalRec();if(cbRec){try{cbRec.stop();}catch(e){}}return;}
  if(!CB_STT_OFF){cbStartLocalRec();return;}
  if(!cbRec)cbRec=cbInitRec();
  if(!cbRec){
    cbBot(cbEmbedded()
      ? 'Η αναγνώριση φωνής δεν είναι εγκατεστημένη σε αυτόν τον υπολογιστή. Γράψε την εντολή εδώ.'
      : 'Αυτός ο browser δεν έχει φωνητική αναγνώριση. Δοκίμασε Chrome ή Edge, ή γράψε την εντολή εδώ.');
    return;}
  cbRec.lang=$('#cbLang').value;try{cbRec.start();cbRecOn=true;$('#cbMic').classList.add('rec');}catch(e){}}
async function cbStartLocalRec(){
  let stream;
  try{stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,noiseSuppression:true,echoCancellation:true}});}
  catch(e){CB_STT_OFF=true;cbBot('Δεν δόθηκε πρόσβαση στο μικρόφωνο. Γράψε την εντολή εδώ.');return;}
  CB_CTXA=new (window.AudioContext||window.webkitAudioContext)();
  const src=CB_CTXA.createMediaStreamSource(stream);
  // ScriptProcessor και όχι AudioWorklet: το worklet θέλει ξεχωριστό αρχείο
  // module, που δεν φορτώνεται σε offline εγκατάσταση χωρίς επιπλέον διαδρομή.
  const node=CB_CTXA.createScriptProcessor(4096,1,1);
  CB_CHUNKS=[];
  node.onaudioprocess=e=>{CB_CHUNKS.push(new Float32Array(e.inputBuffer.getChannelData(0)));};
  src.connect(node);node.connect(CB_CTXA.destination);
  CB_MEDIA={stream,src,node,rate:CB_CTXA.sampleRate};
  cbRecOn=true;$('#cbMic').classList.add('rec');
  cbAdd('🎙 Ακούω… πάτα ξανά το μικρόφωνο όταν τελειώσεις.','bot');
  // Δικλείδα: μια ξεχασμένη ηχογράφηση δεν πρέπει να τρέχει για πάντα.
  clearTimeout(CB_MEDIA._t);CB_MEDIA._t=setTimeout(()=>{if(cbRecOn)cbStopLocalRec();},20000);
}
async function cbStopLocalRec(){
  const m=CB_MEDIA;CB_MEDIA=null;cbRecOn=false;$('#cbMic').classList.remove('rec');
  if(!m)return;
  clearTimeout(m._t);
  try{m.node.disconnect();m.src.disconnect();m.stream.getTracks().forEach(t=>t.stop());}catch(e){}
  const wav=pcmToWav(CB_CHUNKS,m.rate,16000);CB_CHUNKS=[];
  try{if(CB_CTXA)await CB_CTXA.close();}catch(e){}
  CB_CTXA=null;
  if(!wav){cbBot('Δεν ηχογραφήθηκε τίποτα.');return;}
  cbAdd('⏳ Αναγνώριση…','bot');
  try{
    const fd=new FormData();fd.append('audio',new Blob([wav],{type:'audio/wav'}),'cmd.wav');
    fd.append('stt','1');fd.append('lang',($('#cbLang').value||'el').slice(0,2));
    if(ACCOUNT)fd.append('account',ACCOUNT);
    const r=await fetch(API,{method:'POST',body:fd});
    const d=await r.json();
    if(r.status===501){CB_STT_OFF=true;cbMicHint();
      cbBot('Η τοπική αναγνώριση φωνής δεν είναι εγκατεστημένη. Δοκίμασε ξανά το μικρόφωνο — θα χρησιμοποιήσω τον browser.');return;}
    if(!d.success||!(d.text||'').trim()){cbBot('Δεν κατάλαβα τι είπες — δοκίμασε ξανά ή γράψε το.');return;}
    $('#cbInput').value=d.text.trim();cbSubmitText();
  }catch(e){cbBot('Η αναγνώριση απέτυχε: '+e.message);}
}
// Float32 δείγματα → 16-bit PCM WAV στη ζητούμενη συχνότητα. Η μηχανή δέχεται
// ΜΟΝΟ 16 kHz mono· χωρίς τη μετατροπή εδώ θα χρειαζόταν ffmpeg στο bundle.
function pcmToWav(chunks,fromRate,toRate){
  let total=0;chunks.forEach(c=>total+=c.length);
  if(total<fromRate/4)return null;                  // < 0,25 δευτ. = παρατράβηγμα
  const all=new Float32Array(total);let o=0;chunks.forEach(c=>{all.set(c,o);o+=c.length;});
  const ratio=fromRate/toRate,outLen=Math.floor(total/ratio);
  const out=new Int16Array(outLen);
  for(let i=0;i<outLen;i++){
    // Μέσος όρος του παραθύρου: απλό anti-aliasing, αρκετό για φωνή.
    const start=Math.floor(i*ratio),end=Math.min(total,Math.floor((i+1)*ratio));
    let sum=0,n=0;for(let j=start;j<end;j++){sum+=all[j];n++;}
    const v=n?sum/n:0;
    out[i]=Math.max(-1,Math.min(1,v))*0x7fff;
  }
  const buf=new ArrayBuffer(44+out.length*2),view=new DataView(buf);
  const str=(off,s)=>{for(let i=0;i<s.length;i++)view.setUint8(off+i,s.charCodeAt(i));};
  str(0,'RIFF');view.setUint32(4,36+out.length*2,true);str(8,'WAVEfmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,toRate,true);view.setUint32(28,toRate*2,true);
  view.setUint16(32,2,true);view.setUint16(34,16,true);
  str(36,'data');view.setUint32(40,out.length*2,true);
  new Int16Array(buf,44).set(out);
  return buf;
}
// Helpers
function cbNum(re,t){const m=t.match(re);return m?parseFloat(m[1].replace(',','.')):null;}
function cbFindProd(s){for(const c in PRODMAP){const dsc=(PRODMAP[c].desc||'').toLowerCase();if(dsc.length>=4&&s.includes(dsc.slice(0,Math.min(8,dsc.length))))return c;}return '';}
// Intent router
let CB_CTX=null; // pending multi-step flow (e.g. resolving an unknown customer)
// --- Ψηφιακός βοηθός: κανονικοποίηση + δηλωτικός πίνακας προθέσεων ------------
// Γιατί όχι έτοιμη βιβλιοθήκη NLU (NLP.js, Transformers.js): θα πρόσθεταν
// megabytes και εξάρτηση από CDN ή κατεβασμένο μοντέλο — ασύμβατο με το offline
// desktop και με self-hosted εγκατάσταση. Το λεξιλόγιο εδώ είναι μικρό και
// σταθερό (ρήματα τιμολόγησης), οπότε ένας κανονικοποιημένος πίνακας κανόνων
// είναι και ακριβέστερος και μηδενικού κόστους.

// Πεζά + αφαίρεση τόνων/διαλυτικών, ώστε «καρτέλα», «ΚΑΡΤΕΛΑ» και «καρτελα» να
// είναι το ίδιο πράγμα — παλιά κάθε λέξη έμπαινε δύο φορές στους πίνακες.
function cbNorm(s){return (s||'').toLowerCase()
  .replace(/[άὰᾶα̈]/g,'α').replace(/[έὲ]/g,'ε').replace(/[ήὴῆ]/g,'η')
  .replace(/[ίὶῖϊΐ]/g,'ι').replace(/[όὸ]/g,'ο').replace(/[ύὺῦϋΰ]/g,'υ').replace(/[ώὼῶ]/g,'ω')
  .replace(/ς/g,'σ');}

// Ενότητα → λέξεις-κλειδιά (κανονικοποιημένες, χωρίς τόνους).
const CB_NAV=[
  ['issue',        ['εκδοση','εκδοσ','νεο παραστατικο','τιμολογηση']],
  // Τα εκδοθέντα παραστατικά έχουν πλέον **δική τους** ενότητα (όλο το έτος, με
  // μαζική εκτύπωση/ZIP), όπως και στην εφαρμογή υπολογιστή.
  ['documents',    ['παραστατικα','τιμολογια μου','λιστα παραστατικων','αναζητηση παραστατικ','αρχειο παραστατικων']],
  ['bulk',         ['μαζικη εκδοση','μαζικ','παρτιδ']],
  ['customers',    ['πελατ','πελατολογ']],
  ['card',         ['καρτελ','υπολοιπ','κινησεισ πελατ']],
  ['bankimp',      ['τραπεζ','extrait','εξτρε','εισαγωγη πληρωμ','πληρωμ','εισπραξ','ταμει']],
  ['products',     ['ειδη','ειδοσ','προιοντ','καταλογοσ ειδων','υπηρεσιε']],
  ['series',       ['σειρ','αριθμηση']],
  ['drafts',       ['προχειρ','προσχεδ']],
  ['cancel',       ['ακυρωσ','πιστωτικ']],
  ['schedule',     ['προγραμματισμ','χρονοπρογραμμ','αυτοματη εκδοσ']],
  ['stats',        ['στατιστικ','τζιρο','γραφημ','πιτα']],
  ['settings',     ['ρυθμισ','2fa','κωδικο','authenticator','email']],
  ['admin',        ['διαχειρισ','χρηστ','ρολο','προσκλησ','λογιστ','εταιρει','επιχειρησ']],
];

//: Ονόματα ενοτήτων για τα μηνύματα («Δεν το κατάλαβα, μήπως εννοείς…»).
const CB_VIEW_NAMES={issue:'Έκδοση',bulk:'Μαζική έκδοση',customers:'Πελάτες',card:'Καρτέλα',
  documents:'Παραστατικά',bankimp:'Εισαγωγή πληρωμών',products:'Είδη',series:'Σειρές',
  drafts:'Πρόχειρα',cancel:'Ακύρωση/Πιστωτικό',schedule:'Προγραμματισμός',stats:'Στατιστικά',
  settings:'Ρυθμίσεις',admin:'Διαχείριση'};
// Απόσταση Levenshtein — μικρή και αρκετή για μία λέξη. Χωρίς αυτήν, ένα
// «πελατεσ» γραμμένο «πελατσε» (ή μια λέξη που άκουσε λάθος η αναγνώριση
// φωνής) έπεφτε στο «δεν το κατάλαβα».
function cbDist(a,b){
  if(a===b)return 0;
  const m=a.length,n=b.length;
  if(!m||!n)return m||n;
  let prev=Array.from({length:n+1},(_,j)=>j),cur=new Array(n+1);
  for(let i=1;i<=m;i++){cur[0]=i;
    for(let j=1;j<=n;j++){
      cur[j]=Math.min(prev[j]+1,cur[j-1]+1,prev[j-1]+(a[i-1]===b[j-1]?0:1));}
    [prev,cur]=[cur,prev];}
  return prev[n];
}
// Η ενότητα που ταιριάζει σε μια φράση: πρώτα ακριβές ταίριασμα λέξης-κλειδιού,
// μετά ανεκτικό σε ένα τυπογραφικό. Επιστρέφει '' όταν δεν είναι σίγουρο.
function cbMatchView(s){
  for(const[view,keys]of CB_NAV){if(keys.some(k=>s.includes(k)))return view;}
  const words=s.split(/\s+/).filter(w=>w.length>=5);
  for(const[view,keys]of CB_NAV){
    for(const k of keys){
      if(k.length<5)continue;
      for(const w of words){
        // Ένα λάθος γράμμα σε λέξη ≥5 χαρακτήρων· παραπάνω θα μάντευε.
        if(Math.abs(w.length-k.length)<=2&&cbDist(w,k)<=1)return view;
      }
    }
  }
  return '';
}

async function cbHandle(t){const s=cbNorm(t);
  // Πάντα διαθέσιμη έξοδος: χωρίς αυτό, μια ημιτελής ροή «κρατούσε» τον βοηθό
  // και κάθε επόμενη εντολή καταναλωνόταν ως απάντηση σε παλιά ερώτηση.
  if(/^(ακυρο|ακυρωση|σταματα|ξεχνα το|cancel|stop)$/.test(s.trim())){
    if(CB_CTX){CB_CTX=null;cbBot('Εντάξει, το ακύρωσα.');}else cbBot('Δεν εκκρεμεί κάτι.');return;}
  if(CB_CTX)return cbContinue(t);              // we're mid-conversation

  // --- Διευρυμένος χειρισμός: εντολές που αλλάζουν την ΕΦΑΡΜΟΓΗ, όχι τη σελίδα -
  // Ίδιες λέξεις με την εφαρμογή υπολογιστή (`assistant.COMMANDS`): ο λογιστής
  // που έμαθε «σώπα» ή «άλλαξε εταιρεία» στο ένα, το λέει και στο άλλο.
  // ΠΡΙΝ την πλοήγηση: το «καρτέλα του 802576637» δεν είναι «άνοιξε την Καρτέλα»
  // — ο αριθμός είναι όλη η εντολή, και αλλιώς χανόταν.
  const vatSaid=(s.match(/\b(\d{9})\b/)||[])[1]||'';
  // «φτιάξε καρτέλα για τον Χ» είναι ΝΕΟΣ πελάτης, όχι άνοιγμα καρτέλας: ίδια
  // λέξη, αντίθετη ενέργεια — το ρήμα αποφασίζει.
  const makesNew=/\bνεοσ?\b|\bνεα\b|\bνεο\b|φτιαξε|δημιουργησε|καταχωρησε|προσθεσε/.test(s);
  if(vatSaid&&!makesNew&&(/καρτελ/.test(s)||/χρωσταει|υπολοιπο/.test(s))){
    if(!ALL_CUSTOMERS.length)await loadCustomers();
    const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===vatSaid);
    openCard(vatSaid,c&&c.name);cbBot('Άνοιξα την καρτέλα του πελάτη.');return;}
  if(vatSaid&&/εταιρει|επιχειρησ/.test(s)){
    const sel=$('#account');
    if(sel&&Array.from(sel.options).some(o=>o.value===vatSaid)){
      sel.value=vatSaid;ACCOUNT=vatSaid;loadProductList();
      const nav=document.querySelector('.nav-item.active');if(nav)showView(nav.dataset.view);
      cbBot('Άλλαξα ενεργή εταιρεία.');
    }else cbBot('Δεν βρήκα εταιρεία με αυτό το ΑΦΜ στη λίστα σου.');
    return;}
  if(/σωπα|μη μιλασ|σταματα να μιλασ|\bmute\b/.test(s)){
    CB_MUTED=true;
    // Σιωπή σημαίνει ΤΩΡΑ — όχι «μετά την πρόταση που ήδη ακούγεται».
    if(CB_AUDIO){CB_AUDIO.pause();CB_AUDIO=null;}
    if(window.speechSynthesis)speechSynthesis.cancel();
    cbAdd('Εντάξει, απαντώ μόνο γραπτά.','bot');return;}
  if(/μιλα μου|ξαναμιλα|ενεργοποιησε τη φωνη|\bunmute\b/.test(s)){
    CB_MUTED=false;cbBot('Εντάξει, ξαναμιλάω.');return;}
  if(/εγχειριδι|manual|οδηγιεσ χρησ/.test(s)){
    cbBot('Ετοιμάζω το εγχειρίδιο χρήσης σε PDF.');downloadManual();return;}
  if(/αντιγραφο ασφαλει|backup|κρατα αντιγραφο/.test(s)){
    cbBot('Το αντίγραφο ασφαλείας γίνεται από την εφαρμογή υπολογιστή '+
      '(Πίνακας ελέγχου → «Αντίγραφο τώρα»), όχι από τον browser.');return;}
  if(/ανανεωσ|ξαναφορτωσ|refresh|φρεσκαρε/.test(s)){
    const nav=document.querySelector('.nav-item.active');
    if(nav)showView(nav.dataset.view);
    cbBot('Ανανέωσα τη σελίδα.');return;}
  if(/αποσυνδεσ|logout/.test(s)){cbBot('Σε αποσυνδέω.');logout();return;}
  // Πλήθη: τα έχουμε ήδη στη μνήμη — καμία ερώτηση στο backend, και ΠΡΙΝ τα
  // στατιστικά, που μετρούν παραστατικά και όχι πελάτες.
  if(/ποσ\S*\s+πελατ/.test(s)){
    if(!ALL_CUSTOMERS.length)await loadCustomers();
    cbBot('Έχεις '+ALL_CUSTOMERS.length+' πελάτες στο πελατολόγιο.');return;}
  if(/ποσ\S*\s+(?:ειδ|προιοντ)/.test(s)){
    if(!PRODUCTS.length)await loadProducts();
    cbBot('Έχεις '+PRODUCTS.length+' είδη στον κατάλογο.');return;}

  // Ρητή πλοήγηση ΠΡΩΤΑ: το «πήγαινε στα παραστατικά» περιέχει «παραστατ» και
  // αλλιώς θα περνούσε λανθασμένα για εντολή έκδοσης.
  const isNav=/πηγαινε|ανοιξε|go to|open|δειξε|εμφανισε|παμε/.test(s);
  if(isNav){
    const view=cbMatchView(s);
    if(view){showView(view);cbBot('Άνοιξα: '+(CB_VIEW_NAMES[view]||view)+'.');return;}
  }
  const isIssue=!isNav&&/εκδοσ|τιμολογ|αποδειξ|παραστατ|issue|invoice/.test(s)&&!/λιστα|αναζητησ|ολα τα/.test(s);
  // Help
  if(/βοηθεια|help|τι μπορεισ|τι κανεισ|οδηγιεσ/.test(s)){
    cbBot('Μπορώ (πάντα ως ΠΡΟΧΕΙΡΟ — καμία οριστική έκδοση/ΜΑΡΚ χωρίς εσένα):\n'+
      '📄 Έκδοση: «έκδοση τιμολογίου στην <επωνυμία ή ΑΦΜ> καθαρή αξία <ποσό> με παρακράτηση <%> είδος <περιγραφή>»\n'+
      '👥 Δεδομένα: «νέος πελάτης <ΑΦΜ>» · «νέο είδος <περιγραφή> <τιμή> ευρώ» · «νέα σειρά»\n'+
      '🖨️ Εκτυπώσεις: «μαζική εκτύπωση παραστατικών» · «ZIP παραστατικών» · «PDF καρτέλας»\n'+
      '💶 Ταμείο: «εισαγωγή πληρωμών από τράπεζα» · «πληρωμές»\n'+
      '⏰ Αυτοματισμοί: «προγραμματισμός» · «ειδοποιήσεις» · «πόσες αδιάβαστες»\n'+
      '⚙️ Λογαριασμός: «ρυθμίσεις» · «ενεργοποίηση 2FA» · «αλλαγή κωδικού» · «διαχείριση χρηστών»\n'+
      '🛠️ Εφαρμογή: «εγχειρίδιο» · «άλλαξε εταιρεία <ΑΦΜ>» · «καρτέλα του <ΑΦΜ>» · «ανανέωσε» · «σώπα» · «αποσύνδεση»\n'+
      '📊 Ερωτήσεις: «πόσα τιμολόγια φέτος» · «τζίρος μήνα» · «πόσους πελάτες έχω»\n'+
      '🧭 Πλοήγηση: «πήγαινε στην καρτέλα / πελάτες / είδη / σειρές / πρόχειρα…»\n\n'+
      'ℹ️ Το παραστατικό παίρνει ΜΑΡΚ μόνο όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση».');return;}
  // New series
  if(/νεα σειρα|new series|δημιουργησε σειρα|φτιαξε σειρα/.test(s)){
    showView('series');cbBot('Άνοιξα τη διαχείριση Σειρών. Διάλεξε τύπο παραστατικού, δώσε κωδικό σειράς (π.χ. Α, ΤΠΥ, ΔΑ) και πάτα «Δημιουργία σειράς».');return;}
  // Μαζική εκτύπωση / ZIP — δουλεύουν και στο web και στον thin client.
  if(/μαζικη εκτυπωσ|εκτυπωσε ολα|τυπωσε τα παραστατικ|print all/.test(s)){
    if(window.CARD_INVOICES&&window.CARD_INVOICES.length){cbBot('Ετοιμάζω προεπισκόπηση εκτύπωσης…');printCustomerInvoices();}
    else{showView('card');cbBot('Φόρτωσε πρώτα την καρτέλα ενός πελάτη και μετά πάτα «🖨️ Μαζική εκτύπωση».');}
    return;}
  if(/\bzip\b|συμπιεσ|πακετ|κατεβασε ολα/.test(s)){
    const vat=($('#cardVat')&&$('#cardVat').value||'').trim();
    if(vat){cbBot('Κατεβάζω ZIP με τα παραστατικά του πελάτη…');zipCustomerInvoices();}
    else{showView('card');cbBot('Διάλεξε πελάτη στην Καρτέλα και μετά «🗜️ ZIP παραστατικών».');}
    return;}
  // Ειδοποιήσεις
  if(/ειδοποιησ|αδιαβαστ|notification/.test(s)){
    try{const d=await api({notif_count:1});cbBot('Έχεις '+(d.unread||0)+' αδιάβαστες ειδοποιήσεις.');toggleNotifPanel();}
    catch(e){cbBot('Δεν μπόρεσα να δω τις ειδοποιήσεις τώρα.');}return;}
  // 2FA / κωδικός
  if(/2fa|διπλη πιστοποιησ|authenticator|αλλαγη κωδικ|αλλαξε κωδικ/.test(s)){
    showView('settings');cbBot('Άνοιξα τις Ρυθμίσεις. Εκεί αλλάζεις κωδικό και ενεργοποιείς το 2FA σαρώνοντας το QR με την εφαρμογή authenticator.');return;}
  // Προγραμματισμός
  if(/προγραμματισμ|χρονοπρογραμμ|αυτοματη εκδοσ/.test(s)){
    showView('schedule');cbBot('Άνοιξα τον Προγραμματισμό. Από εδώ βλέπεις και ακυρώνεις τις προγραμματισμένες εκδόσεις.');return;}
  // Stats Q&A
  if(/ποσα τιμολ|τζιρο|στατιστικ|how many invoic|φετοσ/.test(s)&&!isIssue){
    const period=/μηνα|μηνασ|φετινο μηνα/.test(s)?'month':'year';
    cbBot('Φέρνω στατιστικά…');
    try{const d=await api({statistics:1,period:period});
      cbBot((period==='year'?'Φέτος':'Αυτόν τον μήνα')+': '+(d.total_count??'—')+' παραστατικά, καθαρή αξία '+fmt(d.total_value||0)+' €.');}
    catch(e){cbBot('Δεν μπόρεσα να φέρω στατιστικά τώρα.');}return;}
  // New customer
  if(/νεοσ? πελατ|new customer|create customer|δημιουργησε πελατ|φτιαξε πελατ|καταχωρησε πελατ|προσθεσε πελατ|φτιαξε καρτελα|νεα καρτελα/.test(s)){
    const afm=(t.match(/\b(\d{9})\b/)||[])[1]||'';
    cbBot('Ανοίγω φόρμα νέου πελάτη'+(afm?(' για ΑΦΜ '+afm):'')+'. Έλεγξε τα στοιχεία και πάτα Αποθήκευση.');
    openCustomerModal(c=>{if(c)cbBot('✔ Ο πελάτης «'+(c.name||c.vat||'')+'» αποθηκεύτηκε.');},afm);return;}
  // New product / item
  if(/νεο ειδ|νεο προι|new item|new product|create item|δημιουργησε ειδ|φτιαξε ειδ|καταχωρησε ειδ|καταχωρησε προι|προσθεσε ειδ|προσθεσε προι/.test(s)){
    const price=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)/i,t);
    let desc=t.replace(/^.*?(νέο είδ\S*|νεο ειδ\S*|νέο προϊ\S*|νεο προι\S*|new (?:item|product)|καταχώρησε είδ\S*|καταχώρησε προϊ\S*|πρόσθεσε είδ\S*|πρόσθεσε προϊ\S*|δημιούργησε είδ\S*|φτιάξε είδ\S*)/i,'').replace(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur).*/i,'').replace(/\bτιμή\b|\bτιμη\b/gi,'').trim();
    cbBot('Ανοίγω φόρμα νέου είδους'+(desc?(' «'+desc+'»'):'')+(price?(' τιμή '+price+'€'):'')+'. Έλεγξε και πάτα Αποθήκευση.');
    openProductModal('',c=>{if(c)cbBot('✔ Το είδος αποθηκεύτηκε.');});
    setTimeout(()=>{if(desc&&$('#pdDesc'))$('#pdDesc').value=desc;if(price&&$('#pdPrice'))$('#pdPrice').value=price;},180);return;}
  // Issue invoice → smart flow (resolve customer & item, apply withholding)
  // Σκέτο όνομα ενότητας μετράει κι αυτό ως πλοήγηση: ο χρήστης λέει «πελάτες»,
  // όχι «πήγαινε στους πελάτες». **Μετά** τις συγκεκριμένες εντολές, γιατί το
  // «μαζική εκτύπωση» είναι δύο λέξεις και θα πήγαινε στη Μαζική έκδοση· και
  // **πριν** την έκδοση, γιατί ένα σκέτο «παραστατικά» περιέχει «παραστατ» και
  // αλλιώς ξεκινά ροή τιμολόγησης.
  if(s.trim().split(/\s+/).length<=2){
    const view=cbMatchView(s);
    if(view){showView(view);cbBot('Άνοιξα: '+(CB_VIEW_NAMES[view]||view)+'.');return;}
  }
  if(isIssue){cbStartIssue(cbParseIssue(t));return;}
  // Τελευταία ευκαιρία: μήπως είναι ενότητα, γραμμένη (ή ακουσμένη) με λάθος;
  // «Δεν το κατάλαβα» χωρίς πρόταση είναι αδιέξοδο — ο χρήστης δεν ξέρει τι να
  // δοκιμάσει μετά.
  const guess=cbMatchView(s);
  if(guess){
    showView(guess);
    cbBot('Δεν ήμουν σίγουρος, οπότε άνοιξα: '+(CB_VIEW_NAMES[guess]||guess)+'. Πες «άκυρο» αν δεν εννοούσες αυτό.');
    return;}
  cbBot('Δεν το κατάλαβα. Μπορώ να ανοίξω: '+
    Object.values(CB_VIEW_NAMES).join(' · ')+
    '\nή να ετοιμάσω πρόχειρο: «έκδοση τιμολογίου στον <ΑΦΜ> καθαρή αξία <ποσό>». Πες «βοήθεια» για όλα.');
}

// --- Smart issue assistant ----------------------------------------------------
// Parse a free-text issue command into a structured object.
function cbParseIssue(t){
  const afm=(t.match(/\b(\d{9})\b/)||[])[1]||'';
  // customer reference (name) after στην/στον/στη/στο/πελάτη/για
  let ref='';const m=t.match(/(?:στην|στον|στη|στο|πελάτ\S*|πελατ\S*|για\s+τον?ν?)\s+([\wΑ-Ωα-ωΆ-Ώά-ώ&.\-]+(?:\s+[\wΑ-Ωα-ωΆ-Ώά-ώ&.\-]+){0,3})/i);
  if(m)ref=m[1].replace(/\s+(καθαρ\S*|ποσ[όο]|αξ[ίι]α|με|είδος|ειδος|παρακρ\S*|,).*$/i,'').trim();
  // net / amount
  let net=cbNum(/καθαρ\S*\s*αξ\S*\s*(\d+(?:[.,]\d+)?)/i,t);
  if(net==null)net=cbNum(/(?:ποσ[όο]|αξ[ίι]α)\s*(\d+(?:[.,]\d+)?)/i,t);
  if(net==null)net=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)/i,t);
  const wpct=cbNum(/παρακρ\S*\s*(?:φ[όο]ρου)?\s*(\d+(?:[.,]\d+)?)\s*%/i,t);
  // item description after ειδος/είδος (up to a trailing amount/withholding clause)
  let item='';const mi=t.match(/ε[ίι]δος\s*[:\-]?\s*(.+)$/i);
  if(mi)item=mi[1].replace(/\s*(με\s+παρακρ\S*.*|καθαρ\S*\s*αξ\S*.*)$/i,'').trim();
  const qty=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:τεμ|τεμάχ|τεμαχ|\bx\b|\bχ\b)/i,t)||1;
  return {afm,customerRef:ref,net,withholdingPct:wpct,item,qty:qty||1};
}
function cbResolveCustomer(ref,afm){const custs=ALL_CUSTOMERS.map(custFields);
  if(afm){const c=custs.find(x=>x.vat===afm);if(c)return c;}
  if(ref){const q=ref.toLowerCase();
    return custs.find(x=>x.name.toLowerCase()===q)||custs.find(x=>x.name.toLowerCase().includes(q))||null;}
  return null;}
function cbFindProdByDesc(desc){if(!desc)return '';const d=desc.toLowerCase();let best='',bs=0;
  for(const c in PRODMAP){const pd=(PRODMAP[c].desc||'').toLowerCase();if(pd.length<3)continue;
    let hit=0;if(d.includes(pd)||pd.includes(d))hit+=5;
    for(const w of pd.split(/\s+/).filter(w=>w.length>=4))if(d.includes(w))hit++;
    if(hit>bs){bs=hit;best=c;}}
  return bs>=2?best:'';}
async function cbStartIssue(o){
  if(!ALL_CUSTOMERS.length)await loadCustomers();
  const cust=cbResolveCustomer(o.customerRef,o.afm);
  if(cust){o.afm=cust.vat;o.name=cust.name;return cbResolveProduct(o);}
  CB_CTX={stage:'who',o};
  cbBot('Δεν βρήκα πελάτη «'+(o.customerRef||o.afm||'—')+'». Είναι επαγγελματίας ή ιδιώτης;',
    `<div class="cbAct"><button class="go" onclick="cbWho('pro')">🏢 Επαγγελματίας</button><button class="go" onclick="cbWho('idiot')">👤 Ιδιώτης</button></div>`);
}
function cbWho(kind){if(!CB_CTX)return;const o=CB_CTX.o;
  if(kind==='pro'){CB_CTX.stage='afm';cbBot('Δώσε το <b>ΑΦΜ</b> της επιχείρησης «'+(o.customerRef||'')+'» για να τον καταχωρήσω.');}
  else{CB_CTX=null;o.retail=true;
    cbBot('Άνοιξα φόρμα νέου ιδιώτη — συμπλήρωσε ονοματεπώνυμο & στοιχεία και πάτα Αποθήκευση· μετά ετοιμάζω το παραστατικό.');
    openCustomerModal(c=>{if(c){o.afm=c.vat||'';o.name=c.name||o.customerRef||'';cbResolveProduct(o);}else CB_CTX=null;});
    setTimeout(()=>{custTab('personal');if(o.customerRef&&$('#cpName'))$('#cpName').value=o.customerRef.toUpperCase();},160);
  }
}
async function cbContinue(t){const s=t.toLowerCase();
  if(CB_CTX.stage==='who'){
    if(/επαγγελ|επιχειρ|εταιρ|professional/.test(s))return cbWho('pro');
    if(/ιδι[ώω]τ|φυσικ|individual/.test(s))return cbWho('idiot');
    cbBot('Πες «επαγγελματίας» ή «ιδιώτης».');return;}
  if(CB_CTX.stage==='afm'){const afm=(t.match(/\b(\d{9})\b/)||[])[1];
    if(!afm){cbBot('Δώσε ένα έγκυρο 9ψήφιο ΑΦΜ (ή «άκυρο»).');if(/άκυρ|ακυρ|cancel/.test(s))CB_CTX=null;return;}
    const o=CB_CTX.o;CB_CTX=null;o.afm=afm;o.name=o.customerRef||'';
    cbBot('✔ ΑΦΜ '+afm+' — θα δημιουργηθεί/βρεθεί αυτόματα κατά την έκδοση.');
    return cbResolveProduct(o);}
  CB_CTX=null;cbBot('Εντάξει, ακυρώθηκε.');
}
async function cbResolveProduct(o){
  if(!Object.keys(PRODMAP).length)await loadProductList();
  let code=o.code||'';
  if(!code&&o.item)code=cbFindProdByDesc(o.item);
  if(code){o.code=code;cbBot('✔ Βρήκα υπάρχον είδος: '+code+' — '+(PRODMAP[code]?.desc||''));return cbFinalizeIssue(o);}
  if(o.item){
    cbBot('Το είδος «'+o.item+'» δεν υπάρχει — το ανοίγω για δημιουργία. Έλεγξε κατηγορία/ΦΠΑ και πάτα Αποθήκευση.');
    openProductModal('',c=>{if(c){o.code=c;cbFinalizeIssue(o);}});
    setTimeout(()=>{if($('#pdDesc'))$('#pdDesc').value=o.item;if(o.net&&$('#pdPrice'))$('#pdPrice').value=o.net;},180);
    return;}
  cbFinalizeIssue(o);
}
function cbFinalizeIssue(o){
  const price=(o.net!=null?o.net:o.price)||'';
  const sum='Θα ετοιμάσω ΠΡΟΧΕΙΡΟ:\n• Πελάτης: '+(o.name||o.afm||'—')
    +'\n• Είδος: '+(o.code?(o.code+' '+(PRODMAP[o.code]?.desc||'')):(o.item||'(στη φόρμα)'))
    +'\n• Ποσότητα: '+(o.qty||1)+(price!==''?('\n• Καθαρή αξία: '+fmt(price)+' €'):'')
    +(o.withholdingPct?('\n• Παρακράτηση φόρου: '+o.withholdingPct+'%'):'');
  const id='__cbi'+Date.now();window[id]={afm:o.afm,name:o.name,code:o.code,qty:o.qty||1,price,withholdingPct:o.withholdingPct,retail:o.retail};
  cbBot(sum,`<div class="cbAct"><button class="go" onclick="cbDoIssue(window['${id}'])">✔ Ετοίμασε πρόχειρο</button><button onclick="showView('issue')">Άνοιξε φόρμα</button></div>`);
}
async function cbApplyWithholding(pct){await loadTaxCats();
  const list=(TAXCATS&&TAXCATS.withheld)||[];
  const target=list.find(c=>Math.abs(taxRateFromLabel(c.label)*100-pct)<0.01)||list.find(c=>(c.label||'').includes(pct+'%'));
  if(!target){cbBot('⚠ Δεν βρήκα κατηγορία παρακράτησης '+pct+'% — πρόσθεσέ την χειροκίνητα από «💶 Φόρος/Κράτηση».');return;}
  const net=issueNetTotal();const amt=Math.round(net*(pct/100)*100)/100;
  ITAXES.push({type:1,category:target.code,amount:amt,notes:'',label:target.label});renderTaxes();sumTotals();
}
// Execute an issue command → fills the form and saves a DRAFT (preview) for review.
async function cbDoIssue(o){cbBot('Ετοιμάζω το πρόχειρο…');
  showView('issue');wizSkip(o.retail?'idiot':'pro');await loadIssueTypes();await new Promise(r=>setTimeout(r,200));
  if(o.afm){$('#iAfm').value=o.afm;if(/^\d{9}$/.test(o.afm)){lookupAfm();await new Promise(r=>setTimeout(r,700));}}
  if(o.name&&!$('#iName').value)$('#iName').value=o.name;
  $('#iLines tbody').innerHTML='';addLine(o.code||'',o.qty||1,o.price||'');
  const row=$('#iLines tbody tr:last-child');
  if(o.code&&PRODMAP[o.code]){pickProd(row.querySelector('.ln-code'),o.code);}
  if(o.price){row.querySelector('.ln-price').value=elFmt(elNum(o.price),4);lineFromInputs(row);}
  await new Promise(r=>setTimeout(r,150));
  if(o.withholdingPct)await cbApplyWithholding(o.withholdingPct);
  if(!collectLines().length){cbBot('Χρειάζεται είδος/τιμή — συμπλήρωσέ τα στη φόρμα και πάτα «Πρόχειρο».');return;}
  await submitInvoice(false);
  cbBot('✔ Το πρόχειρο ετοιμάστηκε'+(o.withholdingPct?(' με παρακράτηση '+o.withholdingPct+'%'):'')+'. Έλεγξέ το εδώ ή στα «Πρόχειρα» και έκδωσέ το χειροκίνητα.');
}
$('#cbLang').addEventListener('change',()=>{if(cbRec)cbRec.lang=$('#cbLang').value;});

// boot
// Warm ALL e-timologio caches in the background so every view opens instantly
// (same snapshot-cache mechanism used for πελάτες). Fire-and-forget, staggered
// so we don't hammer the AADE session with parallel logins.
async function prewarmAll(){const kinds=['customers','products','series','invtypes','categories','deductions','drafts'];
  for(const k of kinds){try{await api({sync:k});}catch(e){}}}

// --- Guided page tour ---------------------------------------------------------
const TOUR=[
  {sel:'[data-view="issue"]',view:'issue',title:'🧾 Έκδοση',text:'Ξεκίνα εδώ. Ένας οδηγός σε ρωτά τι θέλεις να εκδώσεις (Τιμολόγιο/Απόδειξη ή Δελτίο) και αν ο πελάτης είναι επαγγελματίας ή ιδιώτης, και προσαρμόζει τη φόρμα.'},
  {sel:'[data-view="bulk"]',title:'📚 Μαζική έκδοση',text:'Έκδοση πολλών παραστατικών μαζί: μία γραμμή ανά παραστατικό με picker πελάτη & είδους — χωρίς πληκτρολόγηση ΑΦΜ/κωδικών.'},
  {sel:'[data-view="customers"]',title:'👥 Πελάτες',text:'Το πελατολόγιό σου με φίλτρα ανά στήλη. Από κάθε γραμμή εκδίδεις κατευθείαν ή ανοίγεις την καρτέλα.'},
  {sel:'[data-view="card"]',title:'📇 Καρτέλα πελάτη',text:'Τιμολόγια ΑΑΔΕ + τοπικές πληρωμές + τρέχον υπόλοιπο. Από τα κουμπιά της καρτέλας βγάζεις PDF καρτέλας, κάνεις <b>μαζική εκτύπωση</b> όλων των παραστατικών του πελάτη (με προεπισκόπηση) ή τα κατεβάζεις όλα σε <b>ZIP</b>. <b>Διπλό κλικ σε πληρωμή</b> την ανοίγει για διόρθωση.'},
  {sel:'[data-view="card"]',title:'✉️ Στείλε την καρτέλα',text:'Το «✉️ Αποστολή καρτέλας» στέλνει το PDF στον πελάτη — πάντα με προεπισκόπηση κειμένου, που απευθύνεται στην <b>επωνυμία</b> του και λέει αν το υπόλοιπο είναι «προς πληρωμή» ή «πιστωτικό», μαζί με τα IBAN σου. Το «📨 Μαζική αποστολή» κάνει το ίδιο για πολλούς μαζί, με φίλτρο σε όσους χρωστούν.'},
  {sel:'[data-view="documents"]',title:'📄 Παραστατικά',text:'Όλα τα εκδοθέντα της περιόδου σε μία λίστα. Τσέκαρε όσα θέλεις και τύπωσέ τα μαζί ή κατέβασέ τα σε <b>ZIP</b>. Με το «⚙ Στήλες» διαλέγεις τι φαίνεται — π.χ. κρύβεις το ΜΑΡΚ που πιάνει πλάτος.'},
  {sel:'[data-view="cancel"]',title:'↩️ Ακύρωση / Πιστωτικό',text:'Στο myDATA δεν διαγράφεις παραστατικό — το ακυρώνεις με συσχετιζόμενο πιστωτικό. Διάλεξε το αρχικό ΜΑΡΚ· πλήρης αξία = ακύρωση, μικρότερη = μερική πίστωση.'},
  {sel:'[data-view="bankimp"]',title:'🏦 Εισαγωγή πληρωμών',text:'Ανέβασε extrait τράπεζας (CSV/XLSX) για μαζική καταχώρηση — ή πάτα «+ Νέα πληρωμή» για μία-μία. Με την <b>επαναλαμβανόμενη εισαγωγή</b> το παράθυρο μένει ανοιχτό και κρατά τον ίδιο πελάτη, και το «📇 Καρτέλα» δείχνει το υπόλοιπό του χωρίς να φύγεις από τη φόρμα.'},
  {sel:'[data-view="series"]',title:'🔢 Σειρές',text:'Κάθε τύπος παραστατικού χρειάζεται μία σειρά για να εκδοθεί. Δημιούργησέ τες με το πράσινο κουμπί «➕ Νέα σειρά».'},
  {sel:'[data-view="drafts"]',title:'📝 Πρόχειρα',text:'Προσωρινά αποθηκευμένα (χωρίς ΜΑΡΚ): προεπισκόπηση PDF και μαζική διαγραφή με τα checkboxes.'},
  {sel:'[data-view="schedule"]',title:'⏰ Προγραμματισμός',text:'Προγραμμάτισε την αυτόματη έκδοση παραστατικών (μεμονωμένων ή μαζικών) σε μελλοντική ώρα, με προαιρετική επανάληψη. Εδώ βλέπεις κατάσταση & ιστορικό.'},
  {sel:'#account',title:'🏢 Επιλογή εταιρίας',text:'Διάλεξε εδώ την επιχείρηση με την οποία δουλεύεις. Ο <b>διαχειριστής</b> βλέπει κάθε εταιρία· ο <b>λογιστής</b> μόνο τις δικές του — και τις ανοίγει μόνος του από τη Διαχείριση, χωρίς να περιμένει ανάθεση.'},
  {sel:'[data-view="admin"]',title:'🛡️ Διαχείριση',text:'Πάνω-πάνω γράφει τι ακριβώς βλέπεις. Κάθε εταιρία έχει <b>δική της καρτέλα</b>: ΑΦΜ, ετικέτα, διαπιστευτήρια ΑΑΔΕ και ποιοι λογιστές έχουν πρόσβαση. Το «➕ Νέα εταιρία» την προσθέτει αμέσως στο γραφείο σου.'},
  {sel:'.bell-btn',title:'🔔 Ειδοποιήσεις',text:'Κάθε πραγματική έκδοση (ΜΑΡΚ) ειδοποιεί τον λογιστή/διαχειριστή. Το κουδουνάκι δείχνει τις αδιάβαστες και ποιος εξέδωσε τι.'},
  {sel:'[data-view="settings"]',title:'⚙️ Ρυθμίσεις & προτιμήσεις email',text:'Αλλαγή κωδικού, ενεργοποίηση 2FA με authenticator, και — για λογιστή/διαχειριστή — επιλογή για ΠΟΙΕΣ εταιρίες και ΠΟΙΕΣ κινήσεις θα λαμβάνεις email ειδοποιήσεων.'},
  {sel:'#bkTable',view:'settings',title:'🏦 Λογαριασμοί & αυτόματη αποστολή',text:'Καταχώρησε τα IBAN της επιχείρησης — η τράπεζα βγαίνει από λίστα και το IBAN ελέγχεται πραγματικά (mod-97), οπότε λάθος ψηφίο δεν περνά. Όσα έχουν ✓ «στο email» γράφονται στα μηνύματα καρτέλας με <b>χρεωστικό</b> υπόλοιπο· μπορείς και να ανεβάσεις PDF με τους λογαριασμούς.'},
  {sel:'#bkAutoSend',view:'settings',title:'📤 Να φεύγει μόνο του',text:'Με τον διακόπτη ενεργό, κάθε παραστατικό που παίρνει ΜΑΡΚ στέλνεται αμέσως στον πελάτη με το PDF συνημμένο. Παρακάτω ορίζεις και <b>προγραμματισμένη αποστολή καρτελών</b>: ημέρα του μήνα, μόνο σε όσους χρωστούν, πάνω από ένα ποσό.'},
  {sel:'.search-trigger',title:'🔍 Γρήγορη αναζήτηση',text:'Πάτα Ctrl+K οποιαδήποτε στιγμή για να βρεις πελάτη αστραπιαία.'},
  {sel:'#cbToggle',title:'🎤 Ψηφιακός βοηθός',text:'Γράψε ή <b>μίλα</b> και εκτελεί: «έκδοση τιμολογίου στον 802012659 για 2 τεμ ΚΩΔ 10 ευρώ», «μαζική εκτύπωση», «παραστατικά», «πόσες αδιάβαστες», «πήγαινε στην καρτέλα». Πες «βοήθεια» για όλη τη λίστα. Ό,τι ετοιμάζει μένει <b>πρόχειρο</b> — ΜΑΡΚ παίρνεις μόνο εσύ.<br><br>Στην εφαρμογή υπολογιστή ακούει και μιλά <b>εκτός δικτύου</b>: τίποτα δεν φεύγει από το μηχάνημα. Οι φωνητικές εντολές είναι αξιόπιστες για πλοήγηση και ερωτήσεις — τα ΑΦΜ γράψε τα.'},
  {sel:'.side-actions',title:'🧭 Ξενάγηση & Εγχειρίδιο',text:'Εδώ, πάνω από τους διακόπτες, θα βρίσκεις πάντα την «Ξενάγηση» και το «Εγχειρίδιο» (PDF) για βοήθεια.'},
  {sel:'#themeToggle',title:'🌙 Θέμα & επεξηγήσεις',text:'Οι δύο διακόπτες κάτω από τις «ΡΥΘΜΙΣΕΙΣ» δουλεύουν ακριβώς όπως στην εφαρμογή υπολογιστή: «Φωτεινό θέμα» αλλάζει φωτεινό/σκοτεινό και «Βοηθητικά μηνύματα» εμφανίζει ή κρύβει τις επεξηγήσεις.'},
  {sel:'#custTable thead th:nth-child(3)',view:'customers',title:'📐 Οι πίνακες είναι δικοί σου',text:'Σύρε το <b>δεξί όριο</b> μιας κεφαλίδας για πλάτος, σύρε την <b>ίδια την κεφαλίδα</b> για να αλλάξεις σειρά στηλών, και πέρνα από πάνω για το <b>χωνί</b> φίλτρου. Η διάταξη αποθηκεύεται στον λογαριασμό σου και σε ακολουθεί σε κάθε υπολογιστή.'}
];
let tourI=0;
function startTour(){tourI=0;$('#tourOverlay').classList.add('on');localStorage.setItem('etim_tour_done','1');tourShow(0);}
function endTour(){$('#tourOverlay').classList.remove('on');}
function tourPrev(){if(tourI>0)tourShow(tourI-1);}
function tourNext(){if(tourI<TOUR.length-1)tourShow(tourI+1);else endTour();}
function tourShow(i){tourI=i;const s=TOUR[i];if(s.view)showView(s.view);
  $('#tourTitle').textContent=s.title;$('#tourText').textContent=s.text;$('#tourStep').textContent=(i+1)+' / '+TOUR.length;
  $('#tourPrev').style.visibility=i===0?'hidden':'visible';$('#tourNext').textContent=i===TOUR.length-1?'Τέλος':'Επόμενο →';
  const el=document.querySelector(s.sel),ring=$('#tourRing'),box=$('#tourBox');
  setTimeout(()=>{
    if(!el){ring.style.display='none';box.style.left='50%';box.style.top='40%';box.style.transform='translate(-50%,-50%)';return;}
    el.scrollIntoView({block:'center',behavior:'smooth'});
    const r=el.getBoundingClientRect();
    ring.style.display='block';ring.style.left=(r.left-6)+'px';ring.style.top=(r.top-6)+'px';ring.style.width=(r.width+12)+'px';ring.style.height=(r.height+12)+'px';
    box.style.transform='none';let bx=r.right+16,by=r.top;
    if(bx+340>window.innerWidth){bx=Math.max(14,r.left);by=r.bottom+14;}
    if(by+190>window.innerHeight)by=Math.max(14,window.innerHeight-200);
    box.style.left=Math.max(14,bx)+'px';box.style.top=by+'px';
  },s.view?60:0);
}

// --- User manual (PDF) --------------------------------------------------------
const MANUAL=[
  ['e-Timologio Pro — Εγχειρίδιο χρήσης','h1'],
  ['Πλήρης εφαρμογή έκδοσης παραστατικών & διαχείρισης πελατών πάνω από το e-timologio της ΑΑΔΕ (myDATA). Υποστηρίζει πολλαπλές επιχειρήσεις, ρόλους (διαχειριστής/λογιστής/επιχείρηση), χρονοπρογραμματισμό εκδόσεων, ειδοποιήσεις και προαιρετικό 2FA. Το παρόν εγχειρίδιο καλύπτει αναλυτικά κάθε λειτουργία.','p'],

  ['0. Γρήγορη εκκίνηση','h2'],
  ['1) Συνδέσου με email/κωδικό (αν έχεις ενεργό 2FA, δώσε και τον 6ψήφιο κωδικό authenticator). 2) Πάνω αριστερά διάλεξε «Λογαριασμό» (επιχείρηση) — αν είσαι λογιστής/διαχειριστής βλέπεις όλες τις εταιρίες. 3) Στην «Έκδοση» ο οδηγός σε καθοδηγεί βήμα-βήμα. 4) Δοκίμασε πάντα πρώτα με «Αποθήκευση & Προεπισκόπηση» (πρόχειρο, χωρίς ΜΑΡΚ) και μόνο όταν είσαι σίγουρος πάτα «Οριστική Έκδοση».','p'],
  ['Βασικός κανόνας ασφάλειας: τίποτα δεν υποβάλλεται στην ΑΑΔΕ (δεν παίρνει ΜΑΡΚ) παρά μόνο με το κόκκινο κουμπί «Οριστική Έκδοση» — ή αυτόματα, μόνο για όσα εσύ έχεις προγραμματίσει.','p'],

  ['1. Έκδοση παραστατικού','h2'],
  ['Ο οδηγός έκδοσης ρωτά πρώτα «Τιμολόγιο/Απόδειξη ή Δελτίο αποστολής;» και μετά «Επαγγελματίας ή Ιδιώτης;», επιλέγοντας αυτόματα τον σωστό τύπο παραστατικού (τιμολόγιο vs απόδειξη) και εστιάζοντας στο κατάλληλο πεδίο (ΑΦΜ για επαγγελματία, Επωνυμία για ιδιώτη).','p'],
  ['Βήματα: (α) Δώσε ΑΦΜ — τα στοιχεία του πελάτη αντλούνται αυτόματα από το Taxisnet/e-timologio (ή δημιουργείται νέος πελάτης). (β) Επίλεξε Σειρά και Τρόπο εξόφλησης (προεπιλογή «Επί πιστώσει»). (γ) Πρόσθεσε γραμμές ειδών με το picker (κωδικός + περιγραφή + ΦΠΑ)· η τιμή μονάδας συμπληρώνεται από το είδος. (δ) Προαιρετικά πρόσθεσε έκπτωση % ανά γραμμή, φόρους/κρατήσεις (το ποσό υπολογίζεται αυτόματα από το ποσοστό) και σημειώσεις.','p'],
  ['Κουμπιά: «💾👁 Αποθήκευση & Προεπισκόπηση» δημιουργεί/ενημερώνει πρόχειρο και δείχνει το πραγματικό PDF προεπισκόπησης της ΑΑΔΕ (χωρίς ΜΑΡΚ)· «🆕 Νέο» ξεκινά νέο πρόχειρο· «⏰ Προγραμματισμός» προγραμματίζει την έκδοση για αργότερα· «📤 Οριστική Έκδοση» υποβάλλει στην ΑΑΔΕ και δίνει ΜΑΡΚ. Μετά την έκδοση προσφέρεται και δημιουργία σχετικού Δελτίου αποστολής για τα ίδια αγαθά.','p'],
  ['Φωνητικός/έξυπνος βοηθός: μπορείς να πεις/γράψεις π.χ. «έκδοση τιμολογίου στην <επωνυμία> καθαρή αξία <ποσό> με παρακράτηση <%> είδος <περιγραφή>» — ο βοηθός βρίσκει τον πελάτη με το όνομα, βρίσκει/δημιουργεί το είδος και εφαρμόζει την παρακράτηση, ετοιμάζοντας πάντα ΠΡΟΧΕΙΡΟ.','p'],

  ['2. Μαζική έκδοση','h2'],
  ['Για πολλά παραστατικά ταυτόχρονα: μία γραμμή ανά παραστατικό, με picker πελάτη και είδους (χωρίς πληκτρολόγηση ΑΦΜ/κωδικών) και κοινό τύπο/σειρά/τρόπο πληρωμής/γλώσσα από πάνω. «➕ Γραμμή» για νέα εγγραφή, «➕ Νέος πελάτης…»/«➕ Νέο είδος…» εν κινήσει. Για προχωρημένους υπάρχει και εισαγωγή από CSV (ΑΦΜ;κωδικός;ποσότητα;τιμή).','p'],
  ['«💾 Δημιουργία προχείρων (όλα)» για δοκιμή, «⏰ Προγραμματισμός» για μελλοντική μαζική έκδοση, «📤 Οριστική έκδοση όλων» για υποβολή. Τα αποτελέσματα εμφανίζονται ανά γραμμή (ΜΑΡΚ ή σφάλμα), ώστε μια μερική αποτυχία να είναι διαφανής.','p'],

  ['3. Πελάτες & Καρτέλα','h2'],
  ['«Πελάτες»: όλο το πελατολόγιο με ταξινόμηση και φίλτρα ανά στήλη (χωνάκι ▾ με λίστα τιμών, τύπου Excel). Από κάθε γραμμή εκδίδεις κατευθείαν ή ανοίγεις την καρτέλα. «+ Νέος πελάτης» με ΑΦΜ (άντληση από Taxisnet) ή ως ιδιώτης χωρίς ΑΦΜ.','p'],
  ['«Καρτέλα»: συνδυάζει τα παραστατικά της ΑΑΔΕ με τις τοπικές πληρωμές σε μια κίνηση χρέωσης/πίστωσης με τρέχον υπόλοιπο. «+ Πληρωμή» για καταχώρηση είσπραξης, «📄 PDF καρτέλας» για εκτύπωση και «🗜️ ZIP παραστατικών» για μαζική λήψη PDF.','p'],

  ['3β. Μαζική εκτύπωση & εξαγωγή ZIP','h2'],
  ['Από την «Καρτέλα» ενός πελάτη έχεις δύο μαζικές ενέργειες για ΟΛΑ τα παραστατικά του διαστήματος:','p'],
  ['🖨️ <b>Μαζική εκτύπωση</b> — κατεβάζει τα PDF από την ΑΑΔΕ, τα ενώνει σε ένα αρχείο και ανοίγει προεπισκόπηση. Από εκεί τυπώνεις όλα μαζί με μία εργασία, αντί να ανοίγεις ένα-ένα.','li'],
  ['🗜️ <b>ZIP παραστατικών</b> — πακετάρει τα ίδια PDF σε ένα αρχείο ZIP για αρχειοθέτηση ή αποστολή στον πελάτη. Κάθε αρχείο ονομάζεται «ημερομηνία σειρά-ΑΑ ΜΑΡΚ.pdf», ώστε να ταξινομούνται σωστά.','li'],
  ['Οι ίδιες ενέργειες υπάρχουν και στην εφαρμογή υπολογιστή (σελίδα «Παραστατικά», με επιλογή γραμμών μέσω checkbox). Λειτουργούν και όταν συνδέεσαι στον κεντρικό server (thin client) — η λήψη των PDF γίνεται από τον server, μέσα στα δικαιώματα του λογαριασμού σου.','p'],
  ['Όριο: 200 παραστατικά ανά παρτίδα. Αν κάποιο PDF δεν βρεθεί, τα υπόλοιπα προχωρούν κανονικά και ενημερώνεσαι για όσα έλειψαν.','p'],

  ['4. Εισαγωγή πληρωμών (extrait τράπεζας)','h2'],
  ['Ανέβασε αρχείο κινήσεων τράπεζας (CSV Eurobank, XLSX Optima/Εθνικής κ.ά.). Η εφαρμογή αναγνωρίζει αυτόματα ημερομηνία/περιγραφή/ποσό (και ελληνικά νούμερα 1.234,56), αντιστοιχίζει κάθε κατάθεση σε πελάτη (με ΑΦΜ ή ασαφή αντιστοίχιση ονόματος), σου επιτρέπει να διορθώσεις/επιλέξεις πελάτη ανά γραμμή, και καταχωρεί μαζικά τις εισπράξεις. Προσοχή: το ποσό κατάθεσης καταχωρείται όπως είναι — δεν «κλείνει» υποχρεωτικά υπόλοιπο (μερικές/υπερβάλλουσες πληρωμές επιτρέπονται).','p'],

  ['5. Σειρές','h2'],
  ['Κάθε τύπος παραστατικού απαιτεί τουλάχιστον μία καταχωρημένη σειρά για να εκδοθεί. Στη «Σειρές» βλέπεις όλες τις σειρές και δημιουργείς νέα με το πράσινο «➕ Νέα σειρά» (τύπος, κωδικός π.χ. Α/ΤΠΥ/ΔΑ, αρχικό Α/Α, περιγραφή). Χωρίς σειρά, ο τύπος δεν εμφανίζεται στη λίστα έκδοσης.','p'],

  ['6. Πρόχειρα','h2'],
  ['Τα προσωρινά αποθηκευμένα (χωρίς ΜΑΡΚ). Προεπισκόπηση του πραγματικού PDF της ΑΑΔΕ για οποιοδήποτε πρόχειρο, μαζική επιλογή με checkboxes και μαζική διαγραφή. Ιδανικό για να ετοιμάζεις παραστατικά και να τα οριστικοποιείς αργότερα.','p'],

  ['7. Προγραμματισμός εκδόσεων (χρονοπρογραμματισμός)','h2'],
  ['Προγραμμάτισε την αυτόματη οριστική έκδοση ενός παραστατικού ή μιας ολόκληρης μαζικής παρτίδας για μελλοντική ημερομηνία/ώρα, με προαιρετική επανάληψη (καθημερινά/εβδομαδιαία/μηνιαία). Στην «Έκδοση» ή τη «Μαζική έκδοση» πάτα «⏰ Προγραμματισμός», όρισε ημερομηνία/ώρα (τοπική ώρα Ελλάδας) και επανάληψη, και προαιρετικά μια περιγραφή.','p'],
  ['Στην ενότητα «Προγραμματισμός» βλέπεις όλα τα προγράμματα με κατάσταση (σε αναμονή / ολοκληρώθηκε / απέτυχε / ακυρώθηκε), την τελευταία εκτέλεση με το ΜΑΡΚ ή το σφάλμα, και κουμπί ακύρωσης. Ο λογιστής/διαχειριστής βλέπει τα προγράμματα όλων των εταιριών· η επιχείρηση μόνο τα δικά της. Για να προγραμματίσεις για συγκεκριμένη εταιρία, επίλεξέ την πρώτα από τον διακόπτη «Λογαριασμός».','p'],
  ['Τεχνική προϋπόθεση: πρέπει να τρέχει ο runner scheduler.php στον server κάθε λεπτό (Windows Task Scheduler ή cron), με ορισμένα τα SCHED_TOKEN και APP_BASE_URL στο config.php.','p'],

  ['8. Ειδοποιήσεις εκδόσεων','h2'],
  ['Κάθε πραγματική έκδοση (λαμβάνει ΜΑΡΚ) — εκτός από τα δελτία αποστολής (9.x) — καταγράφει ειδοποίηση για τον λογιστή/διαχειριστή. Το κουδουνάκι 🔔 πάνω δεξιά δείχνει το πλήθος των αδιάβαστων και ανοίγει τη λίστα με το ποιος εξέδωσε τι και πότε: τύπος παραστατικού, πελάτης, σειρά/ΑΑ, σύνολο, ΜΑΡΚ και ένδειξη πηγής (⏰ προγραμματισμένη, 📚 μαζική). Ο λογιστής/διαχειριστής βλέπει τις εκδόσεις όλων των εταιριών· η κάθε επιχείρηση μόνο τις δικές της. Πάτησε μια ειδοποίηση για να τη σημάνεις αναγνωσμένη, ή «✓ Όλα».','p'],

  ['9. Προτιμήσεις email ειδοποιήσεων (ανά εταιρία & κίνηση)','h2'],
  ['Ο λογιστής/διαχειριστής ρυθμίζει από «Ρυθμίσεις → Ειδοποιήσεις email» για ΠΟΙΕΣ εταιρίες-πελάτες και ΠΟΙΕΣ κινήσεις θέλει να λαμβάνει email όταν εκδίδεται παραστατικό: επίλεξε «(Όλες)» ή συγκεκριμένες εταιρίες, και τύπους κίνησης (Τιμολόγια, Αποδείξεις λιανικής, Πιστωτικά/Ακυρώσεις). Ο γενικός διακόπτης «Λαμβάνω email» ενεργοποιεί/απενεργοποιεί εντελώς τα email. Οι εντός εφαρμογής ειδοποιήσεις (🔔) δεν επηρεάζονται — φιλτράρονται μόνο τα email. Απαιτείται ρυθμισμένος πάροχος email (Resend ή SMTP) στο config.php.','p'],

  ['10. Ρόλοι & μέλη (διαχειριστής/λογιστής/επιχείρηση)','h2'],
  ['Τρεις ρόλοι: «Διαχειριστής» = πλήρη δικαιώματα, διαχείριση μελών και πρόσβαση σε όλες τις εταιρίες· «Λογιστής» = πρόσβαση/έκδοση/χρονοπρογραμματισμός/ειδοποιήσεις σε όλες τις εταιρίες, χωρίς διαχείριση μελών· «Επιχείρηση» = μόνο οι δικές της εταιρίες.','p'],
  ['Ο διαχειριστής, από τη «Διαχείριση»: εγκρίνει νέες εγγραφές, αλλάζει ρόλο κάθε μέλους από το αναπτυσσόμενο μενού, βλέπει την κατάσταση 2FA, και προσκαλεί νέα μέλη με email («✉️ Πρόσκληση μέλους» → email με σύνδεσμο ενεργοποίησης όπου το μέλος ορίζει κωδικό). Αν δεν υπάρχει πάροχος email, εμφανίζεται ο σύνδεσμος ενεργοποίησης για χειροκίνητη αποστολή.','p'],
  ['Ως λογιστής/διαχειριστής, επίλεξε εταιρία από τον διακόπτη «Λογαριασμός» πάνω και εργάσου (έκδοση, καρτέλες, πληρωμές, χρονοπρογραμματισμός, ειδοποιήσεις) για οποιαδήποτε εταιρία-πελάτη.','p'],

  ['11. Ασφάλεια — 2FA με authenticator','h2'],
  ['Προαιρετική επαλήθευση δύο παραγόντων. Από «Ρυθμίσεις → 2FA» πάτα «Ενεργοποίηση», σκάναρε τον κωδικό QR με εφαρμογή authenticator (Google Authenticator, Authy, Microsoft Authenticator, 1Password κ.λπ.) ή καταχώρησε το εμφανιζόμενο κλειδί χειροκίνητα, και επιβεβαίωσε με τον 6ψήφιο κωδικό. Στο εξής, σε κάθε σύνδεση θα ζητείται ο τρέχων κωδικός. Απενεργοποίηση με τον κωδικό authenticator ή με τον κωδικό πρόσβασής σου. Το μυστικό 2FA αποθηκεύεται κρυπτογραφημένο.','p'],

  ['11β. Ψηφιακός βοηθός','h2'],
  ['Το μπλε κουμπί με το μικρόφωνο (κάτω δεξιά) ανοίγει τον βοηθό. Γράφεις ή μιλάς στα ελληνικά και εκτελεί ενέργειες — αναγνωρίζει το κείμενο με ή χωρίς τόνους.','p'],
  ['Έκδοση: «έκδοση τιμολογίου στην <επωνυμία ή ΑΦΜ> καθαρή αξία <ποσό> με παρακράτηση <%> είδος <περιγραφή>». Βρίσκει τον πελάτη από το όνομα, ρωτά αν είναι επαγγελματίας ή ιδιώτης όταν δεν υπάρχει, και βρίσκει ή δημιουργεί το είδος.','li'],
  ['Δεδομένα: «νέος πελάτης <ΑΦΜ>», «νέο είδος <περιγραφή> <τιμή> ευρώ», «νέα σειρά».','li'],
  ['Εκτυπώσεις: «μαζική εκτύπωση», «ZIP παραστατικών», «PDF καρτέλας».','li'],
  ['Λογαριασμός & αυτοματισμοί: «ειδοποιήσεις», «πόσες αδιάβαστες», «προγραμματισμός», «ενεργοποίηση 2FA», «αλλαγή κωδικού», «διαχείριση χρηστών».','li'],
  ['Ερωτήσεις: «πόσα τιμολόγια φέτος», «τζίρος μήνα». Πλοήγηση: «πήγαινε στην καρτέλα/πελάτες/είδη/σειρές/πρόχειρα…».','li'],
  ['<b>Ασφάλεια:</b> ό,τι ετοιμάζει ο βοηθός μένει ΠΡΟΧΕΙΡΟ. Το παραστατικό παίρνει ΜΑΡΚ μόνο όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση». Πες «βοήθεια» για την πλήρη λίστα.','p'],

  ['11γ. Λογαριασμοί, IBAN και αποστολή με email','h2'],
  ['Στις «Ρυθμίσεις → 🏦 Λογαριασμοί & αυτόματη αποστολή» καταχωρείς τους τραπεζικούς λογαριασμούς της επιχείρησης. Η τράπεζα επιλέγεται από λίστα και το IBAN ελέγχεται με το διεθνές πρότυπο mod-97 — λάθος ψηφίο δεν αποθηκεύεται. Όσοι λογαριασμοί έχουν ✓ στο «στο email» γράφονται μέσα στο μήνυμα της καρτέλας.','p'],
  ['Αν προτιμάς έτοιμο έντυπο, ανέβασε PDF με τους λογαριασμούς (έως 3 MB): επισυνάπτεται αντί για — ή μαζί με — το κείμενο. Οι λογαριασμοί μπαίνουν ΜΟΝΟ όταν το υπόλοιπο είναι χρεωστικό· σε πιστωτικό δεν έχουν τι να εξυπηρετήσουν.','li'],
  ['<b>Αυτόματη αποστολή παραστατικού:</b> με τον διακόπτη ενεργό, κάθε παραστατικό που παίρνει ΜΑΡΚ φεύγει αμέσως στον πελάτη με το PDF συνημμένο. Αν ο πελάτης δεν έχει email, η παράλειψη καταγράφεται στο ημερολόγιο ενεργειών — δεν χάνεται σιωπηλά. Το πεδίο BCC κρατά αντίγραφο στο γραφείο.','li'],
  ['<b>Αποστολή καρτέλας:</b> από την Καρτέλα, το «✉️ Αποστολή καρτέλας» ανοίγει το μήνυμα για να το διορθώσεις πριν φύγει. Το κείμενο απευθύνεται στην επωνυμία του πελάτη και λέει με λέξεις αν το υπόλοιπο είναι «προς πληρωμή» ή «πιστωτικό». Η καρτέλα στέλνεται πάντα με SMTP, από τη διεύθυνση της επιχείρησης.','li'],
  ['<b>Μαζική αποστολή:</b> το «📨 Μαζική αποστολή» δείχνει όλους τους πελάτες με τα υπόλοιπά τους, με φίλτρο «μόνο χρεωστικά» και ελάχιστο ποσό. Βλέπεις ποιος θα λάβει τι πριν στείλεις. Το «🔎 Εύρεση email» συμπληρώνει όσες διευθύνσεις λείπουν, ρωτώντας την ΑΑΔΕ μία φορά ανά πελάτη.','li'],
  ['<b>Προγραμματισμένη αποστολή:</b> ορίζεις ημέρα του μήνα και φίλτρο, και οι καρτέλες φεύγουν μόνες τους — το πολύ μία φορά τον μήνα. Επειδή τρέχει χωρίς browser, η καρτέλα γράφεται ως πίνακας κινήσεων ΜΕΣΑ στο μήνυμα (το PDF το φτιάχνει ο browser). Το «▶️ Αποστολή τώρα» την τρέχει αμέσως.','li'],

  ['11δ. Επιβεβαίωση email στην εγγραφή','h2'],
  ['Μια νέα εγγραφή λαμβάνει πρώτα σύνδεσμο επιβεβαίωσης (ισχύει 24 ώρες). Ο διαχειριστής ειδοποιείται μόνο αφού επιβεβαιωθεί το email — έτσι η ουρά εγκρίσεων δεν γεμίζει με τυπογραφικά λάθη. Αν ο σύνδεσμος λήξει, από την οθόνη σύνδεσης ζητάς νέον.','p'],

  ['11ε. Λήψεις αρχείων','h2'],
  ['Στην εφαρμογή υπολογιστή τα PDF κατεβαίνουν κατευθείαν στον φάκελο λήψεων (ορίζεται από τον Πίνακα ελέγχου) και ανοίγουν στον αναγνώστη σου. Δεύτερη λήψη του ίδιου παραστατικού <b>αντικαθιστά</b> το αρχείο αντί να αφήνει αντίγραφα «(1)», «(2)». Αν το αρχείο είναι ανοιχτό εκείνη τη στιγμή, η λήψη παίρνει δεύτερο όνομα ώστε να μη χαθεί.','p'],
  ['Οι καρτέλες αποθηκεύονται ως <b>ΚΑΡΤΕΛΑ (ΕΠΩΝΥΜΙΑ ΠΕΛΑΤΗ).pdf</b>.','li'],

  ['11στ. Όταν πέσει το internet','h2'],
  ['Κάθε έκδοση περνά από την ΑΑΔΕ, άρα χωρίς σύνδεση δεν εκδίδεται τίποτα. Μόλις χαθεί η γραμμή εμφανίζεται <b>κόκκινη μπάρα</b> στην κορυφή που μένει όσο κρατά το πρόβλημα — δεν είναι μήνυμα που φεύγει σε τρία δευτερόλεπτα.','p'],
  ['Ο έλεγχος δεν βασίζεται στο τι νομίζει ο browser: ο server δοκιμάζει να φτάσει <b>την ίδια την ΑΑΔΕ</b>. Ένα router χωρίς γραμμή δείχνει «συνδεδεμένος» ενώ δεν βγαίνει τίποτα έξω.','li'],
  ['Η εφαρμογή ξαναδοκιμάζει μόνη της κάθε 20 δευτερόλεπτα και η μπάρα φεύγει μόλις επανέλθει η σύνδεση· το «↻ Έλεγχος ξανά» το κάνει αμέσως.','li'],
  ['Τα <b>τοπικά</b> δεδομένα δεν επηρεάζονται: πελάτες, πληρωμές, καρτέλες και πρόχειρα διαβάζονται και γράφονται κανονικά.','li'],

  ['12. Χρήσιμα & συντομεύσεις','h2'],
  ['• Ctrl+K: αστραπιαία αναζήτηση πελάτη από παντού.  • Κάτω αριστερά στο πλαϊνό μενού: τα κουμπιά «🧭 Ξενάγηση» και «📄 Εγχειρίδιο», και οι διακόπτες φωτεινού/σκοτεινού θέματος και επεξηγήσεων (tooltips).  • Αλλαγή κωδικού από «Ρυθμίσεις».  • Όλα τα τοπικά δεδομένα (πληρωμές, ρυθμίσεις, προγράμματα, ειδοποιήσεις, μυστικά 2FA, διαπιστευτήρια AADE) αποθηκεύονται τοπικά και κρυπτογραφημένα.','p']
];
async function downloadManual(){
  if(!window.jspdf){toast('Η βιβλιοθήκη PDF δεν φόρτωσε','err');return;}
  toast('Δημιουργία εγχειριδίου…','ok');
  try{await ensureFont();
    const {jsPDF}=window.jspdf;const doc=new jsPDF({unit:'pt',format:'a4'});
    doc.addFileToVFS('DejaVuSans.ttf',FONT_B64);doc.addFont('DejaVuSans.ttf','DejaVu','normal');doc.setFont('DejaVu');
    const W=doc.internal.pageSize.getWidth(),H=doc.internal.pageSize.getHeight();const AC=[14,165,233],DK=[35,45,60],MUT=[90,100,120];const L=48,R=W-48;
    doc.setFillColor(...AC);doc.rect(0,0,W,6,'F');
    let y=64;
    const nl=(h)=>{if(y+h>H-48){doc.addPage();doc.setFillColor(...AC);doc.rect(0,0,W,6,'F');y=64;}};
    for(const [txt,kind] of MANUAL){
      if(kind==='h1'){nl(30);doc.setTextColor(...DK);doc.setFontSize(20);doc.text(txt,L,y);y+=30;}
      else if(kind==='h2'){nl(26);doc.setTextColor(...AC);doc.setFontSize(14);doc.text(txt,L,y);y+=20;}
      else{doc.setTextColor(...MUT);doc.setFontSize(11);const lines=doc.splitTextToSize(txt,R-L);for(const ln of lines){nl(16);doc.text(ln,L,y);y+=16;}y+=8;}
    }
    doc.setTextColor(...MUT);doc.setFontSize(8);doc.text('e-Timologio Pro · '+new Date().toLocaleDateString('el-GR'),L,H-24);
    doc.save('e-timologio-egheiridio.pdf');
  }catch(e){toast('Εγχειρίδιο: '+e.message,'err');}
}
// ===== Σύνδεση με web server (μόνο στην εγκατάσταση γραφείου) ================
// Το κλειδί πρόσβασης το φτιάχνει ο διαχειριστής ΣΤΟΝ SERVER· εδώ απλώς
// επικολλάται. Η επιτυχής σύνδεση γράφει το `service.json` (mode: thin), που
// είναι ό,τι διαβάζει η ίδια η εφαρμογή υπολογιστή όταν ξεκινά — γι' αυτό η
// αλλαγή ισχύει στο επόμενο άνοιγμα, και το λέμε ρητά.
async function loadLink(){
  if(!$('#lkTable'))return;                      // εγκατάσταση server: δεν υπάρχει η κάρτα
  try{
    const d=await apost({auth:'link_get'});
    if(!d.success)return;
    const st=$('#lkState');
    st.textContent=d.connected?'συνδεδεμένο':'τοπικά (offline)';
    st.className='pill'+(d.connected?' ok':'');
    $('#lkInfo').innerHTML=d.connected
      ? `Server: <b>${esc(d.url)}</b>${d.label?(' · λογαριασμός <b>'+esc(d.label)+'</b>'):''}${d.since?(' · από '+esc(d.since)):''}`
      : 'Χωρίς σύνδεση: όλα μένουν σε αυτόν τον υπολογιστή.';
    $('#lkTable tbody').innerHTML=(d.items||[]).map(i=>`<tr>
      <td>${esc(i.label||'—')}</td><td>${esc(i.vat)}</td>
      <td>${d.web_link?`<span class="muted">${esc(d.web_link)}</span>`:'<span class="muted">—</span>'}</td>
      <td class="right">${d.web_link?`<button class="ghost sm" onclick="linkCopy('${q1(d.web_link)}')">🔗 Αντιγραφή</button>
        <button class="ghost sm" onclick="window.open('${q1(d.web_link)}','_blank')">🌐 Άνοιγμα</button>`:''}</td></tr>`)
      .join('')||'<tr><td colspan="4" class="muted">Καμία εταιρεία σε αυτή την εγκατάσταση.</td></tr>';
  }catch(e){}
}
async function linkConnect(){
  const key=($('#lkKey').value||'').trim();
  if(!key){toast('Επικόλλησε το κλειδί πρόσβασης','err');return;}
  try{
    const d=await apost({auth:'link_connect',key});
    if(d.success){
      $('#lkKey').value='';
      toast('Συνδέθηκε: '+(d.label||d.url),'ok');
      // Η αλλαγή ζει στο service.json, που το διαβάζει η εφαρμογή ΟΤΑΝ ΞΕΚΙΝΑ:
      // χωρίς αυτό το μήνυμα, ο λογιστής θα περίμενε να αλλάξει κάτι τώρα.
      alert('Η σύνδεση αποθηκεύτηκε. Κλείσε και ξανάνοιξε την εφαρμογή για να δουλέψει πάνω στον server.');
      loadLink();
    }
  }catch(e){toast(e.message,'err');}
}
async function linkDisconnect(){
  if(!confirm('Επιστροφή σε τοπική λειτουργία; Τα δεδομένα που ζουν στον server μένουν εκεί.'))return;
  try{const d=await apost({auth:'link_disconnect'});
    if(d.success){toast('Επιστροφή σε τοπική λειτουργία','ok');loadLink();}
  }catch(e){toast(e.message,'err');}
}
function linkCopy(url){
  if(!url)return;
  try{navigator.clipboard.writeText(url);toast('Ο σύνδεσμος αντιγράφηκε','ok');}
  catch(e){prompt('Αντίγραψε τον σύνδεσμο:',url);}
}

// ===== Issuance notifications (TODO 91) ======================================
async function pollNotifCount(){try{const d=await api({notif_count:1});setBell(d.unread||0);}catch(e){}}

// --- Έλεγχος ΑΑΔΕ: ειδοποιήσεις και για ό,τι ΔΕΝ εκδόθηκε από εδώ ------------
// Η καμπάνα γέμιζε μόνο από εκδόσεις αυτής της εγκατάστασης. Ένα παραστατικό
// που έβγαλε ο λογιστής από αλλού, ή που εκδόθηκε απευθείας στο e-Τιμολόγιο της
// ΑΑΔΕ, δεν εμφανιζόταν ποτέ. Εδώ η εφαρμογή, κάθε φορά που έχει internet,
// συγκρίνει την τοπική cache με την πλατφόρμα (`?sync=newdocs`) και ο server
// γράφει ειδοποίηση για κάθε νέο ΜΑΡΚ. Σιωπηλό όταν δεν υπάρχει δίκτυο ή
// σύνδεση ΑΑΔΕ — ο έλεγχος δεν είναι λόγος να δει ο χρήστης σφάλμα.
let AADE_CHECK_BUSY=false;
async function checkAadeNewDocs(silent=true){
  if(AADE_CHECK_BUSY)return;
  if(navigator.onLine===false)return;
  AADE_CHECK_BUSY=true;
  try{
    const d=await api({sync:'newdocs'});
    if(d&&d.success){
      await pollNotifCount();
      if(d.discovered>0)toast(d.discovered+' νέο/α παραστατικό/ά από την ΑΑΔΕ','ok');
      else if(!silent)toast('Κανένα νέο παραστατικό στην ΑΑΔΕ','ok');
    }else if(!silent)toast('Ο έλεγχος δεν ολοκληρώθηκε','err');
  }catch(e){if(!silent)toast('Ο έλεγχος δεν ολοκληρώθηκε: '+e.message,'err');}
  finally{AADE_CHECK_BUSY=false;}
}
// Ξαναδοκίμασε μόλις επιστρέψει το δίκτυο — αυτή είναι η «σύνδεση στο internet».
window.addEventListener('online',()=>setTimeout(()=>checkAadeNewDocs(),4000));
function setBell(n){const b=$('#bellBadge');if(!b)return;n=+n||0;if(n>0){b.hidden=false;b.textContent=n>99?'99+':n;}else b.hidden=true;}
async function toggleNotifPanel(){const p=$('#notifPanel');const willOpen=p.hidden;p.hidden=!willOpen;if(willOpen)await loadNotifications();}
document.addEventListener('click',e=>{const w=document.querySelector('.bell-wrap');const p=$('#notifPanel');if(w&&p&&!w.contains(e.target))p.hidden=true;});
async function loadNotifications(){const list=$('#notifList');if(!list)return;list.innerHTML='<div class="notif-empty">Φόρτωση…</div>';
  try{const d=await api({notifications:1,limit:100});setBell(d.unread||0);renderNotifications(d.items||[]);}
  catch(e){list.innerHTML='<div class="notif-empty">Σφάλμα: '+esc(e.message)+'</div>';}}
function renderNotifications(items){const list=$('#notifList');
  if(!items.length){list.innerHTML='<div class="notif-empty">Καμία ειδοποίηση ακόμη.</div>';return;}
  list.innerHTML=items.map(n=>{
    const amt=n.amount_total!=null?fmt(n.amount_total)+' €':'';
    const who=esc(n.actor_name||n.actor_email||'');
    const buyer=esc(n.buyer_name||n.buyer_vat||'');
    const src=n.source==='scheduled'?' ⏰':(n.source==='bulk'?' 📚':(n.source==='aade'?' 🛰️':''));
    const acct=(IS_STAFF&&n.account_vat)?(' · ΑΦΜ '+esc(n.account_vat)):'';
    const seri=n.series?(' · Σειρά '+esc(n.series)+(n.aa?('/'+esc(n.aa)):'')):'';
    return `<div class="notif-item ${n.is_read?'':'unread'}" onclick="notifRead(${n.id},this)">
      <div class="nt-top"><b>${esc(n.doc_label||n.doc_type)}</b>${src}<span class="nt-amt">${amt}</span></div>
      <div class="nt-sub">${buyer?('Πελάτης: '+buyer):''}${who?(' · από '+who):''}${acct}</div>
      <div class="nt-sub">${esc(n.created_at||'')}${seri}</div>
      <div class="nt-mark">ΜΑΡΚ ${esc(n.mark)}</div>
    </div>`;}).join('');}
async function notifRead(id,el){if(el)el.classList.remove('unread');try{const d=await api({notif_read:1,id});setBell(d.unread||0);}catch(e){}}
async function notifMarkAll(){try{await api({notif_read_all:1});setBell(0);await loadNotifications();}catch(e){}}

// ===== Scheduled issuance (TODO 90) ==========================================
let SCHED_CTX=null;
function scheduleIssue(kind){
  let payload,summary;
  if(kind==='bulk'){
    const parsed=blkCollectRows(false);if(!parsed)return;const {items,errs}=parsed;
    if(!items.length){toast('Καμία έγκυρη γραμμή','err');blkCollectRows(true);return;}
    payload={bulk_issue:'1',items:JSON.stringify(items),live:1};
    summary=`📚 Μαζική έκδοση · ${items.length} παραστατικά`+(errs.length?` (${errs.length} με σφάλμα θα παραλειφθούν)`:'');
  }else{
    const lines=collectLines();if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
    const ser=$('#iSeries').value;if(!ser||ser==='__new'){toast('Επίλεξε σειρά παραστατικού','err');return;}
    const p={lines:JSON.stringify(lines),type:$('#iType').value,issue_series:ser,payment:$('#iPay').value,issue_lang:$('#iLang').value,afm:$('#iAfm').value.trim(),name:$('#iName').value,address:$('#iAddress').value,city:$('#iCity').value,zip:$('#iZip').value,live:1};
    if(ITAXES.length)p.taxes=JSON.stringify(ITAXES.map(t=>({type:t.type,category:t.category,amount:t.amount,notes:t.notes})));
    const notes=$('#iNotes').value.trim();if(notes)p.notes=notes;
    payload=p;
    const nm=$('#iName').value||$('#iAfm').value||'—';
    const tl=(typeof invLabelByValue==='function'?invLabelByValue($('#iType').value):'')||$('#iType').value;
    summary=`🧾 ${tl} · ${lines.length} γραμμές · ${nm}`;
  }
  SCHED_CTX={kind,payload,summary};
  $('#schedSummary').textContent=summary;
  $('#schResult').innerHTML='';
  const t=new Date(Date.now()+864e5);$('#schDate').value=t.toISOString().slice(0,10);$('#schTime').value='09:00';
  $('#schRec').value='none';$('#schTitle').value='';
  schedDateNote();
  schedModal.showModal();
}
// Η ΗΜΕΡΟΜΗΝΙΑ ΕΚΔΟΣΗΣ είναι η προγραμματισμένη, όχι η σημερινή. Δεν είναι
// λεπτομέρεια: το παραστατικό μπαίνει στη φορολογική περίοδο εκείνης της
// ημέρας, και ο χρήστης που «ετοιμάζει σήμερα για την 1η» πρέπει να το ξέρει
// ΠΡΙΝ πατήσει, όχι όταν δει τον ΜΑΡΚ.
function schedDateNote(){
  const el=$('#schedWhenNote');if(!el)return;
  const date=$('#schDate').value,time=$('#schTime').value||'09:00';
  if(!date){el.innerHTML='';return;}
  const rec=$('#schRec').value;
  const human=isoToDmy(date)+' '+time;
  el.innerHTML=`📅 Το παραστατικό θα φέρει <b>ημερομηνία έκδοσης ${esc(isoToDmy(date))}</b> — την ημέρα που θα εκδοθεί, όχι τη σημερινή.`+
    (rec&&rec!=='none'
      ? ` Σε κάθε επανάληψη (${esc(SCHED_REC[rec]||rec)}) η ημερομηνία έκδοσης είναι η ημέρα της εκτέλεσης.`
      : ` Προγραμματισμένη εκτέλεση: <b>${esc(human)}</b>.`);
}
async function confirmSchedule(){if(!SCHED_CTX)return;
  const date=$('#schDate').value,time=$('#schTime').value||'09:00';
  if(!date){toast('Επίλεξε ημερομηνία','err');return;}
  const runAt=date+' '+time;const when=new Date(runAt.replace(' ','T'));
  if(isNaN(when.getTime())){toast('Μη έγκυρη ημερομηνία/ώρα','err');return;}
  if(when.getTime()<Date.now()-60000&&!confirm('Η ώρα είναι στο παρελθόν — θα εκτελεστεί στο επόμενο πέρασμα του runner. Συνέχεια;'))return;
  const body=new URLSearchParams();
  body.set('sched_add','1');body.set('sched_payload',JSON.stringify(SCHED_CTX.payload));
  body.set('run_at',runAt);body.set('recurrence',$('#schRec').value);body.set('kind',SCHED_CTX.kind);
  body.set('title',($('#schTitle').value||'').trim());if(ACCOUNT)body.set('account',ACCOUNT);
  $('#schResult').innerHTML='<span class="spin"></span> Αποθήκευση…';
  try{const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'},body});
    const d=await r.json();
    if(d.success){$('#schResult').innerHTML=`<div class="card"><span class="pill ok">Προγραμματίστηκε</span> για ${esc(d.run_at)}${d.recurrence&&d.recurrence!=='none'?' · επανάληψη: '+esc(d.recurrence):''}<div class="hint" style="margin-top:6px">📅 Ημερομηνία έκδοσης του παραστατικού: <b>${esc(isoToDmy(String(d.run_at).slice(0,10)))}</b></div></div>`;
      toast('Προγραμματίστηκε','ok');setTimeout(()=>{try{schedModal.close();}catch(e){}showView('schedule');},900);}
    else $('#schResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#schResult').innerHTML='';toast('Προγραμματισμός: '+e.message,'err');}}
const SCHED_STATUS={pending:'Σε αναμονή',done:'Ολοκληρώθηκε',failed:'Απέτυχε',running:'Εκτελείται',cancelled:'Ακυρώθηκε'};
const SCHED_REC={none:'—',daily:'Καθημερινά',weekly:'Εβδομαδιαία',monthly:'Μηνιαία'};
async function loadSchedule(){const tb=$('#schedTable tbody');if(!tb)return;tb.innerHTML='<tr><td colspan="7"><span class="spin"></span> Φόρτωση…</td></tr>';
  const note=$('#schedNote');if(note)note.innerHTML=IS_STAFF
    ?'👁 Ως λογιστής/διαχειριστής βλέπεις τα προγράμματα <b>όλων</b> των εταιριών. Για να προγραμματίσεις για συγκεκριμένη εταιρία, επίλεξέ την από τον διακόπτη «Λογαριασμός» πάνω και χρησιμοποίησε το «⏰ Προγραμματισμός» στην Έκδοση/Μαζική.'
    :'Βλέπεις τα προγράμματα της επιχείρησής σου.';
  try{const d=await api({sched_list:1});renderSchedule(d.jobs||[]);}
  catch(e){tb.innerHTML='<tr><td colspan="7">Σφάλμα: '+esc(e.message)+'</td></tr>';}}
function renderSchedule(jobs){attachColumnFilters('schedTable');const tb=$('#schedTable tbody');$('#schedCount').textContent=jobs.length?(jobs.length+' προγράμματα'):'';
  if(!jobs.length){tb.innerHTML='<tr><td colspan="7" class="muted" style="text-align:center;padding:18px">Κανένα προγραμματισμένο παραστατικό. Χρησιμοποίησε το «⏰ Προγραμματισμός» στην Έκδοση ή τη Μαζική έκδοση.</td></tr>';return;}
  tb.innerHTML=jobs.map(j=>{
    const lr=j.last_result;let res='';
    if(lr)res=lr.success?`<span class="pill ok">ΜΑΡΚ ${esc(lr.mark||'')||'OK'}</span>`:`<span class="pill bad" title="${esc(lr.error||'')}">Σφάλμα</span>`;
    const acct=(IS_STAFF&&j.account_vat)?`<div class="ln-desc">ΑΦΜ ${esc(j.account_vat)}</div>`:'';
    return `<tr>
      <td>${esc(j.title||('#'+j.id))}${acct}</td>
      <td>${j.kind==='bulk'?'📚 Μαζική':'🧾 Παραστατικό'}</td>
      <td>${esc(j.run_at||'')}</td>
      <td>${SCHED_REC[j.recurrence]||esc(j.recurrence)}</td>
      <td><span class="sched-status ${esc(j.status)}">${SCHED_STATUS[j.status]||esc(j.status)}</span></td>
      <td>${j.last_run_at?esc(j.last_run_at)+' '+res:'<span class="muted">—</span>'}</td>
      <td>${j.status==='pending'
            ?`<button class="danger sm" onclick="cancelJob(${j.id})">Ακύρωση</button>`
            :`<button class="ghost sm" onclick="deleteJob(${j.id})" title="Διαγραφή από τη λίστα">🗑</button>`}</td>
    </tr>`;}).join('');}
async function cancelJob(id){if(!confirm('Ακύρωση αυτού του προγράμματος;'))return;
  try{const d=await api({sched_cancel:1,id});if(d.success){toast('Ακυρώθηκε','ok');loadSchedule();}else toast('Δεν ακυρώθηκε (ίσως εκτελέστηκε ήδη)','warn');}
  catch(e){toast('Ακύρωση: '+e.message,'err');}}
// Οι τελειωμένες εργασίες (ακυρωμένες/εκτελεσμένες/αποτυχημένες) φεύγουν από τη
// λίστα — οι εκκρεμείς πρώτα ακυρώνονται, δεν διαγράφονται κατά λάθος.
async function deleteJob(id){
  try{const d=await api({sched_delete:1,id});if(d.success){loadSchedule();}else toast('Δεν διαγράφηκε','warn');}
  catch(e){toast('Διαγραφή: '+e.message,'err');}}
async function clearFinishedJobs(){
  if(!confirm('Διαγραφή ΟΛΩΝ των ολοκληρωμένων και ακυρωμένων προγραμμάτων;'))return;
  try{const d=await api({sched_delete:1,id:0});toast((d.deleted||0)+' διαγράφηκαν','ok');loadSchedule();}
  catch(e){toast('Καθαρισμός: '+e.message,'err');}}

// Ματάκι σε ΚΑΘΕ πεδίο κωδικού (αλλαγή κωδικού, νέος χρήστης), χωρίς να
// πειραχτεί η κάθε φόρμα ξεχωριστά — ίδια συμπεριφορά με την οθόνη σύνδεσης.
function addEyes(root){
  (root||document).querySelectorAll('input[type=password]').forEach(inp=>{
    if(inp.parentElement && inp.parentElement.classList.contains('pw'))return;
    const wrap=document.createElement('div');wrap.className='pw';
    inp.parentNode.insertBefore(wrap,inp);wrap.appendChild(inp);
    const btn=document.createElement('button');
    btn.type='button';btn.className='eye';btn.textContent='👁';
    btn.title='Εμφάνιση κωδικού';btn.setAttribute('aria-label','Εμφάνιση κωδικού');
    btn.onclick=()=>{const show=inp.type==='password';inp.type=show?'text':'password';
      btn.textContent=show?'🙈':'👁';
      btn.title=btn.ariaLabel=show?'Απόκρυψη κωδικού':'Εμφάνιση κωδικού';inp.focus();};
    wrap.appendChild(btn);
  });
}

(async()=>{addEyes();loadGridLayouts();await initAccounts();loadInvTypes();await loadProductList();loadCustomers();showView('issue');prewarmAll();
  pollNotifCount();setInterval(pollNotifCount,60000);
  // Ο έλεγχος ΑΑΔΕ αργεί (ζωντανή κλήση): δεν πρέπει να καθυστερεί το πρώτο
  // άνοιγμα, γι' αυτό τρέχει μετά — και μετά κάθε μισή ώρα.
  setTimeout(()=>checkAadeNewDocs(),9000);
  setInterval(()=>checkAadeNewDocs(),1800000);
  // First-time visitors: gently offer the tour once.
  if(!localStorage.getItem('etim_tour_done'))setTimeout(()=>{try{if(confirm('Καλωσήρθες! Θέλεις μια γρήγορη ξενάγηση 30 δευτερολέπτων στην εφαρμογή;'))startTour();else localStorage.setItem('etim_tour_done','1');}catch(e){}},900);
})();
</script>
</body>
</html>
