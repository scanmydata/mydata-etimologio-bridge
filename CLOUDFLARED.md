# cloudflared — έκθεση του e‑Τιμολόγιο Pro στο internet

> **Για τον agent/διαχειριστή που στήνει το cloudflared.** Ο server τρέχει **ήδη
> άλλες live υπηρεσίες** πίσω από cloudflared. Μην στήσεις νέο tunnel και μην
> αγγίξεις τις υπάρχουσες εγγραφές — **πρόσθεσε ένα ακόμη hostname** στο tunnel
> που ήδη δουλεύει.

## Τι πρέπει να εκτεθεί

Ένα και μόνο πράγμα: ο container `etimologio`, **HTTP στη θύρα 8080**.

| | |
|---|---|
| Πρωτόκολλο origin | `http` (όχι https — το TLS το κάνει η Cloudflare) |
| Θύρα | `8080` |
| Health endpoint | `GET /healthz.php` → `ok` |
| Προτεινόμενο hostname | π.χ. `timologio.<το-domain-σου>` |

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

  - hostname: timologio.example.gr
    service: http://etimologio:8080          # δες §3 για το σωστό host
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
      # Το κατέβασμα PDF από την ΑΑΔΕ και η μαζική εκτύπωση μπορεί να αργήσουν.
      httpHostHeader: timologio.example.gr

  - service: http_status:404                 # μένει ΤΕΛΕΥΤΑΙΟ
```

Η σειρά μετράει: το cloudflared παίρνει τον **πρώτο** κανόνα που ταιριάζει.

```bash
cloudflared tunnel ingress validate         # έλεγχος πριν το restart
sudo systemctl reload cloudflared           # ή: docker restart cloudflared
```

Και η DNS εγγραφή:

```bash
cloudflared tunnel route dns <TUNNEL> timologio.example.gr
```

### 2β. Tunnel από το dashboard

Zero Trust → **Networks → Tunnels** → το tunnel σου → **Public Hostnames** →
**Add a public hostname**:

- Subdomain `timologio`, Domain το δικό σου
- Type **HTTP**, URL `etimologio:8080` (ή δες §3)
- Additional settings → **No TLS Verify: On**

### 3. Ποιο host:port να βάλεις

Εξαρτάται από το πού τρέχει το cloudflared:

| Το cloudflared τρέχει… | Βάλε |
|---|---|
| σε container **στο ίδιο docker network** με την εφαρμογή | `http://etimologio:8080` |
| σε container σε **άλλο** network | βάλε το στο ίδιο network, ή `http://<ip-του-host>:8080` |
| ως **systemd service στον host** | `http://127.0.0.1:8080` |
| με **Coolify** | συνήθως ο proxy του Coolify — δείξε στο service name που δίνει το Coolify |

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
curl -s http://localhost:8080/healthz.php                       # → ok

# από τον container του cloudflared (ότι βλέπει το origin)
docker exec cloudflared wget -qO- http://etimologio:8080/healthz.php

# απ' έξω, μετά το DNS
curl -s https://timologio.example.gr/healthz.php                 # → ok
curl -sI https://timologio.example.gr/app.php | head -3          # → 200/302
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
  ακόμη κι όταν η βάση ή η ΑΑΔΕ είναι εκτός. Δεν αποκαλύπτει τίποτα.
- Μετά το στήσιμο, γράψε το τελικό hostname στο `APP_URL` της εφαρμογής και
  κάνε redeploy — χρησιμοποιείται στους συνδέσμους των email.
