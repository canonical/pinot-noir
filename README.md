# Pinot Noir

## Production setup

### 1. Set environment variables

Create a `.env` file in the project root (never commit this file):

```bash
DJANGO_SETTINGS_MODULE=pinot_noir.settings.production
DJANGO_SECRET_KEY=your-secret-key
DJANGO_FIELD_ENCRYPTION_KEY_VALUE=your-encryption-key
DJANGO_ALLOWED_HOSTS='["pinotnoirdomain.com"]'
DJANGO_BASE_URL=https://pinotnoirdomain.com
POSTGRESQL_DB_NAME=pinot_noir
POSTGRESQL_DB_USERNAME=pinot_noir_user
POSTGRESQL_DB_PASSWORD=your-db-password
POSTGRESQL_DB_HOSTNAME=your-db-host
POSTGRESQL_DB_PORT=5432
```

Generate a secret key with:

```bash
uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Generate a field encryption key the same way (use a value distinct from
`DJANGO_SECRET_KEY`):

```bash
uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Then load the variables into your shell before running any commands:

```bash
set -a; source .env; set +a
```

### 2. Configure Google sign-in (optional)

In Google Cloud Console, create an OAuth 2.0 Web application client. Add the
public callback URL, including the trailing slash, to its authorized redirect
URIs:

```text
https://<Domain Name>/oidc/callback/
```

Add the generated credentials to `.env`:

```bash
GOOGLE_OAUTH_CLIENT_ID=your-google-client-id
GOOGLE_OAUTH_CLIENT_SECRET=your-google-client-secret
```

The Continue with Google button appears only when both values are configured.

### 3. Apply migrations and collect static files

```bash
uv run manage.py migrate
uv run manage.py collectstatic
```

### 4. Create an admin user

```bash
uv run manage.py createsuperuser
```

### 5. Run the application

```bash
uv run manage.py runserver
```
