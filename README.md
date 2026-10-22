# TaskApp

## Email verification

New accounts must verify their email address before signing in. The app sends
verification mail through Gmail SMTP by default. Set these environment
variables in the repository-root `.env` file before starting the application:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-gmail-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM=your-gmail-address@gmail.com
APP_BASE_URL=http://127.0.0.1:8000
```

Use a Google App Password for `SMTP_PASSWORD`, not your regular Gmail password.
The `.env` file is excluded from Git; keep your App Password private. Set
`APP_BASE_URL` to the public base URL when deploying the app.

Apply the database migration from the `TaskApp` directory before starting the
app against an existing database:

```powershell
python -m alembic upgrade head
```

Existing accounts are considered verified by this migration; newly registered
accounts must verify using the emailed link, which expires after 24 hours.
