# Déploiement Cantateo sur Hetzner VPS

## Serveur actuel

- **IP** : `5.75.146.72`
- **OS** : Ubuntu 22.04 LTS
- **Type** : CX21 (2 vCPU, 4 GB RAM, 40 GB SSD)
- **Domaine actif** : `www.cantateo.fr`

## Architecture

```
Internet → Nginx (reverse proxy + SSL) → Gunicorn (Unix socket) → Django
                                                 ↓                    ↓
                                             Celery worker      PostgreSQL
                                                 ↓                    ↓
                                              Redis cache      Cloudflare R2 (médias)
```

## Emplacements sur le serveur

| Chemin | Description |
|--------|-------------|
| `/var/www/cantateo/` | Application Django |
| `/var/www/cantateo/venv/` | Environnement virtuel Python |
| `/var/www/cantateo/.env` | Variables d'environnement |
| `/var/www/cantateo/staticfiles/` | Fichiers statiques collectés |
| `/var/www/cantateo/cantateo.sock` | Socket Unix Gunicorn |
| `/var/log/cantateo/` | Logs Gunicorn |
| `/var/log/nginx/` | Logs Nginx |
| `/etc/systemd/system/cantateo.service` | Service systemd |
| `/etc/systemd/system/cantateo-worker.service` | Worker Celery |
| `/etc/systemd/system/cantateo-omr-worker.service` | Worker Celery OMR |
| `/etc/systemd/system/cantateo-audio-backfill.timer` | Timer de remplissage audio basse priorité |
| `/etc/nginx/sites-available/cantateo` | Config Nginx |

---

## Commandes courantes

### Gestion du service

```bash
# Statut
systemctl status cantateo
systemctl status cantateo-worker
systemctl status cantateo-omr-worker
systemctl status cantateo-audio-backfill.timer

# Redémarrer l'application
systemctl restart cantateo
systemctl restart cantateo-worker
systemctl restart cantateo-omr-worker

# Voir les logs en temps réel
journalctl -u cantateo -f
journalctl -u cantateo-worker -f
journalctl -u cantateo-omr-worker -f
journalctl -u cantateo-audio-backfill.service -f
```

### Déployer une mise à jour

```bash
su - cantateo
cd /var/www/cantateo
git pull origin master
source venv/bin/activate
pip install -r requirements.txt -c requirements-lock.txt
python manage.py migrate
python manage.py collectstatic --no-input
exit
systemctl restart cantateo
systemctl restart cantateo-worker
```

Le script `deploy/deploy.sh` applique aussi les contraintes `requirements-lock.txt`,
vérifie les migrations, puis redémarre les services.

### Modifier la beta depuis smartphone

Flux recommandé pour modifier le code depuis mobile :

1. Demander la modification à Codex Cloud et ouvrir une PR vers
   `beta-catalogue`.
2. Relire puis fusionner la PR depuis GitHub mobile.
3. Ouvrir GitHub Actions, lancer manuellement `Deploy beta`, puis vérifier
   `https://beta.cantateo.fr/healthz`.

Le workflow `Deploy beta` déploie uniquement `beta.cantateo.fr`. Il cible
toujours `beta-catalogue` et refuse de se connecter au serveur si le dernier
commit de cette branche n'a pas une CI `push` terminée avec succès.
Le fichier `.github/workflows/deploy-beta.yml` doit rester présent sur `master`
pour que GitHub affiche le bouton manuel `workflow_dispatch`.

Secrets GitHub nécessaires :

- `HETZNER_HOST` : `5.75.146.72`
- `HETZNER_SSH_USER` : `root`
- `HETZNER_SSH_PRIVATE_KEY` : clé privée SSH autorisée sur le VPS
- `HETZNER_KNOWN_HOSTS` : empreinte SSH du serveur

Générer `HETZNER_KNOWN_HOSTS` depuis une machine de confiance :

```bash
ssh-keyscan -H 5.75.146.72
```

### Nginx

```bash
# Tester la config
nginx -t

# Recharger
systemctl reload nginx
```

---

## Recréer le serveur depuis zéro

### Étape 1 : Commander le serveur Hetzner

1. [hetzner.com/cloud](https://www.hetzner.com/cloud) → Add Server
2. Location : Nuremberg (Allemagne)
3. Image : Ubuntu 22.04
4. Type : CX21 (~4€/mois)
5. SSH Key : Ajouter ta clé publique

### Étape 2 : Connexion et mise à jour

```bash
ssh root@<IP_SERVEUR>
apt update && apt upgrade -y
```

### Étape 3 : Installer les dépendances

```bash
apt install -y python3-venv python3-pip python3-dev \
    postgresql postgresql-contrib redis-server nginx \
    certbot python3-certbot-dns-cloudflare git build-essential libpq-dev ufw \
    fluidsynth ffmpeg poppler-utils
```

### Étape 4 : Configurer le firewall

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

### Étape 5 : Créer l'utilisateur

```bash
adduser --disabled-password --gecos "" cantateo
```

### Étape 6 : Configurer PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE USER cantateo WITH PASSWORD 'MOT_DE_PASSE_SECURISE';
CREATE DATABASE cantateo OWNER cantateo;
GRANT ALL PRIVILEGES ON DATABASE cantateo TO cantateo;
\q
```

### Étape 7 : Créer les répertoires

```bash
mkdir -p /var/www/cantateo /var/log/cantateo /var/backups/cantateo
chown cantateo:cantateo /var/www/cantateo /var/log/cantateo /var/backups/cantateo
```

### Étape 8 : Configurer SSH pour GitHub

```bash
# Générer une clé SSH
ssh-keygen -t ed25519 -C "cantateo-hetzner"

# Afficher la clé publique
cat ~/.ssh/id_ed25519.pub
```

Ajouter cette clé dans GitHub → Settings → SSH Keys.

```bash
# Tester la connexion
ssh -T git@github.com
```

### Étape 9 : Cloner le projet

```bash
cd /var/www/cantateo
git clone git@github.com:xavierxav/cantateo.git .
chown -R cantateo:cantateo /var/www/cantateo
```

### Étape 10 : Environnement Python

```bash
su - cantateo
cd /var/www/cantateo
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt -c requirements-lock.txt
exit
```

### Étape 11 : Fichier .env

Créer `/var/www/cantateo/.env` :

```env
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<générer avec python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())">
ALLOWED_HOSTS=www.cantateo.fr
CSRF_TRUSTED_ORIGINS=https://www.cantateo.fr

DATABASE_URL=postgresql://cantateo:MOT_DE_PASSE@localhost:5432/cantateo
REDIS_URL=redis://localhost:6379/0

CLOUDFLARE_R2_BUCKET_NAME=psalms-media
CLOUDFLARE_R2_ACCESS_KEY_ID=<ta_clé>
CLOUDFLARE_R2_SECRET_ACCESS_KEY=<ton_secret>
CLOUDFLARE_R2_ENDPOINT_URL=<ton_endpoint>
CLOUDFLARE_R2_CUSTOM_DOMAIN=<ton_domaine_r2>

CONTACT_EMAIL=contact@cantateo.fr
TURNSTILE_SITE_KEY=<ta_cle_site>
TURNSTILE_SECRET_KEY=<ton_secret>
SENTRY_DSN=

# Audio generation (Upright Piano KW - CC0 license)
SOUNDFONT_PATH=/var/www/cantateo/soundfonts/UprightPianoKW-20220221.sf2

# OMR generation (PDF -> MusicXML)
OMR_BACKEND=homr_cli
OMR_MODEL_PROFILE=default
HOMR_COMMAND=/opt/omr/homr/.venv/bin/homr
OMR_MAX_PAGES=1
OMR_TASK_TIMEOUT_SECONDS=600
OMR_MAX_ATTEMPTS=2
OMR_RETRY_DELAY_SECONDS=3600
```

### Étape 12 : Installer le SoundFont Piano

Le SoundFont Upright Piano KW (CC0 license, ~55MB) est utilisé pour générer l'audio des voix à partir des fichiers MXL.

```bash
# Créer le répertoire soundfonts
mkdir -p /var/www/cantateo/soundfonts
cd /var/www/cantateo/soundfonts

# Télécharger Upright Piano KW (environ 55 MB)
wget https://freepats.zenvoid.org/Piano/UprightPianoKW/UprightPianoKW-SF2-20220221.tar.xz

# Extraire
tar -xf UprightPianoKW-SF2-20220221.tar.xz

# Déplacer le fichier SF2
mv UprightPianoKW-SF2-20220221/UprightPianoKW-20220221.sf2 .

# Nettoyer
rm -rf UprightPianoKW-SF2-20220221 UprightPianoKW-SF2-20220221.tar.xz

# Corriger les permissions
chown -R cantateo:cantateo /var/www/cantateo/soundfonts

Environment variable in `.env`:
  - `SOUNDFONT_PATH`: Full path to the SoundFont file
```

### Étape 12b : Installer homr pour l'OMR

homr est installé hors du venv Django pour isoler `onnxruntime`, `opencv` et les poids du modèle.

```bash
mkdir -p /opt/omr
git clone https://github.com/liebharc/homr /opt/omr/homr
cd /opt/omr/homr
python3.11 -m venv .venv
.venv/bin/pip install poetry
.venv/bin/poetry install --only main
.venv/bin/poetry run homr --init
chown -R cantateo:cantateo /opt/omr
```

Le worker OMR utilise la file Celery `omr` et doit rester à `--concurrency=1` sur le VPS actuel.

### Étape 13 : Migrations et static

```bash
su - cantateo
cd /var/www/cantateo
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --no-input
exit
```

### Étape 14 : Services systemd

Créer `/etc/systemd/system/cantateo.service` :

```ini
[Unit]
Description=Cantateo Django Application
After=network.target postgresql.service redis.service

[Service]
User=cantateo
Group=cantateo
WorkingDirectory=/var/www/cantateo
Environment="PATH=/var/www/cantateo/venv/bin"
EnvironmentFile=/var/www/cantateo/.env
ExecStart=/var/www/cantateo/venv/bin/gunicorn \
    --workers 3 \
    --bind unix:/var/www/cantateo/cantateo.sock \
    --access-logfile /var/log/cantateo/access.log \
    --error-logfile /var/log/cantateo/error.log \
    psalm_project.wsgi:application

Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Créer `/etc/systemd/system/cantateo-worker.service` :

```ini
[Unit]
Description=Cantateo Celery Worker
After=network.target postgresql.service redis.service cantateo.service
Requires=redis.service

[Service]
User=cantateo
Group=cantateo
WorkingDirectory=/var/www/cantateo
Environment="PATH=/var/www/cantateo/venv/bin"
EnvironmentFile=/var/www/cantateo/.env
ExecStart=/var/www/cantateo/venv/bin/celery \
    -A psalm_project worker \
    --loglevel=info \
    --queues=audio \
    --concurrency=1 \
    --prefetch-multiplier=1 \
    --hostname=audio@%H

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable cantateo
systemctl enable cantateo-worker
systemctl enable cantateo-omr-worker
systemctl start cantateo
systemctl start cantateo-worker
systemctl start cantateo-omr-worker
```

### Étape 15 : Configuration Nginx

Créer `/etc/nginx/sites-available/cantateo` :

```nginx
server {
    listen 80;
    server_name cantateo.fr;
    return 301 https://www.cantateo.fr$request_uri;
}

server {
    listen 80;
    server_name www.cantateo.fr;

    location / {
        proxy_pass http://unix:/var/www/cantateo/cantateo.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/cantateo /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

### Étape 16 : DNS

Chez ton registrar (Wix), ajouter un enregistrement A :
- Nom : `@` et `www`
- Valeur : `5.75.146.72`

### Étape 17 : SSL

Une fois le DNS propagé, obtenir le certificat via DNS-01 (plugin Cloudflare) :

```bash
certbot certonly --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
    -d cantateo.fr -d www.cantateo.fr
```

`dev.cantateo.fr` est abandonné (NXDOMAIN) et retiré du certificat. Les certificats
`beta.cantateo.fr` et `cancionero.cantateo.fr` s'obtiennent de la même façon (DNS-01)
avec leurs domaines respectifs. La config `/etc/letsencrypt/renewal/<cert>.conf`
contient `dns_cloudflare_propagation_seconds = 30`.

### Étape 18 : Importer les données

Depuis WSL :

```bash
cd /home/xavier/Psalms
source venv/bin/activate
python manage.py dumpdata --exclude contenttypes --exclude auth.permission -o data_backup.json
scp data_backup.json root@5.75.146.72:/var/www/cantateo/
```

Sur Hetzner :

```bash
su - cantateo
cd /var/www/cantateo
source venv/bin/activate
python manage.py loaddata data_backup.json
```

---

## Dépannage

### Sauvegardes

Le script `deploy/backup.sh` vérifie l'archive avec `gzip -t` après `pg_dump`.
Pour une copie hors serveur, définir `BACKUP_REMOTE_TARGET` vers une destination
`rsync` accessible par l'utilisateur qui lance la tâche cron.

### Erreur 502 Bad Gateway

```bash
# Vérifier que Gunicorn tourne
systemctl status cantateo

# Vérifier le socket
ls -la /var/www/cantateo/cantateo.sock

# Voir les logs
journalctl -u cantateo -n 50
cat /var/log/cantateo/error.log
```

### Le service ne démarre pas

```bash
# Voir les erreurs détaillées
journalctl -u cantateo -n 100 --no-pager
```

### Problèmes de permissions

```bash
chown -R cantateo:cantateo /var/www/cantateo
chown -R cantateo:cantateo /var/log/cantateo
```

### Réinitialiser le mot de passe PostgreSQL

```bash
sudo -u postgres psql
ALTER USER cantateo WITH PASSWORD 'nouveau_mot_de_passe';
\q
```

---

## Domaine canonique et ancien sous-domaine dev

Le domaine canonique est `www.cantateo.fr`. Le domaine racine redirige vers ce
domaine canonique. L'ancien sous-domaine de développement `dev.cantateo.fr` a été
**supprimé** : il n'a plus d'enregistrement DNS (NXDOMAIN), ses vhosts nginx ont
été retirés et il a été enlevé du certificat SSL. Il bloquait le renouvellement SSL
du domaine principal (le certificat `cantateo.fr` qui l'incluait ne pouvait plus se
renouveler, d'où une erreur Cloudflare 526). Ne pas le recréer.

1. Garder le DNS `@` et `www` pointé vers `5.75.146.72`
2. Garder `.env` : `ALLOWED_HOSTS=www.cantateo.fr`
3. Garder `.env` : `CSRF_TRUSTED_ORIGINS=https://www.cantateo.fr`
4. Garder Nginx : `cantateo.fr` → `https://www.cantateo.fr$request_uri`
5. Obtenir le certificat SSL :
   ```bash
   certbot certonly --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
       -d cantateo.fr -d www.cantateo.fr
   ```
6. Redémarrer : `systemctl restart cantateo && systemctl reload nginx`
