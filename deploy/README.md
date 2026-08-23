# `deploy/` — τα αρχεία που στήνουν τον container

Ο **οδηγός** του στησίματος ζει στη ρίζα του repo, όχι εδώ:

- [`DEPLOY.md`](../DEPLOY.md) — Coolify / Docker Compose, μεταβλητές
  περιβάλλοντος, το volume `/data`, **σύνδεση εταιρειών με τα κλειδιά ΑΑΔΕ**,
  έλεγχος ότι δουλεύει, μεταφορά τοπικών δεδομένων.
- [`CLOUDFLARED.md`](../CLOUDFLARED.md) — πώς μπαίνει η θύρα 8090 σε υπάρχον
  tunnel της Cloudflare.

Αυτός ο φάκελος έχει μόνο τα κομμάτια που μπαίνουν **μέσα** στο image:

| Αρχείο | Τι κάνει |
|---|---|
| [`entrypoint.sh`](entrypoint.sh) | Παράγει το `config.php` από τα env στο boot (κανένα μυστικό στο image), γράφει τα όρια PHP, περιμένει τη βάση, ξεκινά τον χρονοπρογραμματιστή ανά λεπτό και παραδίδει στον Apache |
| [`dburl.php`](dburl.php) | Σπάει το `DATABASE_URL` του Coolify (`postgres://user:pass@host:5432/db`) σε `DB_DSN` / `DB_USER` / `DB_PASS` — έτσι η ρύθμιση της βάσης είναι μία επικόλληση |
| [`php.ini`](php.ini) | Ρυθμίσεις παραγωγής: σφάλματα μόνο στα logs, όρια μνήμης/χρόνου/upload για τις μαζικές εξαγωγές, ώρα Ελλάδας, σκληρότερο cookie συνεδρίας, opcache |
| [`apache-etimologio.conf`](apache-etimologio.conf) | Σερβίρονται μόνο `app.php`, `etimologio.php`, `healthz.php` και τα `assets/`· κόβονται μυστικά, εργαλεία, τεκμηρίωση και αρχεία βιβλιοθήκης· κεφαλίδες ασφαλείας· `/` σερβίρει το `app.php` (DirectoryIndex, χωρίς redirect)· ανέβασμα σε HTTPS όταν το `X-Forwarded-Proto` λέει `http` |

Καμία από αυτές τις ρυθμίσεις δεν αφορά την **τοπική/offline** λειτουργία της
εφαρμογής υπολογιστή: εκείνη σηκώνει τη δική της φορητή PHP με δικό της
`php.ini`.

Έλεγχος μετά από κάθε deploy, μέσα από τον container:

```bash
php tools/pg_smoke.php
```
