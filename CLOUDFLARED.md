# cloudflared — έκθεση του e‑Τιμολόγιο Pro στο internet

> **Για τον agent/διαχειριστή που στήνει το cloudflared.** Ο server τρέχει **ήδη
> άλλες live υπηρεσίες** πίσω από cloudflared. Μην στήσεις νέο tunnel και μην
> αγγίξεις τις υπάρχουσες εγγραφές — **πρόσθεσε ένα ακόμη hostname** στο tunnel
> που ήδη δουλεύει.

## Τι πρέπει να εκτεθεί

Ένα και μόνο πράγμα: ο container `etimologio`, **HTTP στη θύρα 8090**.

> Όχι 8080: εκεί απαντά **το ίδιο το Coolify** σε αυτόν τον server. Αν δείξεις
> το tunnel στην 8080 θα βγάλεις τον πίνακα του Coolify στο internet, όχι την
> εφαρμογή.

| | |
|---|---|
| Πρωτόκολλο origin | `http` (όχι https — το TLS το κάνει η Cloudflare) |
| Θύρα | `8090` |
| Health endpoint | `GET /healthz.php` → `ok` (και `?db=1` για «απαντά και η βάση») |
| Hostname | `etimologiopro.scanmydata.gr` |

Ποιος το χρησιμοποιεί: οι πελάτες‑επιχειρήσεις από browser (`/app.php`) **και**
η εφαρμογή υπολογιστή σε λειτουργία thin client (`/etimologio.php`). Είναι το
**ίδιο** hostname και για τα δύο — μην τα χωρίσεις.

---

## Βήματα

### 1. Βρες το υπάρχον tunnel

```bash
cloudflared tunnel list
sudo systemctl status cloudflared          # ή: docker ps | grep cloudflared
```

Εντόπισε **πού ζει το config** — συνήθως `/etc/cloudflared/config.yml` ή, αν
τρέχει σε container, το mounted config. Αν το tunnel διαχειρίζεται από το
**dashboard** (Zero Trust → Networks → Tunnels), τότε **δεν υπάρχει τοπικό
ingress** και η προσθήκη γίνεται από το dashboard (βήμα 2β).

### 2α. Tunnel με τοπικό `config.yml`

Πρόσθεσε **πάνω** από τον τελικό `service: http_status:404` κανόνα:

```yaml
ingress:
  # …οι υπάρχουσες εγγραφές — ΜΗΝ τις πειράξεις…

  - hostname: etimologiopro.scanmydata.gr
    service: http://etimologio:8090          # δες §3 για το σωστό host
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      # Το κατέβασμα PDF από την ΑΑΔΕ και η μαζική εκτύπωση μπορεί να αργήσουν.
      httpHostHeader: etimologiopro.scanmydata.gr

  - service: http_status:404                 # μένει ΤΕΛΕΥΤΑΙΟ
```

Η σειρά μετράει: το cloudflared παίρνει τον **πρώτο** κανόνα που ταιριάζει.

```bash
cloudflared tunnel ingress validate         # έλεγχος πριν το restart
sudo systemctl reload cloudflared           # ή: docker restart cloudflared
```

Και η DNS εγγραφή:

```bash
cloudflared tunnel route dns <TUNNEL> etimologiopro.scanmydata.gr
```

### 2β. Tunnel από το dashboard

Zero Trust → **Networks → Tunnels** → το tunnel σου → **Public Hostnames** →
**Add a public hostname**:

- Subdomain `timologio`, Domain το δικό σου
- Type **HTTP**, URL `etimologio:8090` (ή δες §3)
- Additional settings → **No TLS Verify: On**

### 3. Ποιο host:port να βάλεις

Εξαρτάται από το πού τρέχει το cloudflared:

| Το cloudflared τρέχει… | Βάλε |
|---|---|
| σε container **στο ίδιο docker network** με την εφαρμογή | `http://etimologio:8090` |
| σε container σε **άλλο** network | βάλε το στο ίδιο network, ή `http://<ip-του-host>:8090` |
| ως **systemd service στον host** | `http://127.0.0.1:8090` |
| με **Coolify** | ο proxy του Coolify (Traefik). Στο ingress βάλε το URL που δείχνει το Coolify για την εφαρμογή· εναλλακτικά, βάλε το cloudflared στο δίκτυο του Coolify και δείξε απευθείας `http://<service>:8090` |

Αν το compose του repo τρέχει αυτούσιο, το service ονομάζεται **`etimologio`**
και το network **`etimologio_net`**. Για να μπει το cloudflared εκεί:

```yaml
# στο compose του cloudflared
services:
  cloudflared:
    networks: [etimologio_net]
networks:
  etimologio_net:
    external: true
```

---

## Έλεγχος

```bash
# από τον server, πριν το tunnel
curl -s http://localhost:8090/healthz.php                       # → ok

# από τον container του cloudflared (ότι βλέπει το origin)
docker exec cloudflared wget -qO- http://etimologio:8090/healthz.php

# απ' έξω, μετά το DNS
curl -s https://etimologiopro.scanmydata.gr/healthz.php                 # → ok
curl -sI https://etimologiopro.scanmydata.gr/app.php | head -3          # → 200/302
```

Αν το `/healthz.php` απαντά έξω αλλά το `/app.php` όχι, το πρόβλημα είναι στην
εφαρμογή (δες `DEPLOY.md`), όχι στο tunnel.

---

## Σημαντικά

- **Μη βάλεις Cloudflare Access** μπροστά στο hostname. Η εφαρμογή υπολογιστή
  μιλά με cookie‑based login· ένα Access interstitial θα την έκοβε. Αν θέλεις
  Access, βάλ' το σε **ξεχωριστό** hostname μόνο για browser χρήση.
- **WebSockets δεν χρειάζονται** — όλα είναι απλά HTTP requests.
- **Μεγάλα responses:** η μαζική εξαγωγή ZIP μπορεί να φτάσει δεκάδες MB. Άφησε
  τα default της Cloudflare· μη βάλεις επιθετικό caching σε `/etimologio.php`
  (είναι δυναμικό API — ιδανικά `Cache-Control: no-store` ή Page Rule bypass).
- **Το `/healthz.php` είναι δημόσιο και ανώνυμο** — σκόπιμα, ώστε να απαντά
  ακόμη κι όταν η βάση ή η ΑΑΔΕ είναι εκτός. Δεν αποκαλύπτει τίποτα: το `?db=1`
  λέει μόνο `ok` ή `db-down`, ποτέ DSN, χρήστη ή μήνυμα σφάλματος.
- **Rate limiting αντί για Access.** Το login είναι απλό POST στο
  `/etimologio.php` με `auth=login`. Ένα Rate Limiting rule της Cloudflare
  (π.χ. 10 αιτήματα/λεπτό ανά IP σε αυτό το path) κόβει τις επαναλαμβανόμενες
  απόπειρες χωρίς να ενοχλεί κανέναν πραγματικό χρήστη — η εφαρμογή δεν έχει
  δικό της throttling.
- **Μην ενεργοποιήσεις «restore original IP» στο origin** (mod_remoteip ή
  παρόμοιο) χωρίς λόγο. Η εφαρμογή εμπιστεύεται το loopback για τον
  χρονοπρογραμματιστή· κρατά και δεύτερο έλεγχο (απουσία κεφαλίδων proxy), αλλά
  ο απλούστερος δρόμος είναι να μένει η `REMOTE_ADDR` αυτή του proxy.
- Μετά το στήσιμο, γράψε το τελικό hostname στο `APP_URL` της εφαρμογής και
  κάνε redeploy — χρησιμοποιείται στους συνδέσμους των email.
