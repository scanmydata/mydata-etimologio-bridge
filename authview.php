<?php // Login / signup / password-reset screen (included by app.php when logged out) ?>
<!DOCTYPE html>
<html lang="el">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>e-Timologio Pro — Σύνδεση</title>
<link rel="icon" type="image/png" sizes="32x32" href="assets/icons/favicon-32.png">
<link rel="icon" href="assets/icons/favicon.ico" sizes="any">
<link rel="apple-touch-icon" sizes="180x180" href="assets/icons/apple-touch-icon.png">
<style>
  :root{--bg:#0b1220;--panel:#131f33;--panel2:#18263d;--line:#2b3b54;--txt:#e6edf6;--muted:#93a4bd;--accent:#38bdf8;--accent2:#0ea5e9;--ok:#22c55e;--bad:#ef4444;--radius:14px;--shadow:0 10px 30px rgba(0,0,0,.4)}
  *{box-sizing:border-box} html,body{height:100%}
  body{margin:0;font-family:system-ui,'Segoe UI',Roboto,Arial,sans-serif;background:radial-gradient(1200px 600px at 70% -10%,#12233c,#0b1220);color:var(--txt);display:flex;align-items:center;justify-content:center;min-height:100vh}
  .box{width:min(420px,94%);background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);padding:26px 26px 22px}
  .brand{font-size:22px;font-weight:800;margin-bottom:2px}.brand span{color:var(--accent)}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px}
  .tabs{display:flex;gap:6px;margin-bottom:16px}
  .tabs button{flex:1;background:var(--panel2);border:1px solid var(--line);color:var(--muted);border-radius:9px;padding:9px;cursor:pointer;font:inherit;font-weight:600}
  .tabs button.on{background:var(--accent2);border-color:var(--accent2);color:#04222f}
  label{font-size:12px;color:var(--muted);display:block;margin:10px 0 4px}
  input{width:100%;background:var(--panel2);border:1px solid var(--line);color:var(--txt);border-radius:9px;padding:11px;font:inherit;outline:none}
  input:focus{border-color:var(--accent)}
  button.primary{width:100%;margin-top:16px;background:var(--accent2);border:1px solid var(--accent2);color:#04222f;font-weight:700;border-radius:9px;padding:12px;cursor:pointer;font:inherit}
  button.primary:hover{background:var(--accent)}
  .link{background:none;border:none;color:var(--accent);cursor:pointer;font:inherit;font-size:12px;padding:0;margin-top:12px}
  .msg{margin-top:14px;font-size:13px;padding:10px 12px;border-radius:9px;display:none}
  .msg.err{display:block;background:rgba(239,68,68,.12);color:#fca5a5;border:1px solid #7f1d1d55}
  .msg.ok{display:block;background:rgba(34,197,94,.12);color:#86efac;border:1px solid #14532d55}
  .foot{margin-top:16px;font-size:11px;color:var(--muted);text-align:center}
  form{display:none} form.on{display:block}
  /* Το «ματάκι» των κωδικών: κάθεται ΜΕΣΑ στο πεδίο, δεξιά. */
  .pw{position:relative}
  .pw input{padding-right:42px}
  .pw .eye{position:absolute;top:50%;right:6px;transform:translateY(-50%);width:30px;height:30px;
    display:flex;align-items:center;justify-content:center;background:none;border:0;cursor:pointer;
    color:var(--muted);font-size:15px;line-height:1;padding:0;border-radius:7px}
  .pw .eye:hover{color:var(--accent);background:rgba(56,189,248,.12)}
</style>
</head>
<body>
<div class="box">
  <div class="brand">e-Timologio <span>Pro</span></div>
  <div class="sub" id="subtitle">Συνδεθείτε στον λογαριασμό της επιχείρησής σας</div>

  <?php if ($__resetToken !== ''): ?>
  <!-- RESET MODE -->
  <form id="f-reset" class="on" onsubmit="return doReset(event)">
    <label>Νέος κωδικός (≥ 8 χαρακτήρες)</label>
    <input type="password" id="r-pass" autocomplete="new-password" required>
    <label>Επιβεβαίωση κωδικού</label>
    <input type="password" id="r-pass2" autocomplete="new-password" required>
    <input type="hidden" id="r-token" value="<?= htmlspecialchars($__resetToken, ENT_QUOTES) ?>">
    <button class="primary" type="submit">Ορισμός κωδικού</button>
    <div style="text-align:center"><button type="button" class="link" onclick="location.href='app.php'">← Επιστροφή στη σύνδεση</button></div>
  </form>
  <?php else: ?>
  <div class="tabs">
    <button id="t-login" class="on" onclick="tab('login')">Σύνδεση</button>
    <button id="t-signup" onclick="tab('signup')">Εγγραφή</button>
    <button id="t-forgot" onclick="tab('forgot')">Ξέχασα κωδικό</button>
  </div>

  <form id="f-login" class="on" onsubmit="return doLogin(event)">
    <label>Email</label><input type="email" id="l-email" autocomplete="username" required>
    <label>Κωδικός</label><input type="password" id="l-pass" autocomplete="current-password" required>
    <button class="primary" type="submit">Σύνδεση</button>
  </form>

  <form id="f-signup" onsubmit="return doSignup(event)">
    <label>Επωνυμία επιχείρησης</label><input type="text" id="s-name" required>
    <label>Email</label><input type="email" id="s-email" autocomplete="email" required>
    <label>Κωδικός (≥ 8 χαρακτήρες)</label><input type="password" id="s-pass" autocomplete="new-password" required>
    <button class="primary" type="submit">Δημιουργία λογαριασμού</button>
    <div class="foot">Η εγγραφή εγκρίνεται από τον διαχειριστή πριν την πρώτη σύνδεση.</div>
  </form>

  <form id="f-forgot" onsubmit="return doForgot(event)">
    <label>Email</label><input type="email" id="fg-email" autocomplete="email" required>
    <button class="primary" type="submit">Αποστολή οδηγιών επαναφοράς</button>
    <div class="foot">Θα λάβετε σύνδεσμο επαναφοράς αν υπάρχει λογαριασμός.</div>
  </form>

  <!-- 2FA step (shown after a correct password when authenticator is enabled) -->
  <form id="f-2fa" onsubmit="return do2fa(event)">
    <label>Κωδικός authenticator (6 ψηφία)</label>
    <input type="text" id="tf-code" inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="••••••" required style="letter-spacing:6px;text-align:center;font-size:20px">
    <button class="primary" type="submit">Επαλήθευση & Σύνδεση</button>
    <div style="text-align:center"><button type="button" class="link" onclick="back2fa()">← Πίσω</button></div>
    <div class="foot">Άνοιξε την εφαρμογή authenticator και δώσε τον τρέχοντα κωδικό.</div>
  </form>
  <?php endif; ?>

  <div class="msg" id="msg"></div>
  <div class="foot">🔒 Τα δεδομένα αποθηκεύονται κρυπτογραφημένα</div>
</div>

<script>
const API='etimologio.php';
function msg(t,ok){const m=document.getElementById('msg');m.textContent=t;m.className='msg '+(ok?'ok':'err');}
function tab(w){['login','signup','forgot'].forEach(x=>{document.getElementById('f-'+x).classList.toggle('on',x===w);document.getElementById('t-'+x).classList.toggle('on',x===w);});document.getElementById('msg').className='msg';
  document.getElementById('subtitle').textContent=w==='login'?'Συνδεθείτε στον λογαριασμό της επιχείρησής σας':w==='signup'?'Δημιουργήστε λογαριασμό επιχείρησης':'Επαναφορά κωδικού πρόσβασης';}
const g=id=>document.getElementById(id);
async function post(params){const b=new URLSearchParams(params);const r=await fetch(API,{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b});return r.json();}
function show2fa(on){
  ['login','signup','forgot'].forEach(x=>g('f-'+x).classList.remove('on'));
  const tabsEl=document.querySelector('.tabs');if(tabsEl)tabsEl.style.display=on?'none':'';
  g('f-2fa').classList.toggle('on',on);
  g('subtitle').textContent=on?'Επαλήθευση δύο παραγόντων (2FA)':'Συνδεθείτε στον λογαριασμό της επιχείρησής σας';
  if(on)setTimeout(()=>g('tf-code').focus(),50);
}
function back2fa(){g('tf-code').value='';show2fa(false);g('f-login').classList.add('on');g('msg').className='msg';}
async function doLogin(e){e.preventDefault();try{const d=await post({auth:'login',email:g('l-email').value,password:g('l-pass').value});
  if(d.success){location.href='app.php';}
  else if(d.totp_required){msg('');show2fa(true);}
  else msg(d.error||'Αποτυχία');}catch(x){msg('Σφάλμα δικτύου');}return false;}
async function do2fa(e){e.preventDefault();try{const d=await post({auth:'login_totp',code:g('tf-code').value});
  if(d.success){location.href='app.php';}else msg(d.error||'Αποτυχία');}catch(x){msg('Σφάλμα δικτύου');}return false;}
async function doSignup(e){e.preventDefault();try{const d=await post({auth:'signup',email:g('s-email').value,password:g('s-pass').value,business_name:g('s-name').value});if(d.success){msg(d.note||'Η εγγραφή καταχωρήθηκε.',true);tab('login');}else msg(d.error||'Αποτυχία');}catch(x){msg('Σφάλμα δικτύου');}return false;}
async function doForgot(e){e.preventDefault();try{const d=await post({auth:'forgot',email:g('fg-email').value});msg(d.note||'Στάλθηκαν οδηγίες.',true);}catch(x){msg('Σφάλμα δικτύου');}return false;}
async function doReset(e){e.preventDefault();if(g('r-pass').value!==g('r-pass2').value){msg('Οι κωδικοί δεν ταιριάζουν');return false;}try{const d=await post({auth:'reset',token:g('r-token').value,password:g('r-pass').value});if(d.success){msg('Ο κωδικός ενημερώθηκε. Ανακατεύθυνση…',true);setTimeout(()=>location.href='app.php',1200);}else msg(d.error||'Αποτυχία');}catch(x){msg('Σφάλμα δικτύου');}return false;}

// Ματάκι σε ΚΑΘΕ πεδίο κωδικού, χωρίς να αλλάξει η κάθε φόρμα ξεχωριστά: ένα
// πεδίο που ξεχνιέται είναι ακριβώς εκείνο όπου θα χρειαστεί.
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
addEyes();
</script>
</body>
</html>
