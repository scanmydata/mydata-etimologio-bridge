# e-Τιμολόγιο Pro — shared backend (web UI + JSON API)
#
# One container serves both halves of the product: the browser UI (app.php) for
# client businesses and the JSON API that the desktop app talks to in thin-client
# mode. Deployed on the VPS through Coolify, which builds from the repo, injects
# the env below and puts TLS/routing in front.
#
# Build:  docker build -t etimologio .
# Run:    docker run -p 8080:8080 --env-file .env -v etim-data:/data etimologio

FROM php:8.3-apache

# pdo_pgsql → the shared Postgres on the VPS; pdo_sqlite stays for single-file
# installs and for the one-off local→server migration. zip is NOT required:
# zipwriter.php emits archives with zlib only, so the same code runs on the
# portable PHP the desktop bundles.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpq-dev libzip-dev libonig-dev cron ca-certificates \
 && docker-php-ext-install -j"$(nproc)" pdo_pgsql pdo_sqlite mbstring \
 && apt-get purge -y --auto-remove libpq-dev libzip-dev libonig-dev \
 && rm -rf /var/lib/apt/lists/*

# Apache: pretty errors off, rewrite on, listen where Coolify expects.
RUN a2enmod rewrite headers \
 && sed -ri 's/^Listen 80$/Listen 8080/' /etc/apache2/ports.conf \
 && sed -ri 's!<VirtualHost \*:80>!<VirtualHost *:8080>!' /etc/apache2/sites-available/000-default.conf

WORKDIR /var/www/html
COPY . /var/www/html/

# Runtime state lives on a volume: the encryption key, per-account AADE cookie
# jars and (for SQLite installs) the database. Losing .enckey makes stored data
# unreadable, so it must never live in the image layer.
RUN mkdir -p /data/.cookies \
 && chown -R www-data:www-data /data /var/www/html \
 && rm -f /var/www/html/config.php

ENV ETIM_DATA_DIR=/data \
    PHP_MEMORY_LIMIT=256M

COPY deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD php -r 'exit(@file_get_contents("http://127.0.0.1:8080/healthz.php")==="ok"?0:1);'

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["apache2-foreground"]
