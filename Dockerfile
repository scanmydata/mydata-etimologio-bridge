# e-Τιμολόγιο Pro — shared backend (web UI + JSON API)
#
# One container serves both halves of the product: the browser UI (app.php) for
# client businesses and the JSON API that the desktop app talks to in thin-client
# mode. Deployed on the home server/VPS through Coolify, which builds from the
# repo, injects the env below and routes to port 8080 (cloudflared in front).
#
# Build:  docker build -t etimologio .
# Run:    docker run -p 8080:8080 --env-file .env -v etim-data:/data etimologio

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
RUN set -eux; \
    savedAptMark="$(apt-mark showmanual)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        libsqlite3-dev \
        libzip-dev \
        libonig-dev \
        libsodium-dev \
        ca-certificates; \
    docker-php-ext-install -j"$(nproc)" \
        pdo_pgsql \
        pdo_sqlite \
        mbstring \
        zip; \
    php -m | grep -qi '^sodium$' || docker-php-ext-install -j"$(nproc)" sodium; \
    apt-mark auto '.*' > /dev/null; \
    apt-mark manual $savedAptMark > /dev/null; \
    ldd "$(php -r 'echo ini_get("extension_dir");')"/*.so \
        | awk '/=>/ { print $3 }' | sort -u | grep -v '^$' \
        | xargs -r dpkg-query -S 2>/dev/null | cut -d: -f1 | sort -u \
        | xargs -r apt-mark manual; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*; \
    php -m | grep -Eq '^(pdo_pgsql)$'; \
    php -m | grep -Eq '^(sodium)$'

# Apache: rewrite/headers on, listen where Coolify and cloudflared expect (8080),
# and a ServerName so startup does not warn on every boot.
RUN a2enmod rewrite headers \
 && sed -ri 's/^Listen 80$/Listen 8080/' /etc/apache2/ports.conf \
 && sed -ri 's!<VirtualHost \*:80>!<VirtualHost *:8080>!' /etc/apache2/sites-available/000-default.conf \
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

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD php -r 'exit(@file_get_contents("http://127.0.0.1:8080/healthz.php")==="ok"?0:1);'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

CMD ["apache2-foreground"]
