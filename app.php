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
    --ok:#22c55e; --warn:#f59e0b; --bad:#ef4444; --chip:#0b2942; --hover:#1b2c45;
    --radius:14px; --shadow:0 10px 30px rgba(0,0,0,.4); --side:230px;
  }
  /* Light theme — activated by data-theme="light" on <html> (toggle bottom-left). */
  :root[data-theme="light"]{
    --bg:#f1f5fb; --panel:#ffffff; --panel2:#eef3fa; --line:#d5deea;
    --txt:#1a2637; --muted:#5b6b84; --accent:#0284c7; --accent2:#0369a1;
    --ok:#16a34a; --warn:#d97706; --bad:#dc2626; --chip:#e5eefb; --hover:#e8eef7;
    --shadow:0 10px 30px rgba(30,50,90,.12);
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
  #themeToggle{position:fixed;left:16px;bottom:16px;z-index:60;display:inline-flex;align-items:center;gap:8px;
    background:var(--panel);border:1px solid var(--line);border-radius:999px;padding:5px 12px 5px 6px;cursor:pointer;
    box-shadow:var(--shadow);color:var(--muted);font-size:12px;user-select:none}
  #themeToggle:hover{border-color:var(--accent)}
  #themeToggle .tt-switch{position:relative;width:40px;height:22px;border-radius:999px;background:var(--panel2);border:1px solid var(--line);flex:0 0 auto}
  #themeToggle .tt-knob{position:absolute;top:1px;left:1px;width:18px;height:18px;border-radius:50%;background:var(--accent);
    display:flex;align-items:center;justify-content:center;font-size:11px;transition:transform .2s,background .2s}
  :root[data-theme="light"] #themeToggle .tt-knob{transform:translateX(18px)}
  /* Lightweight CSS tooltips for elements carrying data-tip */
  [data-tip]{position:relative}
  [data-tip]:hover::after{content:attr(data-tip);position:absolute;left:50%;bottom:calc(100% + 8px);transform:translateX(-50%);
    background:#0f1b2e;color:#e6edf6;border:1px solid var(--line);border-radius:8px;padding:6px 9px;font-size:12px;
    white-space:nowrap;z-index:80;box-shadow:0 6px 20px rgba(0,0,0,.35);pointer-events:none}
  [data-tip]:hover::before{content:'';position:absolute;left:50%;bottom:calc(100% + 2px);transform:translateX(-50%);
    border:6px solid transparent;border-top-color:#0f1b2e;z-index:80;pointer-events:none}
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
  /* Colored action buttons (distinct at a glance) */
  button.add{background:rgba(34,197,94,.16);border-color:#16a34a;color:#bbf7d0;font-weight:700}
  button.add:hover{background:rgba(34,197,94,.28)}
  button.tax{background:rgba(245,158,11,.16);border-color:#d97706;color:#fcd34d;font-weight:700}
  button.tax:hover{background:rgba(245,158,11,.28)}
  button.info{background:rgba(56,189,248,.16);border-color:var(--accent2);color:#bae6fd;font-weight:700}
  button.info:hover{background:rgba(56,189,248,.28)}
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
  table.sortable thead th{cursor:pointer;user-select:none;white-space:nowrap}
  table.sortable thead th:hover{color:var(--accent)}
  tbody tr:hover{background:var(--hover)}
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
  .toast{position:fixed;top:20px;right:20px;background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--accent);padding:12px 16px;border-radius:10px;box-shadow:var(--shadow);z-index:90;max-width:380px;opacity:0;transform:translateY(-10px);transition:.25s}
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
      <div class="nav-item active" data-view="issue"><span class="ic">🧾</span> Έκδοση</div>
      <div class="nav-item" data-view="bulk"><span class="ic">📚</span> Μαζική</div>
      <div class="nav-item" data-view="customers"><span class="ic">👥</span> Πελάτες</div>
      <div class="nav-item" data-view="card"><span class="ic">📇</span> Καρτέλα</div>
      <div class="nav-item" data-view="delivery"><span class="ic">🚚</span> Δελτίο</div>
      <div class="nav-item" data-view="products"><span class="ic">📦</span> Είδη</div>
      <div class="nav-item" data-view="series"><span class="ic">🔢</span> Σειρές</div>
      <div class="nav-item" data-view="drafts"><span class="ic">📝</span> Πρόχειρα</div>
      <div class="nav-item" data-view="cancel"><span class="ic">↩️</span> Ακύρωση</div>
      <div class="nav-item" data-view="stats"><span class="ic">📊</span> Στατιστικά</div>
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
    <section class="view" id="view-stats">
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
        <table id="custTable" class="sortable"><thead><tr>
          <th onclick="sortCustomers('code')" id="cs-code">Κωδ.</th>
          <th onclick="sortCustomers('vat')" id="cs-vat">ΑΦΜ</th>
          <th onclick="sortCustomers('name')" id="cs-name">Επωνυμία</th>
          <th onclick="sortCustomers('city')" id="cs-city">Πόλη</th>
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

    <!-- SERIES -->
    <section class="view" id="view-series">
      <h2 class="title">Σειρές παραστατικών</h2><p class="sub">Δημιουργία & διαχείριση σειρών ανά τύπο παραστατικού (όπως στο e-timologio). Κάθε τύπος χρειάζεται τουλάχιστον μία σειρά για να εκδοθεί.</p>
      <div class="panel">
        <div class="row" style="justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap">
          <div class="row" style="gap:10px;align-items:flex-end;flex-wrap:wrap">
            <div class="field"><label>Τύπος παραστατικού</label><select id="srType" style="min-width:280px"></select></div>
            <div class="field"><label>Κωδικός σειράς</label><input id="srCode" placeholder="π.χ. ΔΑ" style="width:120px" maxlength="10"></div>
            <div class="field"><label>Αρχικό Α/Α</label><input id="srAa" type="number" min="1" value="1" style="width:90px"></div>
            <div class="field grow"><label>Περιγραφή (προαιρετικό)</label><input id="srDesc" placeholder="Περιγραφή"></div>
            <button class="primary" onclick="createSeriesUI()">+ Δημιουργία σειράς</button>
          </div>
          <button class="ghost" onclick="loadSeriesView()">↻ Ανανέωση</button>
        </div>
        <div id="srResult" style="margin-top:10px"></div>
        <table id="srTable" style="margin-top:12px"><thead><tr><th>Τύπος παραστατικού</th><th>Σειρά</th><th>Αρχικό Α/Α</th><th>Περιγραφή</th><th></th></tr></thead><tbody></tbody></table>
      </div>
    </section>

    <!-- ISSUE -->
    <section class="view active" id="view-issue">
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
          <div class="field grow" style="min-width:240px"><label>Τύπος παραστατικού <span class="hint">(μόνο με ενεργή σειρά)</span></label>
            <select id="iType" onchange="issueTypeChange()"><option>…</option></select></div>
          <div class="field"><label>Σειρά</label><select id="iSeries" onchange="seriesChange()"></select></div>
          <div class="field"><label>Πληρωμή</label>
            <select id="iPay"><option value="3">Μετρητά</option><option value="1">Τραπεζικός λογ.</option>
              <option value="5">Επί πιστώσει</option><option value="6">Web Banking</option>
              <option value="7" selected>POS</option><option value="8">IRIS</option></select></div>
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
          <div class="hint" id="dfCount"></div>
        </div>
        <table id="draftsTable"><thead><tr><th>Ημ/νία</th><th>Τύπος</th><th>Σειρά</th><th>Πελάτης</th><th></th></tr></thead><tbody></tbody></table>
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
        <div class="field grow">
          <label>Γραμμές (μία ανά παραστατικό) — <b>ΑΦΜ · κωδικός είδους · ποσότητα · τιμή μονάδας</b> (χωρισμένα με «,» ή «;»)</label>
          <textarea id="blkCsv" rows="8" placeholder="800702104, 1, 1, 100&#10;800702104, 3, 2, 50&#10;# γραμμές με # αγνοούνται" style="width:100%;font-family:monospace"></textarea>
          <p class="hint">Παράδειγμα: <code>800702104, 1, 1, 100</code> → ΑΦΜ 800702104, είδος «1», ποσότητα 1, τιμή 100€. Ο τύπος/σειρά/πληρωμή είναι οι κοινοί από πάνω.</p>
        </div>
        <div class="row" style="align-items:center">
          <button class="info" onclick="bulkParse(true)">🔍 Έλεγχος γραμμών</button>
          <button class="add" onclick="bulkRun(false)" title="Δημιουργία προχείρων για όλες τις γραμμές — χωρίς υποβολή/ΜΑΡΚ">💾 Δημιουργία προχείρων (όλα)</button>
          <div class="grow"></div>
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
      <div class="panel" style="margin-top:14px">
        <div class="row" style="justify-content:space-between">
          <strong>Επιχειρήσεις (λογαριασμοί AADE)</strong>
          <span class="hint" id="adminBizCount"></span>
        </div>
        <p class="sub">Όλες οι συνδεδεμένες επιχειρήσεις. Ο διαχειριστής δεν είναι επιχείρηση — απλώς τις διαχειρίζεται.</p>
        <table id="adminBiz"><thead><tr><th>Επωνυμία</th><th>ΑΦΜ</th><th>Χρήστης (κάτοχος)</th><th></th></tr></thead><tbody></tbody></table>
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
  <div class="row"><div class="field"><label>Ημ/νία</label><input id="pmDate" type="text" class="dt" placeholder="ηη/μμ/εεεε" maxlength="10" oninput="dtMask(this)" required></div>
    <div class="field"><label>Τρόπος</label><select id="pmMethod"><option value="3">Μετρητά</option><option value="1">Τραπεζική μεταφορά</option><option value="4">Επιταγή</option></select></div></div>
  <div class="field" style="margin-top:8px"><label>Σημειώσεις</label><input id="pmNotes" placeholder="π.χ. έναντι τιμολογίου…"></div>
  <div class="row" style="margin-top:16px;justify-content:flex-end">
    <button type="button" class="ghost" onclick="payModal.close()">Άκυρο</button>
    <button type="submit" class="primary">Αποθήκευση</button></div>
</form></dialog>

<?php if ($__role === 'master'): ?>
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

<!-- Admin: manage AADE accounts for a user -->
<dialog id="acctModal"><div class="modal-body" style="max-width:720px">
  <div class="modal-head">🏢 Λογαριασμοί AADE — <span id="amUser"></span></div>
  <table id="amList"><thead><tr><th>ΑΦΜ</th><th>Ετικέτα</th><th>Username</th><th></th></tr></thead><tbody></tbody></table>
  <div class="row" style="margin-top:14px;align-items:flex-end">
    <div class="field"><label>ΑΦΜ</label><input id="amVat" oninput="amVatLookup()" style="width:120px"></div>
    <div class="field"><label>Ετικέτα</label><input id="amLabel" placeholder="(αυτόματα)" style="width:160px"></div>
    <div class="field"><label>Username</label><input id="amUsername" style="width:140px"></div>
    <div class="field"><label>Subscription key</label><input id="amKey" style="width:220px"></div>
    <button class="primary" onclick="addAccount()">+ Προσθήκη</button>
  </div>
  <div class="row" style="margin-top:16px;justify-content:flex-end"><button class="ghost" onclick="acctModal.close()">Κλείσιμο</button></div>
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

<!-- Command palette -->
<div id="palette"><div class="pal-box">
  <input id="palInput" placeholder="Αναζήτηση πελάτη (ΑΦΜ ή επωνυμία)… ↵ για καρτέλα">
  <div class="pal-results" id="palResults"></div>
</div></div>

<div class="toast" id="toast"></div>

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
#cbHead select{background:rgba(255,255,255,.15);color:#fff;border:none;border-radius:8px;padding:3px 6px;font-size:12px}
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
  <div id="cbHint">π.χ. «έκδοση τιμολογίου στον 802012659 για 2 τεμ ΚΩΔ 10 ευρώ» · «νέος πελάτης 094xxxxxx» · «νέο είδος Μπογιά 15 ευρώ» · «πήγαινε στην καρτέλα» · «βοήθεια»</div>
  <div id="cbBar">
    <input id="cbInput" placeholder="Γράψε ή πάτα το μικρόφωνο…" onkeydown="if(event.key==='Enter')cbSubmitText()">
    <button id="cbMic" title="Ομιλία" onclick="cbToggleMic()">🎙</button>
    <button id="cbSend" title="Αποστολή" onclick="cbSubmitText()">➤</button>
  </div>
</div>

<div id="themeToggle" onclick="toggleTheme()" data-tip="Εναλλαγή φωτεινού / σκοτεινού θέματος">
  <span class="tt-switch"><span class="tt-knob" id="themeIco">🌙</span></span><span id="themeLbl">Σκούρο</span>
</div>

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
const PAYMETHODS={3:'Μετρητά',1:'Τραπεζική μεταφορά',4:'Επιταγή'};
function payMethod(m){return PAYMETHODS[parseInt(m,10)]||'';}
function toast(m,t=''){const e=$('#toast');e.className='toast show '+t;e.textContent=m;clearTimeout(e._t);e._t=setTimeout(()=>e.className='toast',3400);}
// --- Theme (light / dark) -----------------------------------------------------
function applyTheme(t){const light=t==='light';document.documentElement.setAttribute('data-theme',light?'light':'dark');
  const ico=$('#themeIco'),lbl=$('#themeLbl');if(ico)ico.textContent=light?'☀️':'🌙';if(lbl)lbl.textContent=light?'Φωτεινό':'Σκούρο';}
function toggleTheme(){const cur=document.documentElement.getAttribute('data-theme')==='light'?'light':'dark';
  const next=cur==='light'?'dark':'light';localStorage.setItem('etim_theme',next);applyTheme(next);}
applyTheme(localStorage.getItem('etim_theme')||'dark');

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
  if(v==='delivery'){if(!$('#dnDate').value)dset('dnDate',new Date().toISOString().slice(0,10));if(!$('#dnLines tbody').children.length)addDnLine();dnInit();}
  if(v==='issue'){if(!$('#iLines tbody').children.length)addLine();loadIssueTypes();renderTaxes();loadTaxCats();}
  if(v==='drafts')loadDrafts();
  if(v==='bulk')loadBulkView();
  if(v==='series')loadSeriesView();
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
async function loadAdmin(){try{const d=await apost({auth:'admin_users'});renderAdmin(d.users||[]);
    const a=await apost({auth:'admin_accounts'});renderBiz(a.accounts||[]);
  }catch(e){toast('Διαχείριση: '+e.message,'err');}}
function renderBiz(accs){const el=$('#adminBiz');if(!el)return;
  $('#adminBizCount').textContent=accs.length+' επιχειρήσεις';
  el.querySelector('tbody').innerHTML=accs.map(a=>`<tr>
    <td><b>${esc(a.label||'—')}</b></td><td>${esc(a.vat||'')}</td><td>${esc(a.owner_email||'—')}</td>
    <td class="right"><button class="ghost sm" onclick="openAcctModal(${a.user_id},'${q1(a.label||a.vat)}')" data-tip="Επεξεργασία διαπιστευτηρίων AADE">Διαχείριση</button></td></tr>`).join('')
    ||'<tr><td colspan="4" class="muted">Καμία συνδεδεμένη επιχείρηση. Πάτησε «+ Νέα επιχείρηση».</td></tr>';}
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
  userModal.close();toast('Η επιχείρηση δημιουργήθηκε','ok');loadAdmin();}
let AM_USER=0;
async function openAcctModal(userId,name){AM_USER=userId;$('#amUser').textContent=name;['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');await loadUserAccounts();acctModal.showModal();}
async function loadUserAccounts(){const d=await apost({auth:'admin_user_accounts',user_id:AM_USER});
  $('#amList tbody').innerHTML=(d.accounts||[]).map(a=>`<tr><td>${esc(a.vat)}</td><td>${esc(a.label)}</td><td>${esc(a.username)}</td><td class="right"><button class="danger sm" onclick="delAccount(${a.id})">✕</button></td></tr>`).join('')||'<tr><td colspan="4" class="muted">Κανένας λογαριασμός.</td></tr>';}
let amVatT;
function amVatLookup(){clearTimeout(amVatT);amVatT=setTimeout(async()=>{const vat=$('#amVat').value.trim();if(!/^\d{9}$/.test(vat))return;
  const name=await nameForVat(vat);if(name&&!$('#amLabel').value.trim())$('#amLabel').value=name;},400);}
async function addAccount(){const vat=$('#amVat').value.trim();if(!/^\d{9}$/.test(vat)){toast('ΑΦΜ 9 ψηφίων','err');return;}
  let label=$('#amLabel').value.trim();if(!label)label=await nameForVat(vat);
  const d=await apost({auth:'admin_add_account',user_id:AM_USER,vat,label,username:$('#amUsername').value,subkey:$('#amKey').value});
  if(d.success){['amVat','amLabel','amUsername','amKey'].forEach(i=>$('#'+i).value='');toast('Προστέθηκε','ok');loadUserAccounts();}else toast(d.error||'Αποτυχία','err');}
async function delAccount(id){if(!confirm('Διαγραφή λογαριασμού AADE;'))return;const d=await apost({auth:'admin_delete_account',account_id:id});if(d.success){toast('Διαγράφηκε','ok');loadUserAccounts();}else toast(d.error||'Αποτυχία','err');}
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
  // header sort indicators
  ['code','vat','name','city'].forEach(c=>{const th=document.getElementById('cs-'+c);if(th)th.textContent=th.textContent.replace(/ [▲▼]$/,'')+(CUST_SORT.key===c?(CUST_SORT.dir>0?' ▲':' ▼'):'');});
  $('#custCount').textContent=rows.length+' / '+ALL_CUSTOMERS.length+' πελάτες';
  $('#custTable tbody').innerHTML=rows.slice(0,500).map(c=>
    `<tr class="clickable" onclick="openCard('${q1(c.vat)}','${q1(c.name)}')"><td>${esc(c.code)}</td><td>${esc(c.vat)}</td><td>${esc(c.name)}</td><td>${esc(c.city)}</td>
      <td class="right"><button class="primary sm" title="Έκδοση παραστατικού" onclick="event.stopPropagation();issueFor('${q1(c.vat)}','${q1(c.name)}')">🧾 Έκδοση</button>
      <button class="ghost sm" onclick="event.stopPropagation();editCustomer('${q1(c.vat)}','${q1(c.name)}','${q1(c.address)}','${q1(c.city)}','${q1(c.zip)}')">✎</button>
      <button class="ghost sm" onclick="event.stopPropagation();openCard('${q1(c.vat)}','${q1(c.name)}')">Καρτέλα →</button></td></tr>`).join('')||'<tr><td colspan="5" class="muted">Κανένα αποτέλεσμα.</td></tr>';
}
async function loadCustomers(){await cachedThenSync('customers',rows=>{ALL_CUSTOMERS=rows;renderCustomers();});}

// Customer modal (create/edit)
let CUST_EDIT=null,CUST_ONSAVED=null;
function custTab(t){$('#custTabAfm').style.display=t==='afm'?'':'none';$('#custTabPersonal').style.display=t==='personal'?'':'none';document.querySelectorAll('#custTabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));}
function openCustomerModal(onSaved,prefillAfm){CUST_EDIT=null;CUST_ONSAVED=(typeof onSaved==='function')?onSaved:null;$('#custModalTitle').textContent='Νέος πελάτης';['cmAfm','cmName','cmAddress','cmCity','cmZip','cpName','cpAddress','cpCity','cpZip','cpEmail','cpPhone'].forEach(id=>$('#'+id).value='');$('#cpJob').value='ΙΔΙΩΤΗΣ';custTab('afm');if(prefillAfm)$('#cmAfm').value=prefillAfm;$('#custModal').showModal();}
function editCustomer(vat,name,address,city,zip){CUST_EDIT={vat};CUST_ONSAVED=null;$('#custModalTitle').textContent='Επεξεργασία πελάτη';custTab('afm');$('#cmAfm').value=vat;$('#cmName').value=name;$('#cmAddress').value=address;$('#cmCity').value=city;$('#cmZip').value=zip;$('#custModal').showModal();}
async function cmLookup(){const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}
  try{const d=await api({afm});const c=d.customer||d.info||d;$('#cmName').value=c.name||c.customer_name||'';$('#cmAddress').value=c.address||'';$('#cmCity').value=c.city||'';$('#cmZip').value=c.zip||'';toast('Στοιχεία αντλήθηκαν','ok');}catch(e){toast('Taxisnet: '+e.message,'err');}}
async function saveCustomer(){
  try{let d,saved=null;
    if(CUST_EDIT){d=await api({update_customer:1,update_customer_vat:CUST_EDIT.vat,update_name:$('#cmName').value,update_address:$('#cmAddress').value,update_city:$('#cmCity').value,update_zip:$('#cmZip').value});
      saved={vat:CUST_EDIT.vat,name:$('#cmName').value,address:$('#cmAddress').value,city:$('#cmCity').value,zip:$('#cmZip').value};}
    else if($('#custTabPersonal').style.display!=='none'){
      if(!$('#cpName').value||!$('#cpCity').value||!$('#cpZip').value){toast('Συμπλήρωσε όνομα/πόλη/ΤΚ','err');return;}
      d=await api({create_personal_customer:1,cust_name:$('#cpName').value,cust_address:$('#cpAddress').value,cust_city:$('#cpCity').value,cust_zip:$('#cpZip').value,cust_job_description:$('#cpJob').value,cust_email:$('#cpEmail').value,cust_phone1:$('#cpPhone').value});
      saved={vat:'',name:$('#cpName').value,address:$('#cpAddress').value,city:$('#cpCity').value,zip:$('#cpZip').value};
    }else{const afm=$('#cmAfm').value.trim();if(!/^\d{9}$/.test(afm)){toast('Δώσε 9ψήφιο ΑΦΜ','err');return;}d=await api({afm});
      const c=(d&&(d.info||d.customer))||{};saved={vat:afm,name:c.name||$('#cmName').value||'',address:c.address||'',city:c.city||'',zip:c.zip||''};}
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
let CARD={};
async function loadCard(){const vat=$('#cardVat').value.trim();if(!vat){toast('Επίλεξε πελάτη','err');return;}defaultRange();
  $('#cardCards').innerHTML='<div class="card"><div class="v"><span class="spin"></span></div></div>';$('#cardTable tbody').innerHTML='';
  try{const d=await api({ledger:1,buyer_vat:vat,issue_date_from:di('cardFrom'),issue_date_to:di('cardTo')});if(!d.success)throw new Error(d.error||'σφάλμα');CARD=d;
    const balCls=d.balance>0.005?'pos':'zero';
    $('#cardHead').innerHTML=`<strong>${esc(d.customer_name||vat)}</strong> <span class="muted">ΑΦΜ ${esc(vat)}</span>`;
    $('#cardCards').innerHTML=`<div class="card"><div class="k">Τζίρος</div><div class="v">${fmt(d.total_invoiced)} €</div></div>`+
      `<div class="card"><div class="k">Πληρωμές</div><div class="v" style="color:#86efac">${fmt(d.total_paid)} €</div></div>`+
      `<div class="card"><div class="k">Υπόλοιπο</div><div class="v balance ${balCls}">${fmt(d.balance)} €</div></div>`;
    $('#cardTable tbody').innerHTML=d.entries.map(e=>{
      if(e.kind==='invoice')return `<tr><td>${esc(e.date)}</td><td><span class="pill" title="${esc(invName(e.type))}">${esc(e.type||'')}</span> ${esc(invName(e.type))}</td><td>ΜΑΡΚ ${esc(e.mark)}</td><td class="num">${fmt(e.debit)}</td><td class="num"></td><td class="num">${fmt(e.balance)}</td>
        <td class="right">${e.mark?`<a href="${API}?account=${ACCOUNT}&mark=${esc(e.mark)}&pdf_raw=1" target="_blank">PDF</a> <button class="danger sm" title="Ακύρωση με πιστωτικό" onclick="cancelFromCard('${q1(e.mark)}')">↩ Ακύρωση</button>`:''}</td></tr>`;
      return `<tr><td>${esc(e.date)}</td><td><span class="pill ok">Πληρωμή</span> ${esc(payMethod(e.method))}</td><td>${esc(e.notes||'')}</td><td class="num"></td><td class="num">${fmt(e.credit)}</td><td class="num">${fmt(e.balance)}</td><td class="right"><button class="danger sm" onclick="delPayment(${e.payment_id})">✕</button></td></tr>`;
    }).join('')||'<tr><td colspan="7" class="muted">Καμία κίνηση.</td></tr>';
  }catch(e){$('#cardCards').innerHTML='';toast('Καρτέλα: '+e.message,'err');}
}
async function cancelFromCard(mark){showView('cancel');$('#cxVat').value=CARD.customer_vat||'';$('#cxCust').value=CARD.customer_name||CARD.customer_vat||'';
  await cxLoadInvoices();const idx=CX_INV.findIndex(i=>String(i.mark)===String(mark));if(idx>=0)cxPick(idx);toast('Επιλέχθηκε για πίστωση/ακύρωση','ok');}

// Payments
function openPaymentModal(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε πρώτα καρτέλα','err');return;}
  $('#pmVat').value=vat;$('#pmAmount').value=CARD.balance>0?CARD.balance.toFixed(2):'';dset('pmDate',new Date().toISOString().slice(0,10));$('#pmNotes').value='';$('#payModal').showModal();}
async function savePayment(ev){ev.preventDefault();
  try{const d=await api({add_payment:1,buyer_vat:$('#pmVat').value,customer_name:CARD.customer_name||'',pay_amount:$('#pmAmount').value,pay_method:$('#pmMethod').value,pay_date:di('pmDate'),pay_notes:$('#pmNotes').value});
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
// Accepts a myDATA VAT category (1-8), a percent string ("24%"), or a plain number.
function vatPct(v){if(v===undefined||v===null||v==='')return 24;const s=String(v);if(s.includes('%'))return parseFloat(s)||0;const n=parseInt(s,10);if(n>=1&&n<=8)return VATPCT[n];return isNaN(n)?24:n;}
async function loadProductList(){try{const d=await api({list_products:1});const dl=$('#prodList');dl.innerHTML='';PRODMAP={};
  (d.products||[]).forEach(p=>{const code=p.product_code||p.code;if(!code)return;const desc=p.description||'';const vat=p.vat||p.vat_category||'';const price=parseFloat(p.unit_price||p.price||0)||0;
    const good=String(p.type||'').trim()!=='Υπηρεσία';  // delivery notes accept goods only
    PRODMAP[code]={desc,vat,price,good};const o=document.createElement('option');o.value=code;o.textContent=desc;dl.appendChild(o);});
}catch(e){}}
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
  const rows=[];
  for(const t of INV_TYPES){
    const code=String(t.value||'');const o=await clsOptions(code);const cats=o.categories||[];
    if(!cats.length)continue;
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
let SERIES=[];
async function loadIssueTypes(){await loadInvTypes();
  try{const d=await api({list_series:1});SERIES=d.series||[];const seen=new Set(),opts=[];
    SERIES.forEach(s=>{const v=String(s.invoice_type_code||'').trim();if(v&&!seen.has(v)){seen.add(v);opts.push({v,label:invLabelByValue(v)!==v?invLabelByValue(v):(s.invoice_type||v)});}});
    const sel=$('#iType');const cur=sel.value;
    if(opts.length){sel.innerHTML=opts.map(o=>`<option value="${esc(o.v)}">${esc(o.label)}</option>`).join('');
      if(opts.some(o=>o.v===cur))sel.value=cur;
      sel.title='';
    }else{sel.innerHTML='<option value="">— καμία ενεργή σειρά —</option>';toast('Δεν υπάρχει ενεργή σειρά. Δημιούργησε σειρά για να εκδώσεις.','err');}
    fillSeries();showIssueCls();
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

// --- Μαζική έκδοση (bulk) ------------------------------------------------------
async function loadBulkView(){await loadInvTypes();
  try{if(!SERIES||!SERIES.length){const d=await api({list_series:1});SERIES=d.series||[];}
    const seen=new Set(),opts=[];
    SERIES.forEach(s=>{const v=String(s.invoice_type_code||'').trim();if(v&&!seen.has(v)){seen.add(v);opts.push({v,label:invLabelByValue(v)!==v?invLabelByValue(v):(s.invoice_type||v)});}});
    const sel=$('#blkType');
    sel.innerHTML=opts.length?opts.map(o=>`<option value="${esc(o.v)}">${esc(o.label)}</option>`).join(''):'<option value="">— καμία ενεργή σειρά —</option>';
    blkFillSeries();
  }catch(e){}}
function blkFillSeries(){const t=$('#blkType').value;const sel=$('#blkSeries');
  const list=(SERIES||[]).filter(s=>String(s.invoice_type_code||'')===t);
  sel.innerHTML=list.length?list.map(s=>`<option value="${esc(s.series_code)}">${esc(s.series_code)}${s.description?(' — '+esc(s.description)):''}</option>`).join(''):'<option value="">—</option>';}
// Parse the CSV textarea → array of bulk items using the common type/series/payment.
function bulkParse(announce){
  const type=$('#blkType').value, series=$('#blkSeries').value, pay=$('#blkPay').value, lang=$('#blkLang').value;
  if(!type){toast('Επίλεξε τύπο παραστατικού','err');return null;}
  if(!series){toast('Επίλεξε σειρά','err');return null;}
  const raw=$('#blkCsv').value.split(/\r?\n/);const items=[];const errs=[];
  raw.forEach((ln,i)=>{const s=ln.trim();if(!s||s.startsWith('#'))return;
    const p=s.split(/[;,\t]/).map(x=>x.trim());
    if(p.length<4){errs.push(`Γραμμή ${i+1}: χρειάζονται 4 πεδία (ΑΦΜ, κωδικός, ποσότητα, τιμή)`);return;}
    const [afm,code,qty,price]=p;
    if(!/^\d{9}$/.test(afm)){errs.push(`Γραμμή ${i+1}: μη έγκυρο ΑΦΜ «${afm}»`);return;}
    const q=parseFloat(qty.replace(',','.'))||0, pr=parseFloat(price.replace(',','.'))||0;
    if(!code){errs.push(`Γραμμή ${i+1}: λείπει ο κωδικός είδους`);return;}
    if(q<=0){errs.push(`Γραμμή ${i+1}: μη έγκυρη ποσότητα`);return;}
    items.push({afm,type,series,payment:pay,issue_lang:lang,lines:[{code,qty:q,price:pr}]});
  });
  if(announce){
    let html=`<div class="card"><span class="pill ${errs.length?'warn':'ok'}">${items.length} έγκυρες γραμμές</span>`;
    if(errs.length)html+=`<div style="margin-top:8px;color:#c0392b">${errs.map(esc).join('<br>')}</div>`;
    html+='</div>';$('#blkResult').innerHTML=html;
  }
  return {items,errs};
}
async function bulkRun(live){
  const parsed=bulkParse(false);if(!parsed)return;
  const {items,errs}=parsed;
  if(!items.length){toast('Καμία έγκυρη γραμμή'+(errs.length?' — δες Έλεγχος':''),'err');bulkParse(true);return;}
  if(errs.length&&!confirm(`${errs.length} γραμμές έχουν σφάλμα και θα παραλειφθούν. Συνέχεια με ${items.length};`)){bulkParse(true);return;}
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
async function loadSeriesView(){
  const sel=$('#srType');
  try{
    // populate the invoice-type dropdown (all types, so any series can be created)
    const it=await api({invoice_types:1});const types=it.invoice_types||[];
    sel.innerHTML=types.map(t=>`<option value="${esc(t.value||t.code)}">${esc(t.label||((t.code||'')+' - '+(t.name||'')))}</option>`).join('');
  }catch(e){/* keep whatever is there */}
  $('#srTable tbody').innerHTML='<tr><td colspan="5"><span class="spin"></span></td></tr>';
  try{
    const d=await api({list_series:1});const rows=d.series||[];
    $('#srTable tbody').innerHTML=rows.map(s=>`<tr>
      <td>${esc(s.invoice_type||s.invoice_type_code||'')}</td>
      <td><strong>${esc(s.series_code||'')}</strong></td>
      <td>${esc(s.start_aa||'')}</td>
      <td class="muted">${esc(s.description||'')}</td>
      <td class="right"><button class="danger sm" onclick="delSeries('${q1(s.series_id||s.delete_id||'')}','${q1(s.series_code||'')}')">✕ Διαγραφή</button></td>
    </tr>`).join('')||'<tr><td colspan="5" class="muted">Καμία σειρά. Δημιούργησε μία παραπάνω.</td></tr>';
  }catch(e){$('#srTable tbody').innerHTML='';toast('Σειρές: '+e.message,'err');}
}
async function createSeriesUI(){
  const t=$('#srType').value;const code=$('#srCode').value.trim();
  if(!t){toast('Επίλεξε τύπο παραστατικού','err');return;}
  if(!code){toast('Δώσε κωδικό σειράς','err');return;}
  $('#srResult').innerHTML='<span class="spin"></span> Δημιουργία…';
  try{const d=await api({new_series:1,series_invoice_type:t,series_code:code,series_start_aa:$('#srAa').value||'1',series_description:$('#srDesc').value.trim()});
    if(d.success===false)throw new Error(d.error||'σφάλμα');
    $('#srResult').innerHTML=`<div class="card"><span class="pill ok">Η σειρά «${esc(code)}» δημιουργήθηκε</span></div>`;
    $('#srCode').value='';$('#srDesc').value='';
    SERIES=[];loadSeriesView();
  }catch(e){$('#srResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(e.message)+'</div>';}
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
  if(term)rows=rows.filter(c=>(c.vat+' '+c.name+' '+c.code+' '+c.city).toLowerCase().includes(term));
  rows=rows.slice(0,30);
  const newRow=`<div class="ac-row" style="font-weight:700;color:var(--accent)" onmousedown="newCustFromIssue()">➕ Νέος πελάτης…</div>`;
  panel.innerHTML=newRow+rows.map(c=>`<div class="ac-row" onmousedown="pickCust('${q1(c.vat)}')"><b>${esc(c.name||c.vat)}</b> <small>ΑΦΜ ${esc(c.vat)}${c.city?' · '+esc(c.city):''}</small></div>`).join('');
  panel.classList.add('open');}
function pickCust(vat){const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===vat);if(!c)return;
  $('#iAfm').value=c.vat;$('#iName').value=c.name;$('#iAddress').value=c.address||'';$('#iCity').value=c.city||'';$('#iZip').value=c.zip||'';
  $('#iCustAc').classList.remove('open');showIssueCls();}
// Create a new customer from within the issue form; on save, fill the form with it.
function newCustFromIssue(){$('#iCustAc').classList.remove('open');const typed=($('#iAfm').value||'').trim();
  openCustomerModal(c=>{if(c){$('#iAfm').value=c.vat||$('#iAfm').value;$('#iName').value=c.name||'';$('#iAddress').value=c.address||'';$('#iCity').value=c.city||'';$('#iZip').value=c.zip||'';}},/^\d{9}$/.test(typed)?typed:'');}
document.addEventListener('click',e=>{const p=$('#iCustAc');if(p&&!e.target.closest('#iCustAc')&&e.target!==$('#iAfm')&&e.target!==$('#iName'))p.classList.remove('open');});
// Pre-fill the issue form for a specific customer (from the Πελάτες list)
function issueFor(vat,name){showView('issue');$('#iAfm').value=vat;$('#iName').value=name||'';
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
  <td class="num"><input class="ln-price" type="number" step="0.0001" min="0" value="${esc(price)}" oninput="lineFromInputs(this.closest('tr'))" placeholder="0.00" style="width:100px;text-align:right"></td>
  <td class="num"><input class="ln-disc" type="number" step="0.01" min="0" max="100" value="${esc(disc||'')}" oninput="lineFromInputs(this.closest('tr'))" placeholder="0" style="width:70px;text-align:right"></td>
  <td class="num ln-vat">—</td>
  <td class="num"><input class="ln-gross" type="number" step="0.01" min="0" oninput="lineFromGross(this.closest('tr'))" placeholder="0.00" style="width:110px;text-align:right"></td>
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
  if(p.price&&!parseFloat(row.querySelector('.ln-price').value))row.querySelector('.ln-price').value=p.price;
  row.querySelector('.ln-ac').classList.remove('open');lineFromInputs(row);}
function newProdForLine(el){const row=el.closest('tr');const inp=row.querySelector('.ln-code');row.querySelector('.ln-ac').classList.remove('open');
  const typed=(inp.value||'').trim();
  openProductModal(/^[\w.-]{1,20}$/.test(typed)&&!PRODMAP[typed]?typed:'',code=>{pickProd(el,code);});}
document.addEventListener('click',e=>{if(!e.target.closest('.ln-code')&&!e.target.closest('.ln-ac'))document.querySelectorAll('.ln-ac.open').forEach(p=>p.classList.remove('open'));});
// Recompute a line from unit price / qty / discount → gross (source of truth = unit price).
function lineFromInputs(row){const u=parseFloat(row.querySelector('.ln-price').value)||0;const q=parseFloat(row.querySelector('.ln-qty').value)||0;const d=Math.min(parseFloat(row.querySelector('.ln-disc').value)||0,100);const r=rowRate(row);
  const net=u*q*(1-d/100);const gross=net*(1+r);
  const g=row.querySelector('.ln-gross');if(document.activeElement!==g)g.value=net?gross.toFixed(2):'';
  sumTotals();}
// User typed the gross (with VAT) directly → derive unit price / discount.
// If the item's list unit price is higher than the implied one, express the gap as a discount %.
function lineFromGross(row){const G=parseFloat(row.querySelector('.ln-gross').value)||0;const q=parseFloat(row.querySelector('.ln-qty').value)||0;const r=rowRate(row);
  const netFromG=G/(1+r);const priceInp=row.querySelector('.ln-price');const discInp=row.querySelector('.ln-disc');
  const u=parseFloat(priceInp.value)||0;
  if(q>0&&u>0){const baseNet=u*q;
    if(baseNet>0&&netFromG<baseNet-0.005){discInp.value=((1-netFromG/baseNet)*100).toFixed(2);}      // list price higher ⇒ discount
    else{discInp.value='';priceInp.value=(netFromG/q).toFixed(4);}
  }else if(q>0){priceInp.value=(netFromG/q).toFixed(4);discInp.value='';}
  sumTotals();}
function collectLines(){const out=[];document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const code=(r.querySelector('.ln-code').dataset.code||'').trim();const qty=parseFloat(r.querySelector('.ln-qty').value)||0;const price=parseFloat(r.querySelector('.ln-price').value)||0;const disc=parseFloat(r.querySelector('.ln-disc').value)||0;
  if(code&&price>0&&qty>0){const o={code,qty,price};if(disc>0)o.disc=disc;out.push(o);}});return out;}
// Totals: net + VAT (per-line rate) − withholding = payable.
function sumTotals(){let net=0,vat=0;document.querySelectorAll('#iLines tbody tr').forEach(r=>{
  const u=parseFloat(r.querySelector('.ln-price').value)||0;const q=parseFloat(r.querySelector('.ln-qty').value)||0;const d=Math.min(parseFloat(r.querySelector('.ln-disc').value)||0,100);const rate=rowRate(r);
  const ln=u*q*(1-d/100);net+=ln;vat+=ln*rate;
  r.querySelector('.ln-vat').textContent=rowVatLabel(r);
  const g=r.querySelector('.ln-gross');if(document.activeElement!==g)g.value=ln?(ln*(1+rate)).toFixed(2):'';});
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
$('#txCat')&&$('#txCat').addEventListener('change',function(){
  const t=$('#txType').value;$('#txWarn').textContent='';
  if(this.value==='__new'){createNewDeduction();return;}
  if(t==='1'&&this.value==='3')$('#txWarn').textContent='«Αμοιβές Συμβούλων Διοίκησης 20%»: μόνο για ατομικές επιχειρήσεις.';
});
// Create a new custom deduction (κράτηση) and refresh the dropdown selecting it.
async function createNewDeduction(){
  const name=prompt('Ονομασία νέας κράτησης:','');
  if(!name){$('#txCat').value='';return;}
  $('#txErr').textContent='';
  try{const d=await api({new_deduction:1,deduction_desc:name.trim(),deduction_amount_type:'1',deduction_amount:'0'});
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
    if(d.success){$('#issueResult').innerHTML=d.live?`<div class="card"><span class="pill ok">Εκδόθηκε</span><div style="margin-top:8px">ΜΑΡΚ <strong>${esc(d.mark)}</strong> · ΑΑ ${esc(d.aa)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a></div></div>`:`<div class="card"><span class="pill warn">Πρόχειρο</span><div style="margin-top:8px">Temp ID ${esc(d.temp_id)} · ${lines.length} γραμμές · Σύνολο ${fmt(d.amount_total)} € <span class="muted">(δεν υποβλήθηκε)</span></div></div>`;toast(d.live?'Εκδόθηκε':'Πρόχειρο OK','ok');if(d.live)window.__issueTempId=null;ITAXES=[];renderTaxes();sumTotals();offerDelivery(lines);}
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
    if(d.success)$('#dnResult').innerHTML=`<div class="card"><span class="pill ${d.live?'ok':'warn'}">${d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο'}</span><div style="margin-top:8px">Τύπος ${esc(d.type)} · σκοπός ${esc($('#dnPurpose option:checked').textContent)} · σύνολο ${fmt(d.amount_total)} €<br>${d.live?`ΜΑΡΚ <strong>${esc(d.mark)}</strong> · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a>`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`,toast(d.live?'Δελτίο εκδόθηκε':'Πρόχειρο δελτίο','ok'),d.live&&(window.__dnTempId=null);
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
      <div style="margin-top:8px">Τύπος ${esc(d.credit_type)} (5.1/11.4) · Συσχ. ΜΑΡΚ ${esc(d.correlated_mark)}<br>Αρχικό: ${esc(o.type||'')} · ΑΦΜ ${esc(o.buyer_vat||'')} · καθαρή ${fmt(o.net||0)} €<br>${d.live?`Νέο ΜΑΡΚ <strong>${esc(d.mark)}</strong> · <a href="${API}?account=${ACCOUNT}&mark=${esc(d.mark)}&pdf_raw=1" target="_blank">PDF</a>`:`Temp ID ${esc(d.temp_id)} <span class="muted">(δεν υποβλήθηκε)</span>`}</div></div>`;
      toast(d.live?'Πιστωτικό εκδόθηκε':'Πρόχειρο πιστωτικό OK','ok');if(d.live)window.__cxTempId=null;}
    else $('#cxResult').innerHTML='<div class="card"><span class="pill bad">Σφάλμα</span> '+esc(d.error||'')+'</div>';
  }catch(e){$('#cxResult').innerHTML='';toast('Πιστωτικό: '+e.message,'err');}}

// Drafts (προσωρινά αποθηκευμένα)
function draftRange(){const y=new Date().getFullYear();if(!$('#dfFrom').value)dset('dfFrom',y+'-01-01');if(!$('#dfTo').value)dset('dfTo',y+'-12-31');}
async function loadDrafts(){draftRange();$('#draftsTable tbody').innerHTML='<tr><td colspan="5"><span class="spin"></span></td></tr>';
  try{const d=await api({search_temp:1,save_date_from:di('dfFrom'),save_date_to:di('dfTo')});
    const rows=d.temp_invoices||d.items||d.results||[];$('#dfCount').textContent=rows.length+' πρόχειρα';
    const nameFor=v=>{const c=ALL_CUSTOMERS.map(custFields).find(x=>x.vat===v);return c?c.name:'';};
    $('#draftsTable tbody').innerHTML=rows.map(t=>{const bv=t.buyer_vat||'';const nm=nameFor(bv);
      return `<tr><td>${esc(t.save_date||'')}</td><td>${esc(t.type||'')}</td><td>${esc(t.series||'')}</td><td>${esc(nm||bv||'—')}</td>
      <td class="right"><button class="info sm" onclick="previewDraft('${q1(t.enc_id||t.temp_id)}',this)" title="Φέρε το PDF προεπισκόπησης αυτού του προχείρου (χωρίς νέο πρόχειρο)">👁 Προεπισκόπηση</button>
      <button class="danger sm" onclick="delDraft('${q1(t.temp_id)}','${q1(t.seller_vat||'')}')">✕ Διαγραφή</button></td></tr>`;}).join('')
      ||'<tr><td colspan="5" class="muted">Κανένα πρόχειρο.</td></tr>';
  }catch(e){$('#draftsTable tbody').innerHTML='';toast('Πρόχειρα: '+e.message,'err');}}
// Preview the PDF of an EXISTING draft by its id — reuses the cached model, no new draft.
async function previewDraft(id,btn){const old=btn?btn.textContent:'';if(btn){btn.disabled=true;btn.textContent='…';}
  try{const d=await api({preview_temp:id});
    if(d&&d.success&&d.pdf_b64){cbOpenPdfB64(d.pdf_b64);toast('Προεπισκόπηση ΑΑΔΕ έτοιμη','ok');}
    else toast('Προεπισκόπηση: '+((d&&d.error)||'απέτυχε'),'err');
  }catch(e){toast('Προεπισκόπηση: '+e.message,'err');}
  finally{if(btn){btn.disabled=false;btn.textContent=old;}}}
async function delDraft(id,seller){if(!confirm('Διαγραφή πρόχειρου παραστατικού;'))return;
  try{const d=await api({delete_temp_id:id,seller_vat:seller});if(d.success===false)throw new Error(d.error||'');toast('Διαγράφηκε','ok');loadDrafts();}catch(e){toast('Διαγραφή: '+e.message,'err');}}

// ZIP downloads (browser handles the file)
function zipUrl(params){const q=new URLSearchParams(params);if(ACCOUNT)q.set('account',ACCOUNT);return API+'?'+q.toString();}
function zipCustomerInvoices(){const vat=$('#cardVat').value.trim();if(!vat){toast('Φόρτωσε καρτέλα','err');return;}
  toast('Λήψη ZIP παραστατικών…','ok');window.location=zipUrl({invoices_zip:1,buyer_vat:vat,issue_date_from:di('cardFrom'),issue_date_to:di('cardTo')});}
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

// ====== Voice assistant / chatbot (Web Speech API, no dependency) ============
// Controlled operation: parses Greek/English commands for issuing a document,
// creating a customer, or creating a product — and ALWAYS produces a preview /
// draft for manual review (never auto-issues live). Also answers navigation/help.
let cbRec=null,cbRecOn=false;
function cbTogglePanel(){const p=$('#cbPanel');p.classList.toggle('open');
  if(p.classList.contains('open')){$('#cbInput').focus();if(!$('#cbLog').children.length)cbBot('Γεια! Πες μου π.χ. «έκδοση τιμολογίου στον 802012659 για 2 τεμ κωδ 10 ευρώ», «νέος πελάτης», «νέο είδος», «νέα σειρά», ή «πήγαινε στην καρτέλα». Αποθηκεύω πάντα ΠΡΟΧΕΙΡΟ — ΜΑΡΚ παίρνει το παραστατικό μόνο όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση».');}}
function cbClear(){$('#cbLog').innerHTML='';}
function cbAdd(text,who,actionsHtml){const log=$('#cbLog');const d=document.createElement('div');d.className='cbMsg '+who;d.innerHTML=esc(text).replace(/\n/g,'<br>')+(actionsHtml||'');log.appendChild(d);log.scrollTop=log.scrollHeight;return d;}
function cbMe(t){cbAdd(t,'me');}
function cbBot(t,actions){cbAdd(t,'bot',actions);cbSpeak(t);}
function cbSpeak(t){try{if(!window.speechSynthesis)return;const u=new SpeechSynthesisUtterance(t.replace(/[•✔]/g,''));u.lang=$('#cbLang').value;speechSynthesis.cancel();speechSynthesis.speak(u);}catch(e){}}
function cbSubmitText(){const t=$('#cbInput').value.trim();if(!t)return;$('#cbInput').value='';cbMe(t);cbHandle(t);}
// Speech recognition
function cbInitRec(){const SR=window.SpeechRecognition||window.webkitSpeechRecognition;if(!SR)return null;
  const r=new SR();r.interimResults=false;r.maxAlternatives=1;
  r.onresult=e=>{const t=e.results[0][0].transcript;$('#cbInput').value=t;cbSubmitText();};
  r.onend=()=>{cbRecOn=false;$('#cbMic').classList.remove('rec');};
  r.onerror=()=>{cbRecOn=false;$('#cbMic').classList.remove('rec');};return r;}
function cbToggleMic(){if(!cbRec)cbRec=cbInitRec();
  if(!cbRec){cbBot('Ο browser δεν υποστηρίζει φωνητική αναγνώριση — χρησιμοποίησε Chrome ή Edge (ή γράψε την εντολή).');return;}
  if(cbRecOn){cbRec.stop();return;}
  cbRec.lang=$('#cbLang').value;try{cbRec.start();cbRecOn=true;$('#cbMic').classList.add('rec');}catch(e){}}
// Helpers
function cbNum(re,t){const m=t.match(re);return m?parseFloat(m[1].replace(',','.')):null;}
function cbFindProd(s){for(const c in PRODMAP){const dsc=(PRODMAP[c].desc||'').toLowerCase();if(dsc.length>=4&&s.includes(dsc.slice(0,Math.min(8,dsc.length))))return c;}return '';}
// Intent router
async function cbHandle(t){const s=t.toLowerCase();
  const isIssue=/έκδοσ|εκδοσ|τιμολόγ|τιμολογ|παραστατ|issue|invoice/.test(s);
  // Navigation (not when it's an issue command)
  const nav=[['καρτέλ','card'],['καρτελ','card'],['πελάτ','customers'],['πελατ','customers'],['στατιστ','stats'],['δελτί','delivery'],['δελτι','delivery'],['σειρέ','series'],['σειρε','series'],['σειρά','series'],['σειρων','series'],['σειρών','series'],['είδη','products'],['ειδη','products'],['πρόχειρ','drafts'],['προχειρ','drafts'],['ρυθμίσ','settings'],['ρυθμισ','settings'],['ακύρωσ','cancel'],['ακυρωσ','cancel']];
  if(/πήγαινε|πηγαινε|άνοιξε|ανοιξε|go to|open|δείξε|δειξε|εμφάνισε/.test(s)&&!isIssue){
    for(const[k,v]of nav){if(s.includes(k)){showView(v);cbBot('Άνοιξα την ενότητα.');return;}}
    if(/έκδοσ|εκδοσ/.test(s)){showView('issue');cbBot('Άνοιξα την Έκδοση.');return;}}
  // Help
  if(/βοήθεια|βοηθεια|help|τι μπορείς|τι μπορεις|τι κάνεις/.test(s)){
    cbBot('Μπορώ (πάντα ως ΠΡΟΧΕΙΡΟ — καμία οριστική έκδοση/ΜΑΡΚ χωρίς εσένα):\n• «έκδοση τιμολογίου στον <ΑΦΜ> για <ποσότητα> <είδος> <τιμή> ευρώ»\n• «νέος πελάτης <ΑΦΜ>»\n• «νέο είδος <περιγραφή> <τιμή> ευρώ»\n• «νέα σειρά» (διαχείριση σειρών ανά τύπο)\n• «πήγαινε στην καρτέλα/πελάτες/είδη/σειρές/δελτίο/…»\n• «πόσα τιμολόγια φέτος»\n\nℹ️ Το παραστατικό παίρνει ΜΑΡΚ μόνο όταν πατήσεις εσύ το κόκκινο «Οριστική Έκδοση».');return;}
  // New series
  if(/νέα? σειρά|νεα? σειρα|new series|δημιούργησε σειρά|φτιάξε σειρά/.test(s)){
    showView('series');cbBot('Άνοιξα τη διαχείριση Σειρών. Διάλεξε τύπο παραστατικού, δώσε κωδικό σειράς (π.χ. Α, ΤΠΥ, ΔΑ) και πάτα «Δημιουργία σειράς».');return;}
  // Stats Q&A
  if(/πόσα τιμολ|ποσα τιμολ|τζίρο|τζιρο|στατιστικ|how many invoic|φέτος|εφετος/.test(s)&&!isIssue){
    cbBot('Φέρνω στατιστικά…');try{const d=await api({statistics:1,period:'year'});const y=(d.stats&&(d.stats.year||d.stats))||d.year||d;
      const cnt=y.count!==undefined?y.count:(d.count!==undefined?d.count:'—');const net=y.net!==undefined?y.net:(d.net!==undefined?d.net:0);
      cbBot('Φέτος: '+cnt+' παραστατικά, καθαρή αξία '+fmt(net||0)+' €.');}catch(e){cbBot('Δεν μπόρεσα να φέρω στατιστικά τώρα.');}return;}
  // New customer
  if(/νέος? πελάτ|νεος? πελατ|new customer|create customer|δημιούργησε πελάτ|φτιάξε πελάτ/.test(s)){
    const afm=(t.match(/\b(\d{9})\b/)||[])[1]||'';
    cbBot('Ανοίγω φόρμα νέου πελάτη'+(afm?(' για ΑΦΜ '+afm):'')+'. Έλεγξε τα στοιχεία και πάτα Αποθήκευση.');
    openCustomerModal(c=>{if(c)cbBot('✔ Ο πελάτης «'+(c.name||c.vat||'')+'» αποθηκεύτηκε.');},afm);return;}
  // New product / item
  if(/νέο είδ|νεο ειδ|νέο προϊ|νεο προι|new item|new product|create item|δημιούργησε είδ|φτιάξε είδ/.test(s)){
    const price=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)/i,t);
    let desc=t.replace(/^.*?(νέο είδ\S*|νεο ειδ\S*|νέο προϊ\S*|νεο προι\S*|new (?:item|product)|δημιούργησε είδ\S*|φτιάξε είδ\S*)/i,'').replace(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur).*/i,'').replace(/\bτιμή\b|\bτιμη\b/gi,'').trim();
    cbBot('Ανοίγω φόρμα νέου είδους'+(desc?(' «'+desc+'»'):'')+(price?(' τιμή '+price+'€'):'')+'. Έλεγξε και πάτα Αποθήκευση.');
    openProductModal('',c=>{if(c)cbBot('✔ Το είδος αποθηκεύτηκε.');});
    setTimeout(()=>{if(desc&&$('#pdDesc'))$('#pdDesc').value=desc;if(price&&$('#pdPrice'))$('#pdPrice').value=price;},180);return;}
  // Issue invoice → preview/draft
  if(isIssue){
    const afm=(t.match(/\b(\d{9})\b/)||[])[1]||'';
    const qty=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:τεμ|τεμάχ|τεμαχ|x|χ|ποσότ|ποσοτ)/i,t)||1;
    const price=cbNum(/(\d+(?:[.,]\d+)?)\s*(?:ευρώ|ευρω|€|eur)/i,t);
    let code=(t.match(/κωδ(?:ικός|ικος)?\s*([\w.\-]+)/i)||[])[1]||'';
    if(code&&!PRODMAP[code])code='';
    if(!code)code=cbFindProd(s);
    const o={afm,code,qty:qty||1,price};
    let sum='Θα ετοιμάσω ΠΡΟΧΕΙΡΟ παραστατικό:\n• Πελάτης: '+(afm||'(επίλεξέ τον στη φόρμα)')+'\n• Είδος: '+(code?(code+' '+(PRODMAP[code].desc||'')):'(επίλεξέ το στη φόρμα)')+'\n• Ποσότητα: '+(qty||1)+(price?(' • Τιμή: '+price+'€'):'');
    const id='__cbi'+Date.now();window[id]=o;
    cbBot(sum,`<div class="cbAct"><button class="go" onclick="cbDoIssue(window['${id}'])">✔ Ετοίμασε πρόχειρο</button><button onclick="showView('issue')">Άνοιξε φόρμα</button></div>`);return;}
  cbBot('Δεν το κατάλαβα. Πες «βοήθεια» για παραδείγματα.');
}
// Execute an issue command → fills the form and saves a DRAFT (preview) for review.
async function cbDoIssue(o){cbBot('Ετοιμάζω το πρόχειρο…');
  showView('issue');await loadIssueTypes();await new Promise(r=>setTimeout(r,200));
  if(o.afm){$('#iAfm').value=o.afm;if(/^\d{9}$/.test(o.afm)){lookupAfm();await new Promise(r=>setTimeout(r,700));}}
  $('#iLines tbody').innerHTML='';addLine(o.code||'',o.qty||1,o.price||'');
  const row=$('#iLines tbody tr:last-child');
  if(o.code&&PRODMAP[o.code]){pickProd(row.querySelector('.ln-code'),o.code);}
  if(o.price){row.querySelector('.ln-price').value=o.price;lineFromInputs(row);}
  await new Promise(r=>setTimeout(r,150));
  if(!collectLines().length){cbBot('Χρειάζεται είδος/τιμή — συμπλήρωσέ τα στη φόρμα και πάτα «Πρόχειρο».');return;}
  await submitInvoice(false);
  cbBot('✔ Το πρόχειρο ετοιμάστηκε. Έλεγξέ το εδώ ή στα «Πρόχειρα» και έκδωσέ το χειροκίνητα.');
}
$('#cbLang').addEventListener('change',()=>{if(cbRec)cbRec.lang=$('#cbLang').value;});

// boot
(async()=>{await initAccounts();loadInvTypes();await loadProductList();loadCustomers();showView('issue');})();
</script>
</body>
</html>
