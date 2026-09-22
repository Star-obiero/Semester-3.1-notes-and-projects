# Safari Tent Makers & Fabricators — website + backend

Flask + SQLite. Customers register and log in to place orders (payment on delivery).
The owner manages everything from **/admin**.

## What it does
- **Customers:** register / log in, place orders, see order history and status, get a personal referral code, change password.
- **Orders are saved** in the database (customer, items, sizes, delivery location, status, referrer).
- **Admin (/admin):** orders and status, customers, contact messages, job applications,
  referral report + "commission paid" tick, post **New products**, upload **Gallery** photos,
  download all orders as CSV, reset a customer's password.
- **Public pages:** Home, Products (11 categories), Gallery, New Products, Blog, Jobs & Earn, Contact, Privacy.

## Run it on your computer
```bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# create the admin login (used once at start-up; pick your own!)
export ADMIN_EMAIL="you@yourcompany.co.ke"
export ADMIN_PASSWORD="a-long-password-here"
# Windows (PowerShell): $env:ADMIN_EMAIL="..." ; $env:ADMIN_PASSWORD="..."

python app.py                     # open http://127.0.0.1:5000  → log in → /admin
```

## Settings (environment variables)
| Variable | Purpose |
|---|---|
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Creates / promotes the admin account at start-up (password 8+ chars) |
| `SECRET_KEY` | Long random string for sessions (set this in production) |
| `HTTPS=1` | Set once the site is served over https (secure cookies) |
| `DATA_DIR` | Where the database + uploaded photos live (default `./data`) — **back this folder up** |
| `SITE_NAME`, `SITE_SHORT`, `SITE_PHONE`, `SITE_WHATSAPP` (digits, e.g. 2547…), `SITE_EMAIL`, `SITE_ADDRESS`, `SITE_HOURS`, `SITE_COMMISSION` | Company details shown on the site |
| `SEED_SAMPLES=0` | Don't add the 4 sample "new products" on first run |

## Put it online
Any host that runs Python works. Two easy options:
- **PythonAnywhere** (simple, keeps files between restarts): upload the folder, create a Flask web app
  pointing at `app.py`, set the environment variables, enable HTTPS, reload.
- **Render / Railway / a VPS:** run `gunicorn app:app` (see `Procfile`). Attach a **persistent disk** and
  point `DATA_DIR` at it — otherwise the database is wiped on every deploy.

## Editing content
- Products, blog posts and jobs: `catalog.json` (plain text lists — add or change entries, restart).
- New products and gallery photos: from **/admin/media** (no code).
- Look and feel: `static/style.css`. Templates: `templates/`.

## Before launch
- Have the privacy notice (`templates/privacy.html`) reviewed. Because you store customers' personal
  data, check your obligations under Kenya's Data Protection Act (including registration with the ODPC).
- Change the placeholder phone / email / address.
- Set up a regular backup of `DATA_DIR`.
- Lost passwords: Admin → Customers → **Reset password** gives a temporary one to pass on.

## Not built yet (good next steps)
Email/WhatsApp alerts for new orders, self-service password reset by email, M-Pesa payments,
quotes/prices per product, editing blog posts and jobs from the admin.
