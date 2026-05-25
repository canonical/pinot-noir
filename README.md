# Pinot Noir

## Production setup

### 1. Set environment variables

Create a `.env` file in the project root (never commit this file):

```bash
DJANGO_SETTINGS_MODULE=pinot_noir.settings.production
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=pinotnoirdomain.com
CSRF_TRUSTED_ORIGINS=https://pinotnoirdomain.com
DB_NAME=pinot_noir
DB_USER=pinot_noir_user
DB_PASSWORD=your-db-password
# Optional — defaults to localhost:5432
# DB_HOST=your-db-host
# DB_PORT=5432
```

Generate a secret key with:

```bash
uv run python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'
```

Then load the variables into your shell before running any commands:

```bash
set -a; source .env; set +a
```

### 2. Apply migrations and collect static files

```bash
uv run manage.py migrate
uv run manage.py collectstatic
```

### 3. Create an admin user

```bash
uv run manage.py createsuperuser
```

### 4. Run the application

```bash
uv run manage.py runserver
```