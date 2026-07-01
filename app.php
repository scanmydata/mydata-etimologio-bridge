<?php
// Clear OPcache on every request so file changes take effect immediately.
if (function_exists('opcache_reset')) { opcache_reset(); }

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
$__resetToken = trim($_GET['reset'] ?? '');
if (!$__user || $__resetToken !== '') {
    require __DIR__ . '/authview.php';   // outputs the auth page and exits
    exit;
}
$__role = $__user['role'];
$__email = $__user['email'];
$__business = $__user['business_name'];
?>
<!DOCTYPE html>
<html lang="el">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>e-Timologio Pro</title>
<style>
  :root{
    --bg:#0b1220; --panel:#131f33; --panel2:#18263d; --line:#2b3b54;
    --txt:#e6edf6; --muted:#93a4bd; --accent:#38bdf8; --accent2:#0ea5e9;
    --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --chip:#0b2942;
    --radius:14px; --shadow:0 10px 30px rgba(0,0,0,.4); --side:230px;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0;font-family:system-ui,'Segoe UI',Roboto,Arial,sans-serif;background:var(--bg);color:var(--txt);font-size:14px}
  a{color:var(--accent)}
  .app{display:grid;grid-template-columns:var(--side) 1fr;grid-template-rows:auto 1fr;grid-template-areas:"side top" "side main";height:100vh}
  /* Sidebar */
  aside{grid-area:side;background:linear-gradient(180deg,#0c1626,#0b1220);border-right:1px solid var(--line);display:flex;flex-direction:column;min-height:0}
  .brand{padding:18px 18px 10px;font-size:18px;font-weight:800;letter-spacing:.3px}
  .brand span{color:var(--accent)}
  nav.menu{padding:8px;overflow:auto;flex:1}
  .nav-item{display:flex;align-items:center;gap:11px;padding:11px 13px;border-radius:10px;cursor:pointer;color:var(--muted);font-weight:600;margin-bottom:2px}
  .nav-item .ic{width:20px;text-align:center;font-size:16px}
  .nav-item:hover{background:var(--panel2);color:var(--txt)}
  .nav-item.active{background:var(--accent2);color:#04222f}
  .side-foot{padding:12px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
  /* Topbar */
  header{grid-area:top;display:flex;align-items:center;gap:14px;padding:12px 18px;border-bottom:1px solid var(--line);background:rgba(10,18,32,.85);backdrop-filter:blur(6px)}
  .search-trigger{display:flex;align-items:center;gap:8px;background:var(--panel2);border:1px solid var(--line);border-radius:10px;padding:8px 12px;color:var(--muted);cursor:text;min-width:260px}
  .search-trigger kbd{margin-left:auto;background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:1px 6px;font-size:11px}
  .grow{flex:1}
  main{grid-area:main;overflow:auto;padding:20px}
  /* Controls */
  select,input,button,textarea{font:inherit;color:var(--txt);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:9px 11px;outline:none}
  select:focus,input:focus,textarea:focus{border-color:var(--accent)}
  button{cursor:pointer;transition:.15s}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent2);border-color:var(--accent2);color:#04222f;font-weight:700}
  button.primary:hover{background:var(--accent)}
  button.danger{border-color:var(--bad);color:#fecaca}
  button.danger:hover{background:rgba(239,68,68,.15)}
  button.ghost{background:transparent}
  button.sm{padding:5px 9px;font-size:12px}
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
  table{width:100%;border-collapse:collapse;margin-top:14px;font-size:13px}
  th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}
  th{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.4px}
  tbody tr:hover{background:#1b2c45}
  tr.clickable{cursor:pointer}
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
  .toast{position:fixed;bottom:20px;right:20px;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);padding:12px 16px;border-radius:10px;box-shadow:var(--shadow);z-index:90;max-width:380px;opacity:0;transform:translateY(10px);transition:.25s}
  .toast.show{opacity:1;transform:none}
  .toast.ok{border-left-color:var(--ok)} .toast.err{border-left-color:var(--bad)}
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
</style>
</head>
<body>
<div class="app">
  <aside>
    <div class="brand">e-Timologio <span>Pro</span></div>
    <nav class="menu" id="menu">
      <div class="nav-item active" data-view="stats"><span class="ic">📊</span> Στατιστικά</div>
      <div class="nav-item" data-view="customers"><span class="ic">👥</span> Πελάτες</div>
      <div class="nav-item" data-view="card"><span class="ic">📇</span> Καρτέλα</div>
      <div class="nav-item" data-view="products"><span class="ic">📦</span> Είδη</div>
      <div class="nav-item" data-view="issue"><span class="ic">🧾</span> Έκδοση</div>
      <div class="nav-item" data-view="delivery"><span class="ic">🚚</span> Δελτίο</div>
      <div class="nav-item" data-view="cancel"><span class="ic">↩️</span> Ακύρωση</div>
      <div class="nav-item" data-view="settings"><span class="ic">⚙️</span> Ρυθμίσεις</div>
      <?php if ($__role === 'master'): ?>
      <div class="nav-item" data-view="admin"><span class="ic">🛡️</span> Διαχείριση</div>
      <?php endif; ?>
    </nav>
    <div class="side-foot">🔒 Τοπικά δεδομένα κρυπτογραφημένα<br>Πάτα <b>Ctrl+K</b> για γρήγορη αναζήτηση</div>
  </aside>

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
    <button class="ghost sm" onclick="logout()" title="Αποσύνδεση" style="margin-left:6px">Έξοδος</button>
  </header>

  <main>
    <!-- STATS -->
    <section class="view active" id="view-stats">
      <h2 class="title">Στατιστικά</h2><p class="sub">Σύνοψη τζίρου & παραστατικών από την ΑΑΔΕ.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <div class="seg" id="statPeriod">
            <button data-p="month" class="on">Τρέχων μήνας</button>
            <button data-p="preMonth">Προηγ. μήνας</button>
            <button data-p="year">Τρέχον έτος</button>
          </div>
          <button class="ghost" onclick="loadStats()">↻ Ανανέωση</button>
        </div>
        <div class="cards" id="statCards" style="margin-top:14px"></div>
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
        <table id="custTable"><thead><tr><th>Κωδ.</th><th>ΑΦΜ</th><th>Επωνυμία</th><th>Πόλη</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- CARD -->
    <section class="view" id="view-card">
      <h2 class="title">Καρτέλα πελάτη</h2><p class="sub">Τιμολόγια ΑΑΔΕ + τοπικές πληρωμές + τρέχον υπόλοιπο.</p>
      <div class="panel">
        <div class="row">
          <div class="field"><label>ΑΦΜ πελάτη</label><input id="cardVat" placeholder="ΑΦΜ"></div>
          <div class="field"><label>Από</label><input id="cardFrom" type="date"></div>
          <div class="field"><label>Έως</label><input id="cardTo" type="date"></div>
          <button class="primary" onclick="loadCard()">Φόρτωση</button>
          <button class="ghost" onclick="openPaymentModal()">+ Πληρωμή</button>
          <button class="ghost" onclick="ledgerPdf()">📄 PDF καρτέλας</button>
          <button class="ghost" onclick="zipCustomerInvoices()">🗜️ ZIP παραστατικών</button>
        </div>
        <div id="cardHead" style="margin-top:12px"></div>
        <div class="cards" id="cardCards"></div>
        <table id="cardTable"><thead><tr><th>Ημ/νία</th><th>Κίνηση</th><th>Στοιχεία</th><th class="num">Χρέωση</th><th class="num">Πίστωση</th><th class="num">Υπόλοιπο</th><th></th></tr></thead><tbody></tbody></table>
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

    <!-- ISSUE -->
    <section class="view" id="view-issue">
      <h2 class="title">Έκδοση παραστατικού</h2><p class="sub">Με αυτόματη συμπλήρωση πελάτη από Taxisnet.</p>
      <div class="panel">
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
          <div class="field grow" style="min-width:280px"><label>Τύπος παραστατικού <span class="hint">(μόνο με ενεργή σειρά)</span></label>
            <select id="iType" onchange="showIssueCls()"><option>…</option></select></div>
          <div class="field"><label>Πληρωμή</label>
            <select id="iPay"><option value="3">Μετρητά</option><option value="1">Τραπεζικός λογ.</option>
              <option value="5">Επί πιστώσει</option><option value="6">Web Banking</option>
              <option value="7" selected>POS</option><option value="8">IRIS</option></select></div>
          <div class="grow"></div>
          <button class="ghost sm" type="button" onclick="openProductModal()">+ Νέο είδος</button>
          <button class="ghost sm" type="button" onclick="addLine()">+ Γραμμή</button>
        </div>
        <table id="iLines"><thead><tr><th style="width:40%">Είδος</th><th style="width:78px">Ποσότητα</th><th class="num">Τιμή μον. (€)</th><th style="width:80px" class="num">Έκπτ. %</th><th style="width:70px" class="num">ΦΠΑ</th><th class="num">Σύνολο</th><th></th></tr></thead><tbody></tbody></table>
        <datalist id="prodList"></datalist>
        <div id="iCls" class="hint" style="margin-top:6px"></div>
        <div class="right" style="margin-top:6px;font-size:15px;font-weight:700">Καθαρή αξία: <span id="iNet">0,00</span> €</div>
        <div class="row" style="margin-top:8px;align-items:center">
          <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="iLive" style="width:auto"> <span style="color:#fca5a5;font-weight:700">LIVE έκδοση (υποβολή ΑΑΔΕ)</span></label>
          <div class="grow"></div>
          <button class="ghost" onclick="submitInvoice(false)">💾 Πρόχειρο</button>
          <button class="primary" onclick="submitInvoice(true)">Έκδοση</button>
        </div>
        <div id="issueResult" style="margin-top:14px"></div>
      </div>
    </section>

    <!-- DELIVERY NOTE -->
    <section class="view" id="view-delivery">
      <h2 class="title">Δελτίο Αποστολής / Επιστροφής</h2>
      <p class="sub">Διακίνηση αγαθών (9.x). Για επιστροφή επίλεξε σκοπό «Επιστροφή».</p>
      <div class="panel">
        <div class="row">
          <div class="field"><label>Τύπος δελτίου</label>
            <select id="dnType"><option value="503">9.3 Δελτίο Αποστολής</option><option value="504">9.1 Συσχετιζόμενο</option><option value="505">9.2 Συγκεντρωτικό</option></select></div>
          <div class="field"><label>Σκοπός διακίνησης</label>
            <select id="dnPurpose">
              <option value="1">Πώληση</option><option value="2">Πώληση για Λογ. Τρίτων</option>
              <option value="3">Δειγματισμός</option><option value="4">Έκθεση</option>
              <option value="5">Επιστροφή</option><option value="6">Φύλαξη</option>
              <option value="8">Ενδοδιακίνηση</option><option value="9">Αγορά</option>
              <option value="19">Λοιπές Διακινήσεις</option><option value="20">Μεταφορές</option>
            </select></div>
          <div class="field"><label>ΑΦΜ παραλήπτη</label><input id="dnAfm" placeholder="9 ψηφία" oninput="dnLookup()"></div>
          <div class="field grow"><label>Επωνυμία</label><input id="dnName"></div>
        </div>
        <div class="row">
          <div class="field"><label>Όχημα</label><input id="dnVehicle" placeholder="π.χ. ΙΧΥ-1234"></div>
          <div class="field"><label>Ημ/νία αποστολής</label><input id="dnDate" type="date"></div>
          <div class="field"><label>Ώρα</label><input id="dnTime" type="time"></div>
        </div>
        <div class="row" style="margin:8px 0 2px;align-items:center">
          <strong>Γραμμές ειδών</strong><div class="grow"></div>
          <button class="ghost sm" type="button" onclick="addDnLine()">+ Γραμμή</button>
        </div>
        <table id="dnLines"><thead><tr><th style="width:48%">Είδος</th><th style="width:90px">Ποσότητα</th><th class="num">Τιμή μον. (€)</th><th class="num">Σύνολο</th><th></th></tr></thead><tbody></tbody></table>
        <div class="row" style="justify-content:flex-end;margin-top:6px"><span class="muted">Καθαρή αξία:&nbsp;</span><strong id="dnNet">0,00</strong>&nbsp;€</div>
        <div class="row">
          <div class="field grow"><label>Διεύθυνση παράδοσης</label><input id="dnDStreet" placeholder="Οδός"></div>
          <div class="field"><label>Αριθ.</label><input id="dnDNumber"></div>
          <div class="field"><label>Πόλη</label><input id="dnDCity"></div>
          <div class="field"><label>Τ.Κ.</label><input id="dnDZip"></div>
        </div>
        <div class="row" style="margin-top:8px;align-items:center">
          <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="dnLive" style="width:auto"> <span style="color:#fca5a5;font-weight:700">LIVE έκδοση δελτίου</span></label>
          <div class="grow"></div>
          <button class="ghost" onclick="submitDelivery(false)">💾 Πρόχειρο</button>
          <button class="primary" onclick="submitDelivery(true)">Έκδοση δελτίου</button>
        </div>
        <div id="dnResult" style="margin-top:14px"></div>
      </div>
    </section>

    <!-- CANCEL -->
    <section class="view" id="view-cancel">
      <h2 class="title">Ακύρωση παραστατικού</h2>
      <p class="sub">Η ακύρωση γίνεται με έκδοση <b>πιστωτικού συσχετιζόμενου</b> — χρειάζεται το ΜΑΡΚ του αρχικού.</p>
      <div class="panel">
        <div class="row">
          <div class="field grow"><label>ΜΑΡΚ αρχικού παραστατικού</label><input id="cxMark" placeholder="π.χ. 400013843901315"></div>
          <div class="field grow"><label>Αιτιολογία (προαιρετικό)</label><input id="cxReason" placeholder="Λόγος ακύρωσης"></div>
        </div>
        <div class="row" style="margin-top:8px;align-items:center">
          <label style="display:flex;gap:8px;align-items:center"><input type="checkbox" id="cxLive" style="width:auto"> <span style="color:#fca5a5;font-weight:700">LIVE έκδοση πιστωτικού</span></label>
          <div class="grow"></div>
          <button class="ghost" onclick="doCredit(false)">💾 Πρόχειρο πιστωτικό</button>
          <button class="danger" onclick="doCredit(true)">Έκδοση πιστωτικού (ακύρωση)</button>
        </div>
        <div id="cxResult" style="margin-top:14px"></div>
        <p class="hint">Επιλέγεται αυτόματα 5.1 (Συσχετιζόμενο) για τιμολόγια ή 11.4 (Συσχ.) για λιανική.</p>
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
        <strong>🏢 Συνδεδεμένοι λογαριασμοί AADE</strong>
        <p class="sub" style="margin-top:4px">Τα διαπιστευτήρια e-timologio αποθηκεύονται κρυπτογραφημένα και ρυθμίζονται από τον διαχειριστή.</p>
        <table id="settAccts"><thead><tr><th>ΑΦΜ</th><th>Ετικέτα</th><th>Username</th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <?php if ($__role === 'master'): ?>
    <!-- ADMIN -->
    <section class="view" id="view-admin">
      <h2 class="title">🛡️ Διαχείριση επιχειρήσεων</h2><p class="sub">Έγκριση εγγραφών, διαχείριση χρηστών και σύνδεση διαπιστευτηρίων AADE.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between">
          <strong>Χρήστες</strong>
          <div class="row">
            <button class="ghost" onclick="loadAdmin()">↻ Ανανέωση</button>
            <button class="primary" onclick="openUserModal()">+ Νέα επιχείρηση</button>
          </div>
        </div>
        <table id="adminUsers"><thead><tr><th>Επωνυμία</th><th>Email</th><th>Ρόλος</th><th>Κατάσταση</th><th>Λογ. AADE</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>
    <?php endif; ?>
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

<!-- Product modal -->
<dialog id="prodModal"><div class="modal-body">
  <div class="modal-head">📦 <span id="prodModalTitle">Νέο είδος</span></div>
  <div class="row"><div class="field"><label>Κωδικός *</label><input id="pdCode"></div>
    <div class="field"><label>Τύπος</label><select id="pdType"><option value="2">Υπηρεσία</option><option value="1">Αγαθό</option></select></div></div>
  <div class="row" style="margin-top:8px"><div class="field grow"><label>Περιγραφή *</label><input id="pdDesc"></div></div>
  <div class="row"><div class="field grow"><label>Κατηγορία</label><select id="pdCategory"></select></div>
    <div class="field"><label>ΦΠΑ</label><select id="pdVat">
      <option value="1">24%</option><option value="2">13%</option><option value="3">6%</option>
      <option value="5">9%</option><option value="7">0%</option><option value="8">Απαλλ.</option></select></div>
    <div class="field"><label>Μον. μέτρ.</label><select id="pdUnit">
      <option value="1">Τεμάχιο</option><option value="2">Κιλό</option><option value="3">Λίτρο</option>
      <option value="4">Μέτρο</option><option value="7">Άλλο</option></select></div>
    <div class="field"><label>Τιμή (€)</label><input id="pdPrice" type="number" step="0.01" value="0"></div></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="prodModal.close()">Άκυρο</button>
    <button class="primary" onclick="saveProduct()">Αποθήκευση</button>
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
  <div class="modal-head">💶 Καταχώρηση πληρωμής</div>
  <div class="row"><div class="field grow"><label>Πελάτης (ΑΦΜ)</label><input id="pmVat" readonly></div>
    <div class="field"><label>Ποσό (€)</label><input id="pmAmount" type="number" step="0.01" required></div></div>
  <div class="row"><div class="field"><label>Ημ/νία</label><input id="pmDate" type="date" required></div>
    <div class="field"><label>Τρόπος</label><select id="pmMethod"><option value="3">Μετρητά</option><option value="1">Τραπεζικός</option><option value="6">Web Banking</option><option value="7">POS</option><option value="8">IRIS</option><option value="4">Επιταγή</option></select></div></div>
  <div class="field" style="margin-top:8px"><label>Σημειώσεις</label><input id="pmNotes" placeholder="π.χ. έναντι τιμολογίου…"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button type="button" class="ghost" onclick="payModal.close()">Άκυρο</button>
    <button type="submit" class="primary">Αποθήκευση</button></div>
</form></dialog>

<?php if ($__role === 'master'): ?>
<!-- Admin: create user -->
<dialog id="userModal"><div class="modal-body">
  <div class="modal-head">🏢 Νέα επιχείρηση</div>
  <div class="field grow"><label>Επωνυμία επιχείρησης *</label><input id="uName"></div>
  <div class="row" style="margin-top:8px"><div class="field grow"><label>Email *</label><input id="uEmail" type="email"></div>
    <div class="field"><label>Κωδικός * (≥ 8)</label><input id="uPass" type="password"></div></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button class="ghost" onclick="userModal.close()">Άκυρο</button>
    <button class="primary" onclick="createUser()">Δημιουργία</button></div>
</div></dialog>

<!-- Admin: manage AADE accounts for a user -->
<dialog id="acctModal"><div class="modal-body" style="max-width:720px">
  <div class="modal-head">🏢 Λογαριασμοί AADE — <span id="amUser"></span></div>
  <table id="amList"><thead><tr><th>ΑΦΜ</th><th>Ετικέτα</th><th>Username</th><th></th></tr></thead><tbody></tbody></table>
  <div class="row" style="margin-top:14px;align-items:flex-end">
    <div class="field"><label>ΑΦΜ</label><input id="amVat" style="width:120px"></div>
    <div class="field"><label>Ετικέτα</label><input id="amLabel" style="width:140px"></div>
    <div class="field"><label>Username</label><input id="amUsername" style="width:140px"></div>
    <div class="field"><label>Subscription key</label><input id="amKey" style="width:220px"></div>
    <button class="primary" onclick="addAccount()">+ Προσθήκη</button>
  </div>
  <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="ghost" onclick="acctModal.close()">Κλείσιμο</button></div>
</div></dialog>
<?php endif; ?>

<!-- Command palette -->
<div id="palette"><div class="pal-box">
  <input id="palInput" placeholder="Αναζήτηση πελάτη (ΑΦΜ ή επωνυμία)… ↵ για καρτέλα">
  <div class="pal-results" id="palResults"></div>
</div></div>

<div class="toast" id="toast"></div>

<script src="https://cdn.jsdelivr.net/npm/jspdf@2.5.1/dist/jspdf.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/jspdf-autotable@3.8.2/dist/jspdf.plugin.autotable.min.js"></script>
<script>
const API='etimologio.php';
const ROLE=<?= json_encode($__role) ?>;
let ACCOUNT='';
const $=s=>document.querySelector(s);
const fmt=n=>(Number(n)||0).toLocaleString('el-GR',{minimumFractionDigits:2,maximumFractionDigits:2});
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const q1=s=>String(s??'').replace(/'/g,"\\'");
function toast(m,t=''){const e=$('#toast');e.className='toast show '+t;e.textContent=m;clearTimeout(e._t);e._t=setTimeout(()=>e.className='toast',3400);}

async function api(params){const q=new URLSearchParams(params);if(ACCOUNT)q.set('account',ACCOUNT);
  const r=await fetch(API+'?'+q.toString());const txt=await r.text();
  try{return JSON.parse(txt);}catch(e){throw new Error(txt.slice(0,200));}}

// Navigation
function showView(v){
  document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.view===v));
  document.querySelectorAll('.view').forEach(x=>x.classList.remove('active'));
  $('#view-'+v).classList.add('active');
  if(v==='stats')loadStats();
  if(v==='customers')loadCustomers();
  if(v==='products'){loadProducts();loadCategories();loadCatCls();}
  if(v==='delivery'){if(!$('#dnDate').value)$('#dnDate').value=new Date().toISOString().slice(0,10);if(!$('#dnLines tbody').children.length)addDnLine();}
  if(v==='issue'){if(!$('#iLines tbody').children.length)addLine();loadIssueTypes();}
  if(v==='settings')loadSettings();
  if(v==='admin')loadAdmin();
}
document.querySelectorAll('.nav-item').forEach(n=>n.onclick=()=>showView(n.dataset.view));

// Accounts
async function initAccounts(){
  try{const d=await api({accounts:1});const sel=$('#account');sel.innerHTML='';
    (d.accounts||[]).forEach(a=>{const o=document.createElement('option');o.value=a.vat;o.textContent=a.label+' ('+a.vat+')';sel.appendChild(o);});
    if(!(d.accounts||[]).length){const o=document.createElement('option');o.textContent='— κανένας λογαριασμός AADE —';sel.appendChild(o);}
    ACCOUNT=d.active||(d.accounts[0]&&d.accounts[0].vat)||'';sel.value=ACCOUNT;
    sel.onchange=()=>{ACCOUNT=sel.value;loadProductList();const v=document.querySelector('.nav-item.active').dataset.view;showView(v);};
  }catch(e){toast('Λογαριασμοί: '+e.message,'err');}
}

// Auth: logout, settings, admin
async function logout(){try{await fetch(API+'?auth=logout',{method:'POST'});}catch(e){}location.href='app.php';}
async function changePassword(){const o=$('#cpOld').value,n=$('#cpNew').value,n2=$('#cpNew2').value;
  if(n!==n2){$('#cpResult').textContent='Οι νέοι κωδικοί δεν ταιριάζουν.';return;}
  try{const b=new URLSearchParams({auth:'change_password',old_password:o,password:n});
    const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b});const d=await r.json();
    if(d.success){$('#cpResult').textContent='';toast('Ο κωδικός άλλαξε','ok');['cpOld','cpNew','cpNew2'].forEach(i=>$('#'+i).value='');}
    else $('#cpResult').textContent=d.error||'Αποτυχία';
  }catch(e){$('#cpResult').textContent='Σφάλμα δικτύου';}}
async function loadSettings(){try{const d=await api({accounts:1});
  $('#settAccts tbody').innerHTML=(d.accounts||[]).map(a=>`<tr><td>${esc(a.vat)}</td><td>${esc(a.label)}</td><td class="muted">•••</td></tr>`).join('')||'<tr><td colspan="3" class="muted">Δεν έχει συνδεθεί λογαριασμός AADE.</td></tr>';
}catch(e){}}
async function apost(params){const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(params)});return r.json();}
async function loadAdmin(){try{const d=await apost({auth:'admin_users'});renderAdmin(d.users||[]);}catch(e){toast('Διαχείριση: '+e.message,'err');}}
function renderAdmin(users){$('#adminUsers tbody').innerHTML=users.map(u=>{
  const st=u.status==='active'?'<span class="pill ok">ενεργός</span>':u.status==='pending'?'<span class="pill warn">εκκρεμεί</span>':'<span class="pill bad">ανενεργός</span>';
  const isMaster=u.role==='master';
  let act='';
  if(!isMaster){
    if(u.status==='pending')act+=`<button class="primary sm" onclick="approveUser(${u.id})">Έγκριση</button> `;
    if(u.status!=='disabled')act+=`<button class="danger sm" onclick="setStatus(${u.id},'disabled')">Απενεργ.</button> `;
    else act+=`<button class="ghost sm" onclick="setStatus(${u.id},'active')">Ενεργοπ.</button> `;
    act+=`<button class="ghost sm" onclick="resetPw(${u.id})">Reset</button>`;
  }
  const accBtn=isMaster?'<span class="muted">—</span>':`<button class="ghost sm" onclick="openAcctModal(${u.id},'${q1(u.business_name||u.email)}')">Διαχείριση</button>`;
  return `<tr><td>${esc(u.business_name||'—')}${isMaster?' 🛡️':''}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td>${st}</td><td>${accBtn}</td><td class="right">${act}</td></tr>`;
}).join('')||'<tr><td colspan="6" class="muted">Καμία εγγραφή.</td></tr>';}
async function approveUser(id){if(!confirm('Έγκριση χρήστη;'))return;const d=await apost({auth:'admin_approve',user_id:id});if(d.success){toast('Εγκρίθηκε','ok');loadAdmin();}else toast(d.error||'Αποτυχία','err');}
async function setStatus(id,s){const d=await apost({auth:'admin_set_status',user_id:id,status:s});if(d.success){toast('Ενημερώθηκε','ok');loadAdmin();}else toast(d.error||'Αποτυχία','err');}
async function resetPw(id){const d=await apost({auth:'admin_reset_pw',user_id:id});if(d.success){prompt('Σύνδεσμος επαναφοράς (δώστε τον στον χρήστη — ισχύει 24ω):',d.reset_link);}else toast(d.error||'Αποτυχία','err');}
function openUserModal(){['uName','uEmail','uPass'].forEach(i=>$('#'+i).value='');userModal.showModal();}
async function createUser(){const name=$('#uName').value.trim(),email=$('#uEmail').value.trim(),pass=$('#uPass').value;
  if(!name||!email||pass.length<8){toast('Συμπλήρωσε επωνυμία, email και κωδικό ≥ 8','err');return;}
  const d=await apost({auth:'admin_create_user',email,password:pass,business_name:name});
  if(d.success){userModal.close();toast('Η επιχείρηση δημιουργήθηκε','ok');loadAdmin();}else toast(d.error||'Αποτυχία','err');}
let AM_USER=0;
async function openAcctModal(userId,name){AM_USER=userId;$('#amUser').textContent=name;['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');await loadUserAccounts();acctModal.showModal();}
async function loadUserAccounts(){const d=await apost({auth:'admin_user_accounts',user_id:AM_USER});
  $('#amList tbody').innerHTML=(d.accounts||[]).map(a=>`<tr><td>${esc(a.vat)}</td><td>${esc(a.label)}</td><td>${esc(a.username)}</td><td class="right"><button class="danger sm" onclick="delAccount(${a.id})">✕</button></td></tr>`).join('')||'<tr><td colspan="4" class="muted">Κανένας λογαριασμός.</td></tr>';}
async function addAccount(){const vat=$('#amVat').value.trim();if(!/^\d{9}$/.test(vat)){toast('ΑΦΜ 9 ψηφίων','err');return;}
  const d=await apost({auth:'admin_add_account',user_id:AM_USER,vat,label:$('#amLabel').value,username:$('#amUsername').value,subkey:$('#amKey').value});
  if(d.success){['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');toast('Προστέθηκε','ok');loadUserAccounts();}else toast(d.error||'Αποτυχία','err');}
async function delAccount(id){if(!confirm('Διαγραφή λογαριασμού AADE;'))return;const d=await apost({auth:'admin_delete_account',account_id:id});if(d.success){toast('Διαγράφηκε','ok');loadUserAccounts();}else toast(d.error||'Αποτυχία','err');}

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
  }catch(e){$('#statCards').innerHTML='';toast('Στατιστικά: '+e.message,'err');}
}

// Invoice-type catalogue (verbal labels) — loaded once, used by stats/PDF/issue.
let INVTYPES=[],INVBYCODE={},INVBYVALUE={};
async function loadInvTypes(){if(INVTYPES.length)return INVTYPES;
  try{const d=await api({invoice_types:1});INVTYPES=d.invoice_types||[];
    INVBYCODE={};INVBYVALUE={};INVTYPES.forEach(t=>{if(t.code)INVBYCODE[t.code]=t;INVBYVALUE[String(t.value)]=t;});
  }catch(e){}return INVTYPES;}
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

// Customers (cached + instant client-side filter)
let ALL_CUSTOMERS=[];
$('#custSearch').addEventListener('input',renderCustomers);
function custFields(c){return {vat:c.vat||c.customer_vat||'',name:c.name||c.customer_name||'',code:c.code||c.customer_code||'',city:c.city||'',address:c.address||'',zip:c.zip||''};}
function renderCustomers(){
  const term=($('#custSearch').value||'').toLowerCase().trim();
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.code+' '+c.city).toLowerCase().includes(term));
  $('#custCount').textContent=rows.length+' / '+ALL_CUSTOMERS.length+' πελάτες';
  $('#custTable tbody').innerHTML=rows.slice(0,500).map(c=>
    `<tr class="clickable" onclick="openCard('${q1(c.vat)}','${q1(c.name)}')"><td>${esc(c.code)}</td><td>${esc(c.vat)}</td><td>${esc(c.name)}</td><td>${esc(c.city)}</td>
      <td class="right"><button class="primary sm" title="Έκδοση παραστατικού" onclick="event.stopPropagation();issueFor('${q1(c.vat)}','${q1(c.name)}')">🧾 Έκδοση</button>
      <button class="ghost sm" onclick="event.stopPropagation();editCustomer('${q1(c.vat)}','${q1(c.name)}','${q1(c.address)}','${q1(c.city)}','${q1(c.zip)}')">✎</button>
      <button class="ghost sm" onclick="event.stopPropagation();openCard('${q1(c.vat)}','${q1(c.name)}')">Καρτέλα →</button></td></tr>`).join('')||'<tr><td colspan="5" class="muted">Κανένα αποτέλεσμα.</td></tr>';
}
async function loadCustomers(){await cachedThenSync('customers',rows=>{ALL_CUSTOMERS=rows;renderCustomers();});}

// Customer modal (create/edit)
let CUST_EDIT=null;
function custTab(t){$('#custTabAfm').style.display=t==='afm'?'':'none';$('#custTabPersonal').style.display=t==='personal'?'':'none';document.querySelectorAll('#custTabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));}
function openCustomerModal(){CUST_EDIT=null;$('#custModalTitle').textContent='Νέος πελάτης';['cmAfm','cmName','cmAddress','cmCity','cmZip','cpName','cpAddress','cpCity','cpZip','cpEmail','cpPhone'].forEach(id=>$('#'+id).value='');$('#cpJob').value='ΙΔΙΩΤΗΣ';custTab('afm');$('#custModal').showModal();}
function editCustomer(vat,name,address,city,zip){CUST_EDIT={vat};$('#custModalTitle').textContent='Επεξεργασία πελάτη';custTab('afm');$('#cmAfm').value=vat;$('#cmName').value=name;$('#cmAddress').value=address;$('#cmCity').value=city;$('#cmZip').value=zip;$('#custModal').showModal();}
async function cmLookup(){const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}
  try{const d=await api({afm});const c=d.customer||d.info||d;$('#cmName').value=c.name||c.customer_name||'';$('#cmAddress').value=c.address||'';$('#cmCity').value=c.city||'';$('#cmZip').value=c.zip||'';toast('Στοιχεία αντλήθηκαν','ok');}catch(e){toast('Taxisnet: '+e.message,'err');}}
async function saveCustomer(){
  try{let d;
    if(CUST_EDIT){d=await api({update_customer:1,update_customer_vat:CUST_EDIT.vat,update_name:$('#cmName').value,update_address:$('#cmAddress').value,update_city:$('#cmCity').value,update_zip:$('#cmZip').value});}
    else if($('#custTabPersonal').style.display!=='none'){
      if(!$('#cpName').value||!$('#cpCity').value||!$('#cpZip').value){toast('Συμπλήρωσε όνομα/πόλη/ΤΚ','err');return;}
      d=await api({create_personal_customer:1,cust_name:$('#cpName').value,cust_address:$('#cpAddress').value,cust_city:$('#cpCity').value,cust_zip:$('#cpZip').value,cust_job_description:$('#cpJob').value,cust_email:$('#cpEmail').value,cust_phone1:$('#cpPhone').value});
    }else{const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}d=await api({afm});}
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    $('#custModal').close();toast('Αποθηκεύτηκε','ok');loadCustomers(true);
  }catch(e){toast('Πελάτης: '+e.message,'err');}
}

// Customer card
function defaultRange(){const y=new Date().getFullYear();if(!$('#cardFrom').value)$('#cardFrom').value=y+'-01-01';if(!$('#cardTo').value)$('#cardTo').value=y+'-12-31';}
function openCard(vat,name){showView('card');$('#cardVat').value=vat;defaultRange();loadCard();}
let CARD={};
async function loadCard(){const vat=$('#cardVat').value.trim();if(!vat){toast('Δώσε ΑΦΜ','err');return;}defaultRange();
  $('#cardCards').innerHTML='<div class="card"><div class="v"><span class="spin"></span></div></div>';$('#cardTable tbody').innerHTML='';
  try{const d=await api({ledger:1,buyer_vat:vat,issue_date_from:$('#cardFrom').value,issue_date_to:$('#cardTo').value});if(!d.success)throw new Error(d.error||'σφάλμα');CARD=d;
    const balCls=d.balance>0.005?'pos':'zero';
    $('#cardHead').innerHTML=`<strong>${esc(d.customer_name||vat)}</strong> <span class="muted">ΑΦΜ ${esc(vat)}</span>`;
    $('#cardCards').innerHTML=`<div class="card"><div class="k">Τζίρος</div><div class="v">${fmt(d.total_invoiced)} €</div></div>`+
      `<div class="card"><div class="k">Πληρωμές</div><div class="v" style="color:#86efac">${fmt(d.total_paid)} €</div></div>`+
      `<div class="card"><div class="k">Υπόλοιπο</div><div class="v balance ${balCls}">${fmt(d.balance)} €</div></div>`;
    $('#cardTable tbody').innerHTML=d.entries.map(e=>{
      if(e.kind==='invoice')return `<tr><td>${esc(e.date)}</td><td><span class="pill" title="${esc(invName(e.type))}">${esc(e.type||'')}</span> ${esc(invName(e.type))}</td><td>ΜΑΡΚ ${esc(e.mark)}</td><td class="num">${fmt(e.debit)}</td><td class="num"></td><td class="num">${fmt(e.balance)}</td>
        <td class="right">${e.mark?`<a href="${API}?account=${ACCOUNT}&mark=${esc(e.mark)}&pdf_raw=1" target="_blank">PDF</a> <button class="danger sm" title="Ακύρωση με πιστωτικό" onclick="cancelFromCard('${q1(e.mark)}')">↩ Ακύρωση</button>`:''}</td></tr>`;
      return `<tr><td>${esc(e.date)}</td><td><span class="pill ok">Πληρωμή</span></td><td>${esc(e.notes||'')}</td><td class="num"></td><td class="num">${fmt(e.credit)}</td><td class="num">${fmt(e.balance)}</td><td class="right"><button class="danger sm" onclick="delPayment(${e.payment_id})">✕</button></td></tr>`;
    }).join('')||'<tr><td colspan="7" class="muted">Καμία κίνηση.</td></tr>';
  }catch(e){$('#cardCards').innerHTML='';toast('Καρτέλα: '+e.message,'err');}
}
function cancelFromCard(mark){showView('cancel');$('#cxMark').value=mark;toast('ΜΑΡΚ φορτώθηκε στην Ακύρωση','ok');}

// Payments
function openPaymentModal(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  $('#pmVat').value=vat;$('#pmAmount').value=CARD.balance>0?CARD.balance.toFixed(2):'';$('#pmDate').value=new Date().toISOString().slice(0,10);$('#pmNotes').value='';$('#payModal').showModal();}
async function savePayment(ev){ev.preventDefault();
  try{const d=await api({add_payment:1,buyer_vat:$('#pmVat').value,customer_name:CARD.customer_name||'',pay_amount:$('#pmAmount').value,pay_method:$('#pmMethod').value,pay_date:$('#pmDate').value,pay_notes:$('#pmNotes').value});
    if(!d.success)throw new Error(d.error||'σφάλμα');$('#payModal').close();toast('Πληρωμή καταχωρήθηκε','ok');loadCard();
  }catch(e){toast('Πληρωμή: '+e.message,'err');}}
async function delPayment(id){if(!confirm('Διαγραφή πληρωμής;'))return;try{const d=await api({delete_payment_id:id});if(!d.success)throw new Error('απέτυχε');toast('Διαγράφηκε','ok');loadCard();}catch(e){toast(e.message,'err');}}

// Products
let PRODUCTS=[],CATEGORIES=[];
async function loadProducts(){await cachedThenSync('products',rows=>{PRODUCTS=rows;renderProducts();});}
function renderProducts(){const f=($('#prodFilter').value||'').toLowerCase();
  const rows=PRODUCTS.filter(p=>!f||JSON.stringify(p).toLowerCase().includes(f));
  $('#prodTable tbody').innerHTML=rows.map(p=>{const code=p.product_code||p.code||'',desc=p.description||'',cat=p.category||'',vat=p.vat||p.vat_category||'',price=p.unit_price||p.price||'';
    return `<tr><td>${esc(code)}</td><td>${esc(desc)}</td><td>${esc(cat)}</td><td>${esc(vat)}</td><td class="num">${price!==''?fmt(price):''}</td>
      <td class="right"><button class="ghost sm" onclick="editProduct('${q1(code)}','${q1(desc)}')">✎</button> <button class="danger sm" onclick="delProduct('${q1(code)}')">✕</button></td></tr>`;}).join('')||'<tr><td colspan="6" class="muted">Κανένα είδος.</td></tr>';}
async function loadCategories(){try{const d=await api({list_product_categories:1});CATEGORIES=d.product_categories||d.categories||d.items||[];const sel=$('#pdCategory');if(sel){sel.innerHTML='<option value="">—</option>'+CATEGORIES.map(c=>`<option value="${esc(c.id||c.category_id||'')}">${esc(c.name||c.category||c.category_name||'')}</option>`).join('');}}catch(e){}}
let PRODMAP={};
const VATPCT={1:24,2:13,3:6,4:17,5:9,6:4,7:0,8:0};
function vatPct(cat){const p=VATPCT[parseInt(cat,10)];return p===undefined?24:p;}
async function loadProductList(){try{const d=await api({list_products:1});const dl=$('#prodList');dl.innerHTML='';PRODMAP={};
  (d.products||[]).forEach(p=>{const code=p.product_code||p.code;if(!code)return;const desc=p.description||'';const vat=p.vat||p.vat_category||'';
    PRODMAP[code]={desc,vat};const o=document.createElement('option');o.value=code;o.textContent=desc;dl.appendChild(o);});
}catch(e){}}
let PROD_EDIT=null;
function openProductModal(){PROD_EDIT=null;$('#prodModalTitle').textContent='Νέο είδος';['pdCode','pdDesc'].forEach(i=>$('#'+i).value='');$('#pdPrice').value='0';$('#pdCode').readOnly=false;loadCategories();$('#prodModal').showModal();}
function editProduct(code,desc){PROD_EDIT=code;$('#prodModalTitle').textContent='Επεξεργασία είδους';$('#pdCode').value=code;$('#pdCode').readOnly=true;$('#pdDesc').value=desc;loadCategories();$('#prodModal').showModal();}
async function saveProduct(){if(!$('#pdCode').value||!$('#pdDesc').value){toast('Κωδικός & περιγραφή απαιτούνται','err');return;}
  const base={product_type:$('#pdType').value,product_description:$('#pdDesc').value,product_category:$('#pdCategory').value,vat_category:$('#pdVat').value,unit:$('#pdUnit').value,unit_price:$('#pdPrice').value};
  try{let d;if(PROD_EDIT)d=await api({update_product_code:PROD_EDIT,...base});else d=await api({new_product:1,product_code:$('#pdCode').value,...base});
    if(d.success===false)throw new Error(d.error||'σφάλμα');$('#prodModal').close();toast('Αποθηκεύτηκε','ok');loadProducts();loadProductList();
  }catch(e){toast('Είδος: '+e.message,'err');}}
async function delProduct(code){if(!confirm('Διαγραφή είδους '+code+';'))return;try{const d=await api({delete_product_code:code});if(d.success===false)throw new Error(d.error||'');toast('Διαγράφηκε','ok');loadProducts();}catch(e){toast(e.message,'err');}}

// Category-level classifications (χαρακτηρισμοί ανά κατηγορία, myDATA §9)
let CAT_CLS=[],INV_TYPES=[],CLS_OPTS={};
async function loadCatCls(){try{const d=await api({category_cls:1});CAT_CLS=d.categories||[];INV_TYPES=d.invoice_types||[];renderCatCls();}catch(e){toast('Χαρακτηρισμοί: '+e.message,'err');}}
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
async function loadIssueTypes(){await loadInvTypes();
  try{const d=await api({list_series:1});const seen=new Set(),opts=[];
    (d.series||[]).forEach(s=>{const v=String(s.invoice_type_code||'').trim();if(v&&!seen.has(v)){seen.add(v);opts.push({v,label:invLabelByValue(v)!==v?invLabelByValue(v):(s.invoice_type||v)});}});
    const sel=$('#iType');const cur=sel.value;
    if(opts.length){sel.innerHTML=opts.map(o=>`<option value="${esc(o.v)}">${esc(o.label)}</option>`).join('');
      if(opts.some(o=>o.v===cur))sel.value=cur;
      sel.title='';
    }else{sel.innerHTML='<option value="">— καμία ενεργή σειρά —</option>';toast('Δεν υπάρχει ενεργή σειρά. Δημιούργησε σειρά για να εκδώσεις.','err');}
    showIssueCls();
  }catch(e){}}

// Customer autocomplete on the issue form (searchable + fills all fields)
let acEl=null;
function custAc(el){acEl=el;const term=(el.value||'').toLowerCase().trim();const panel=$('#iCustAc');
  if(!ALL_CUSTOMERS.length){loadCustomers();}
  let rows=ALL_CUSTOMERS.map(custFields);
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.code+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  if(!rows.length){panel.classList.remove('open');return;}
  panel.innerHTML=rows.map(c=>`<div class="ac-row" onmousedown="pickCust('${q1(c.vat)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function pickCust(vat){const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===vat);if(!c)return;
  $('#iAfm').value=c.vat;$('#iName').value=c.name;$('#iAddress').value=c.address||'';$('#iCity').value=c.city||'';$('#iZip').value=c.zip||'';
  $('#iCustAc').classList.remove('open');showIssueCls();}
document.addEventListener('click',e=>{const p=$('#iCustAc');if(p&&!e.target.closest('#iCustAc')&&e.target!==$('#iAfm')&&e.target!==$('#iName'))p.classList.remove('open');});
// Pre-fill the issue form for a specific customer (from the Πελάτες list)
function issueFor(vat,name){showView('issue');$('#iAfm').value=vat;$('#iName').value=name||'';
  if(/^\d{9}$/.test(vat))lookupAfm();toast('Έκδοση για '+(name||vat),'ok');}

let afmTimer;
function lookupAfm(){clearTimeout(afmTimer);afmTimer=setTimeout(async()=>{const afm=$('#iAfm').value.trim();if(!/^\d{9}$/.test(afm))return;
  try{const d=await api({afm});const c=d.customer||d.info||d;if(c){$('#iName').value=c.name||c.customer_name||$('#iName').value;$('#iAddress').value=c.address||$('#iAddress').value;$('#iCity').value=c.city||$('#iCity').value;$('#iZip').value=c.zip||$('#iZip').value;toast('Στοιχεία πελάτη OK','ok');}}catch(e){}},400);}
// Lines editor (multi-line) — code picker shows description + VAT per line
function lineRowHtml(code,qty,price,disc){const p=PRODMAP[code]||{};return `<tr>
  <td><input class="ln-code" list="prodList" value="${esc(code)}" oninput="lineCodeChange(this)" placeholder="κωδικός / αναζήτηση" style="width:100%"><div class="ln-desc">${esc(p.desc||'')}</div></td>
  <td><input class="ln-qty" type="number" step="0.01" min="0" value="${esc(qty)}" oninput="recalcLines()" style="width:72px"></td>
  <td class="num"><input class="ln-price" type="number" step="0.01" min="0" value="${esc(price)}" oninput="recalcLines()" placeholder="0.00" style="width:100px;text-align:right"></td>
  <td class="num"><input class="ln-disc" type="number" step="0.01" min="0" max="100" value="${esc(disc||'')}" oninput="recalcLines()" placeholder="0" style="width:70px;text-align:right"></td>
  <td class="num ln-vat">${p.vat!==undefined&&p.vat!==''?vatPct(p.vat)+'%':'—'}</td>
  <td class="num ln-total">0,00</td>
  <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove();recalcLines()">✕</button></td></tr>`;}
function addLine(code='ΥΠ001',qty=1,price='',disc=''){$('#iLines tbody').insertAdjacentHTML('beforeend',lineRowHtml(code,qty,price,disc));recalcLines();}
function lineCodeChange(inp){const row=inp.closest('tr');const p=PRODMAP[inp.value.trim()]||{};
  row.querySelector('.ln-desc').textContent=p.desc||'';
  row.querySelector('.ln-vat').textContent=(p.vat!==undefined&&p.vat!=='')?vatPct(p.vat)+'%':'—';
  if(p.desc&&!row.querySelector('.ln-price').value&&p.price)row.querySelector('.ln-price').value=p.price;
  recalcLines();}
function collectLines(){const out=[];document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const code=r.querySelector('.ln-code').value.trim();const qty=parseFloat(r.querySelector('.ln-qty').value)||0;const price=parseFloat(r.querySelector('.ln-price').value)||0;const disc=parseFloat(r.querySelector('.ln-disc').value)||0;
  if(code&&price>0&&qty>0){const o={code,qty,price};if(disc>0)o.disc=disc;out.push(o);}});return out;}
function recalcLines(){let net=0;document.querySelectorAll('#iLines tbody tr').forEach(r=>{const qty=parseFloat(r.querySelector('.ln-qty').value)||0;const price=parseFloat(r.querySelector('.ln-price').value)||0;const disc=parseFloat(r.querySelector('.ln-disc').value)||0;const t=qty*price*(1-Math.min(disc,100)/100);r.querySelector('.ln-total').textContent=fmt(t);net+=t;});$('#iNet').textContent=fmt(net);showIssueCls();}

async function submitInvoice(viaIssue){const live=viaIssue&&$('#iLive').checked;
  if(live&&!confirm('Έκδοση ΠΡΑΓΜΑΤΙΚΟΥ παραστατικού στην ΑΑΔΕ. Συνέχεια;'))return;
  const lines=collectLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
  const p={lines:JSON.stringify(lines),type:$('#iType').value,payment:$('#iPay').value,afm:$('#iAfm').value.trim(),name:$('#iName').value,address:$('#iAddress').value,city:$('#iCity').value,zip:$('#iZip').value};if(live)p.live=1;
  $('#issueResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success){$('#issueResult').innerHTML=d.live?`<div class="card"><span class="pill ok">Εκδόθηκε</span><div style="margin-top:8px">ΜΑΡΚ <strong>${esc(d.mark)}</strong> · ΑΑ ${esc(d.aa)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a></div></div>`:`<div class="card"><span class="pill warn">Πρόχειρο</span><div style="margin-top:8px">Temp ID ${esc(d.temp_id)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € <span class="muted">(δεν υποβλήθηκε)</span></div></div>`;toast(d.live?'Εκδόθηκε':'Πρόχειρο OK','ok');}
    else $('#issueResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#issueResult').innerHTML='';toast('Έκδοση: '+e.message,'err');}}

// Classifications hint in Έκδοση (based on the first line's product)
let clsTimer;
function showIssueCls(){clearTimeout(clsTimer);clsTimer=setTimeout(async()=>{
  const first=document.querySelector('#iLines .ln-code');const prod=first?first.value.trim():'';const type=$('#iType').value;
  if(!prod){$('#iCls').textContent='';return;}
  try{const d=await api({classifications:1,product:prod,type});
    if(d.success&&d.classifications.length)$('#iCls').innerHTML='🏷️ '+d.classifications.map(c=>`<span class="pill">${esc(c.code)} · ${esc(c.category_name)}</span>`).join(' ');
    else $('#iCls').innerHTML='<span class="muted">Χωρίς ορισμένο χαρακτηρισμό (θα χρησιμοποιηθεί ο προεπιλεγμένος).</span>';
  }catch(e){$('#iCls').textContent='';}
},300);}

// Delivery / return note
let dnTimer;
function dnLookup(){clearTimeout(dnTimer);dnTimer=setTimeout(async()=>{const afm=$('#dnAfm').value.trim();if(!/^\d{9}$/.test(afm))return;
  try{const d=await api({afm});const c=d.customer||d.info||d;if(c){$('#dnName').value=c.name||c.customer_name||$('#dnName').value;if(!$('#dnDStreet').value)$('#dnDStreet').value=c.address||'';if(!$('#dnDCity').value)$('#dnDCity').value=c.city||'';if(!$('#dnDZip').value)$('#dnDZip').value=c.zip||'';}}catch(e){}},400);}
// Delivery lines editor (multi-line)
function dnRowHtml(code,qty,price){return `<tr>
  <td><input class="dl-code" list="prodList" value="${esc(code)}" oninput="recalcDn()" placeholder="κωδικός είδους" style="width:100%"></td>
  <td><input class="dl-qty" type="number" step="0.01" min="0" value="${esc(qty)}" oninput="recalcDn()" style="width:80px"></td>
  <td class="num"><input class="dl-price" type="number" step="0.01" min="0" value="${esc(price)}" oninput="recalcDn()" placeholder="0.00" style="width:110px;text-align:right"></td>
  <td class="num dl-total">0,00</td>
  <td class="right"><button class="danger sm" type="button" onclick="this.closest('tr').remove();recalcDn()">✕</button></td></tr>`;}
function addDnLine(code='ΥΠ001',qty=1,price=''){$('#dnLines tbody').insertAdjacentHTML('beforeend',dnRowHtml(code,qty,price));recalcDn();}
function collectDnLines(){const out=[];document.querySelectorAll('#dnLines tbody tr').forEach(r=>{
  const code=r.querySelector('.dl-code').value.trim();const qty=parseFloat(r.querySelector('.dl-qty').value)||0;const price=parseFloat(r.querySelector('.dl-price').value)||0;
  if(code&&price>0&&qty>0)out.push({code,qty,price});});return out;}
function recalcDn(){let net=0;document.querySelectorAll('#dnLines tbody tr').forEach(r=>{const qty=parseFloat(r.querySelector('.dl-qty').value)||0;const price=parseFloat(r.querySelector('.dl-price').value)||0;const t=qty*price;r.querySelector('.dl-total').textContent=fmt(t);net+=t;});$('#dnNet').textContent=fmt(net);}
async function submitDelivery(viaIssue){const live=viaIssue&&$('#dnLive').checked;
  if(live&&!confirm('Έκδοση ΠΡΑΓΜΑΤΙΚΟΥ δελτίου στην ΑΑΔΕ. Συνέχεια;'))return;
  const lines=collectDnLines();
  if(!lines.length){toast('Πρόσθεσε τουλάχιστον μία γραμμή (είδος + ποσότητα + τιμή)','err');return;}
  const p={delivery_note:1,dn_type:$('#dnType').value,move_purpose:$('#dnPurpose').value,afm:$('#dnAfm').value.trim(),name:$('#dnName').value,
    lines:JSON.stringify(lines),vehicle:$('#dnVehicle').value,dispatch_date:$('#dnDate').value,dispatch_time:$('#dnTime').value,
    deliv_street:$('#dnDStreet').value,deliv_number:$('#dnDNumber').value,deliv_city:$('#dnDCity').value,deliv_zip:$('#dnDZip').value};
  if($('#dnPurpose').value==='5')p.reverse=1;
  if(live)p.live=1;
  $('#dnResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success)$('#dnResult').innerHTML=`<div class="card"><span class="pill ${d.live?'ok':'warn'}">${d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο'}</span><div style="margin-top:8px">Τύπος ${esc(d.type)} · σκοπός ${esc($('#dnPurpose option:checked').textContent)} · σύνολο ${fmt(d.amount_total)} €<br>${d.live?`ΜΑΡΚ <strong>${esc(d.mark)}</strong> · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a>`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`,toast(d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο','ok');
    else $('#dnResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#dnResult').innerHTML='';toast('Δελτίο: '+e.message,'err');}}

// Cancel / credit note
async function doCredit(viaIssue){const mark=$('#cxMark').value.trim();if(!mark){toast('Δώσε ΜΑΡΚ','err');return;}
  const live=viaIssue&&$('#cxLive').checked;
  if(live&&!confirm('Έκδοση ΠΡΑΓΜΑΤΙΚΟΥ πιστωτικού (ακύρωση) στην ΑΑΔΕ. Συνέχεια;'))return;
  const p={credit_note:1,cancel_mark:mark,reason:$('#cxReason').value};if(live)p.live=1;
  $('#cxResult').innerHTML='<span class="spin"></span> Υποβολή…';
  try{const d=await api(p);
    if(d.success){const o=d.original||{};$('#cxResult').innerHTML=`<div class="card"><span class="pill ${d.live?'ok':'warn'}">${d.live?'Πιστωτικό εκδόθηκε':'Πρόχειρο πιστωτικό'}</span>
      <div style="margin-top:8px">Τύπος ${esc(d.credit_type)} (5.1/11.4) · Συσχ. ΜΑΡΚ ${esc(d.correlated_mark)}<br>Αρχικό: ${esc(o.type||'')} · ΑΦΜ ${esc(o.buyer_vat||'')} · καθαρή ${fmt(o.net||0)} €<br>${d.live?`Νέο ΜΑΡΚ <strong>${esc(d.mark)}</strong> · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a>`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`;
      toast(d.live?'Πιστωτικό εκδόθηκε':'Πρόχειρο πιστωτικό OK','ok');}
    else $('#cxResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#cxResult').innerHTML='';toast('Πιστωτικό: '+e.message,'err');}}

// ZIP downloads (browser handles the file)
function zipUrl(params){const q=new URLSearchParams(params);if(ACCOUNT)q.set('account',ACCOUNT);return API+'?'+q.toString();}
function zipCustomerInvoices(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε καρτέλα','err');return;}
  toast('Λήψη ZIP παραστατικών…','ok');window.location=zipUrl({invoices_zip:1,buyer_vat:vat,issue_date_from:$('#cardFrom').value,issue_date_to:$('#cardTo').value});}
function zipAllInvoices(){const y=new Date().getFullYear();toast('Λήψη ZIP (έτος '+y+')…','ok');
  window.location=zipUrl({invoices_zip:1,issue_date_from:y+'-01-01',issue_date_to:y+'-12-31'});}

// Customer ledger PDF (χρεώσεις-πιστώσεις) via jsPDF + DejaVu (Greek) font
let FONT_B64=null;
function abToB64(buf){let bin='';const b=new Uint8Array(buf),c=0x8000;for(let i=0;i<b.length;i+=c)bin+=String.fromCharCode.apply(null,b.subarray(i,i+c));return btoa(bin);}
async function ensureFont(){if(FONT_B64)return;const r=await fetch('https://cdn.jsdelivr.net/npm/dejavu-fonts-ttf@2.37.3/ttf/DejaVuSans.ttf');FONT_B64=abToB64(await r.arrayBuffer());}
async function ledgerPdf(){
  if(!CARD||!CARD.entries){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  if(!window.jspdf){toast('Η βιβλιοθήκη PDF δεν φόρτωσε','err');return;}
  toast('Δημιουργία PDF…','ok');
  try{
    await ensureFont();await loadInvTypes();
    const {jsPDF}=window.jspdf;const doc=new jsPDF({unit:'pt',format:'a4'});
    doc.addFileToVFS('DejaVuSans.ttf',FONT_B64);doc.addFont('DejaVuSans.ttf','DejaVu','normal');doc.setFont('DejaVu');
    const W=doc.internal.pageSize.getWidth();const AC=[14,165,233],DK=[35,45,60],MUT=[120,130,145];const L=40,R=W-40;
    // ---- Header band ----
    doc.setFillColor(...AC);doc.rect(0,0,W,6,'F');
    doc.setTextColor(...DK);doc.setFontSize(17);doc.text('ΚΑΡΤΕΛΑ ΠΕΛΑΤΗ',L,44);
    doc.setFontSize(9);doc.setTextColor(...MUT);
    doc.text('Επιχείρηση ΑΦΜ: '+ACCOUNT,L,60);
    doc.text('Περίοδος: '+$('#cardFrom').value+' έως '+$('#cardTo').value,R,44,{align:'right'});
    doc.text('Ημ/νία έκδοσης: '+new Date().toLocaleDateString('el-GR'),R,60,{align:'right'});
    // ---- Customer details block ----
    const cust=(ALL_CUSTOMERS.map(custFields).find(c=>c.vat===CARD.customer_vat))||{};
    doc.setDrawColor(...AC);doc.setLineWidth(0.8);doc.roundedRect(L,74,R-L,58,4,4,'S');
    doc.setTextColor(...DK);doc.setFontSize(12);doc.text(CARD.customer_name||cust.name||'—',L+12,94);
    doc.setFontSize(9);doc.setTextColor(...MUT);
    const addr=[cust.address,cust.city,cust.zip].filter(Boolean).join(', ');
    doc.text('ΑΦΜ: '+(CARD.customer_vat||'')+(cust.code?('   ·   Κωδ.: '+cust.code):''),L+12,110);
    doc.text('Διεύθυνση: '+(addr||'—'),L+12,124);
    // ---- Movements table (Χρέωση / Πίστωση / Υπόλοιπο) ----
    let totD=0,totC=0;
    const body=CARD.entries.map(e=>{totD+=(+e.debit||0);totC+=(+e.credit||0);
      const docLbl=e.kind==='invoice'
        ? ((invLabel(e.type)!==e.type?invLabel(e.type):(e.type||'Παραστατικό'))+(e.mark?('  ·  ΜΑΡΚ '+e.mark):''))
        : ('Πληρωμή'+(e.notes?('  ·  '+e.notes):''));
      return [e.date||'',docLbl,e.debit?fmt(e.debit):'',e.credit?fmt(e.credit):'',fmt(e.balance)];});
    doc.autoTable({startY:146,
      head:[['Ημ/νία','Παραστατικό','Χρέωση','Πίστωση','Υπόλοιπο']],
      body,
      foot:[['','Σύνολα',fmt(totD),fmt(totC),fmt(CARD.balance)]],
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
    const bpos=CARD.balance>0.005;doc.setTextColor(...(bpos?[190,40,40]:[22,120,60]));
    doc.setFontSize(12);doc.text('Υπόλοιπο: '+fmt(CARD.balance)+' €',R,y,{align:'right'});
    doc.save('kartela-'+CARD.customer_vat+'.pdf');
    toast('PDF καρτέλας έτοιμο','ok');
  }catch(e){toast('PDF: '+e.message,'err');}
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

// boot
(async()=>{await initAccounts();loadInvTypes();loadProductList();loadCustomers();loadStats();})();
</script>
</body>
</html>
