# EventEye – Bulk Certificate Generator (Flask MVP)

## Quickstart

1. Create and activate a virtualenv
```bash
python -m venv .venv && .venv\\Scripts\\activate
```

2. Install dependencies
```bash
pip install -r requirements.txt
```

3. Configure environment
Copy `.env.example` to `.env` and fill values.

4. Run the app
```bash
python -m app.main
```

5. Initialize the database (first run)
Visit `http://127.0.0.1:5000/initdb` to create tables and a superadmin.

## Folders
- `app/templates/` – certificate templates and HTML templates
- `app/static/` – generated certificates
- `app/utils/` – helpers (DB, auth, cert gen, email)

## MVP Features
- Role-based access: superadmin, admin, club
- Upload CSV or manual add participants
- Certificate generation with QR codes (PNG)
- Bulk email sending with SMTP
- Simple dashboard: participants and delivery status
- Optional public verification `/verify?code=...`

## Notes
- Coordinates mapping is in `coordinates.json` (per template). See sample.
- Sample `participants.csv` provided.
