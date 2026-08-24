# e-Τιμολόγιο Pro — shared backend (web UI + JSON API)
#
# One container serves both halves of the product: the browser UI (app.php) for
# client businesses and the JSON API that the desktop app talks to in thin-client
# mode. Deployed on the home server/VPS through Coolify, which builds from the
# repo, injects the env below and routes to port 8090 (cloudflared in front).
#
# Build:  docker build -t etimologio .
# Run:    docker run -p 8090:8090 --env-file .env -v etim-data:/data etimologio

FROM php:8.3-apache

# Extensions:
#   pdo_pgsql  → the shared Postgres (Coolify service); pdo_sqlite stays for
#                single-file installs and the one-off local→server migration
#   mbstring   → Greek text handling throughout
#   zip        → ONLY for reading .xlsx bank statements (bankimport.php). Writing
#                ZIPs never uses it: zipwriter.php emits archives with zlib, so
#                the same code also runs on the portable PHP the desktop bundles
#   sodium     → crypto.php (at-rest encryption). Already compiled into most
#                official images; built here only when it is missing
#
# The build follows the official docker-php idiom (savedAptMark + ldd): the -dev
# headers are dropped afterwards while the RUNTIME libraries the freshly built
# .so files link against (libpq5, libzip4, libonig5, libsodium23) are marked
# manual so `--auto-remove` cannot take them with it. A plain
# `apt-get purge --auto-remove libpq-dev` removes libpq5 as well and pdo_pgsql
# then fails to load — the database would be unreachable with only a startup
# warning in the log.
#
# Το `readlink -f` πριν το `dpkg-query -S` δεν είναι στολίδι. Το `ldd`
# δείχνει το symlink του SONAME (…/libzip.so.5)· ρώτα το dpkg ποιος το
# κατέχει και δεν απαντά τίποτα, το πακέτο μένει «auto», και το
# `--auto-remove` το σβήνει. Έτσι ακριβώς εξαφανίστηκε η libzip ενώ το
# `zip` έμενε ενεργό στο ini: ΚΑΘΕ αίτημα κατέγραφε «Unable to load
# dynamic library zip» και η εισαγωγή .xlsx από τράπεζα ήταν νεκρή σε
# έναν server που έδειχνε υγιέστατος. Λύνοντας πρώτα το symlink, δίνουμε
# στο dpkg ένα αρχείο που όντως κατέχει.
#
# Ο βρόχος στο τέλος είναι ο φύλακας: μια επέκταση που λείπει ΡΙΧΝΕΙ ΤΟ
# BUILD, αντί να βγάλει εικόνα που ξεκινά μια χαρά και αστοχεί αργότερα.
#
# Το `postgresql-client` (pg_dump) δεν είναι εργαλείο μεταγλώττισης: το τρέχει
# ο ΙΔΙΟΣ ο server για το ημερήσιο αντίγραφο. Γι' αυτό σημειώνεται `manual`,
# ώστε να επιβιώσει του `--auto-remove`, και ελέγχεται στο τέλος μαζί με τις
# επεκτάσεις — αλλιώς το αντίγραφο θα αποτύγχανε στις 3 τα ξημερώματα, σιωπηλά,
# με μια γραμμή σε ένα log που δεν διαβάζει κανείς.
RUN set -eux; \
    savedAptMark="$(apt-mark showmanual)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        libsqlite3-dev \
        libzip-dev \
        libonig-dev \
        libsodium-dev \
        ca-certificates \
        postgresql-client; \
    docker-php-ext-install -j"$(nproc)" \
        pdo_pgsql \
        pdo_sqlite \
        mbstring \
        zip; \
    php -m | grep -qi '^sodium$' || docker-php-ext-install -j"$(nproc)" sodium; \
    apt-mark auto '.*' > /dev/null; \
    apt-mark manual $savedAptMark > /dev/null; \
    apt-mark manual postgresql-client > /dev/null; \
    ldd "$(php -r 'echo ini_get("extension_dir");')"/*.so \
        | awk '/=>/ { print $3 }' | sort -u | grep -v '^$' \
        | xargs -r readlink -f | sort -u \
        | xargs -r dpkg-query -S 2>/dev/null | cut -d: -f1 | sort -u \
        | xargs -r apt-mark manual; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*; \
    for ext in pdo_pgsql pdo_sqlite mbstring zip sodium; do \
        php -m | grep -Eq "^${ext}$" || { echo "MISSING PHP EXTENSION: $ext" >&2; exit 1; }; \
    done; \
    pg_dump --version > /dev/null

# Apache: rewrite/headers on, listen where Coolify and cloudflared expect (8090),
# and a ServerName so startup does not warn on every boot.
#
# NOT 8080: on this home server Coolify itself already answers there, so an app
# on 8080 either refuses to bind or shadows the panel. 8090 is the app's port
# everywhere -- EXPOSE, healthcheck, compose, the Coolify "Ports" field and the
# cloudflared ingress must all say the same number.
RUN a2enmod rewrite headers \
 && sed -ri 's/^Listen 80$/Listen 8090/' /etc/apache2/ports.conf \
 && sed -ri 's!<VirtualHost \*:80>!<VirtualHost *:8090>!' /etc/apache2/sites-available/000-default.conf \
 && printf 'ServerName etimologio\n' > /etc/apache2/conf-available/servername.conf \
 && a2enconf servername

# Hardening + PHP limits. The base image ships NO php.ini at all, which means
# PHP's built-in defaults apply: display_errors ON (stack traces with the DSN
# straight to the browser), memory_limit 128M and max_execution_time 30s — too
# little for a bulk PDF/ZIP export.
COPY deploy/php.ini /usr/local/etc/php/conf.d/etimologio.ini
COPY deploy/apache-etimologio.conf /etc/apache2/conf-available/etimologio.conf
RUN a2enconf etimologio

WORKDIR /var/www/html
COPY . /var/www/html/

# Runtime state lives on a volume: the encryption key, per-account AADE cookie
# jars and (for SQLite installs) the database. Losing .enckey makes stored data
# unreadable, so it must never live in the image layer.
#
# The web root itself is NOT writable by the web user: the app only ever writes
# under /data, and a writable document root turns any file-write bug into remote
# code execution. config.php is rendered by the entrypoint (running as root) and
# handed to www-data read-only.
RUN mkdir -p /data/.cookies \
 && chown -R www-data:www-data /data \
 && chown -R root:www-data /var/www/html \
 && chmod -R g-w,o-rwx /var/www/html \
 && rm -f /var/www/html/config.php

ENV ETIM_DATA_DIR=/data \
    PHP_MEMORY_LIMIT=512M \
    PHP_MAX_EXECUTION_TIME=300 \
    PHP_UPLOAD_MAX_FILESIZE=32M \
    TZ=Europe/Athens

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh

# Ο μεταφραστής του connection string (DATABASE_URL → DSN/χρήστης/κωδικός) ζει
# δίπλα στο entrypoint, ώστε να μη χρειάζεται το web root για να ξεκινήσει.
COPY deploy/dburl.php /usr/local/bin/dburl.php

RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD php -r 'exit(@file_get_contents("http://127.0.0.1:8090/healthz.php")==="ok"?0:1);'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["apache2-foreground"]
