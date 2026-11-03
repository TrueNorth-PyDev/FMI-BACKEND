# PrivCap Hub Backend

A secure, production-ready Django REST Framework backend for **PrivCap Hub**, a private portfolio application for investors to monitor their investments, manage ownership transfers, and explore marketplace opportunities.

## 🚀 Key Features

### 🔐 Authentication & Security
- **JWT Authentication** with access (15m) and refresh (7d) tokens
- **Email Verification** using 6-digit OTP
- **Account Lockout** protection (5 failed attempts, 15m lockout)
- **OTP brute-force protection** (5 wrong guesses invalidate a code) and rate limiting on auth endpoints
- **Revocable sessions**: revoking a session signs it out immediately (refresh token blacklisted, access tokens rejected); changing the password signs out other sessions
- **Least privilege for staff**: only superusers can grant staff rights or modify staff accounts
- **Password Policies** enforcement
- **Comprehensive Logging** of security events

### 📊 Portfolio Management
- **Investment Tracking**: Monitor private equity, VC, and real estate investments (read-only for investors; created by pledge conversion, transfers or staff)
- **Opportunity Integration**: Link investments to marketplace opportunities for automatic data synchronization
- **Daily IRR Accrual**: Automatic daily growth of investment values based on target IRR (compound interest)
  - **Idempotent with backfill**: each investment tracks `last_accrued_date`; a run accrues every missed day and nothing more — safe across multiple Railway deploys.
- **Dual IRR Metrics**: Track both target IRR (from opportunity) and calculated IRR (from capital activities)
- **Analytics Dashboard**: Real-time performance metrics, sector allocation, and risk analysis
- **Capital Activities**: Track contributions, distributions, partial exits, and full exits
  - Types: `INITIAL_INVESTMENT`, `CAPITAL_CALL`, `DISTRIBUTION`, `PARTIAL_EXIT`, `FULL_EXIT`
- **Document Management**: Secure storage for investment documents

### 🔄 Ownership Transfers
- **Digital Workflow**: End-to-end management of ownership transfers
- **Status Tracking**: Draft → Pending → Approved (staff) → Completed (staff)
- **Fee Calculation**: Transfer fee is currently **0%** (waived — configurable in `OwnershipTransfer.save()`)
- **Document Generation**: Automated transfer paperwork

### 🏪 Marketplace
- **Opportunity Discovery**: Browse and search with detailed metrics (Cash Flow, Team, Capacity)
- **Watchlist**: Track interesting deals
- **Due Diligence**: Access virtual data rooms and secure documents
- **Investor Interest**: Pledge to opportunities (min investment and remaining capacity enforced); staff convert a pledge into an `Investment`
- **Automated Lifecycle**:
    - `NEW` ➔ `ACTIVE` after 24 hours
    - `ACTIVE` ➔ `CLOSING_SOON` at 90% funding
    - `CLOSING_SOON` ➔ `CLOSED` at 100% funding
- **Investment Safeguards**: Automatic prevention of over-funding beyond target

### 🔁 Secondary Marketplace
- **Browse Listings**: View all `PENDING` ownership transfers listed by other investors
- **Buyer Interest (Two-Step Flow)**:
  1. `POST /api/secondary-market/{id}/express_interest/` → creates a `SecondaryMarketInterest` record (`PENDING`). No money moves.
  2. Staff `PATCH /api/admin/secondary-interests/{id}/` `{ "status": "CONVERTED" }` → atomically executes the transfer:
     - Deducts amount from seller's investment (`PARTIAL_EXIT` or `FULL_EXIT` capital activity; cost basis reduced proportionally)
     - Creates / tops-up buyer's investment with an `INITIAL_INVESTMENT` capital activity
     - Marks the `OwnershipTransfer` as `COMPLETED` and cancels competing interests
- **Direct transfers** (with a named `to_user`) are never listed publicly
- **Full Exit Detection**: Logs a `FULL_EXIT` activity (instead of `PARTIAL_EXIT`) when a buyout wipes the seller's entire position
- **Raised-Amount Integrity**: Secondary market transfers do **not** modify `MarketplaceOpportunity.current_raised_amount` — no new capital enters the opportunity; only existing ownership changes hands

### 🛠 Custom Admin API
- **Dedicated Admin Panel**: `/api/admin/` powers a custom front-end to rival Django's default admin.
- **RESTful Controls**: Staff-only endpoints to manage users, verify emails, suspend/unlock accounts, and terminate sessions.
- **Lifecycle Management**: Approve ownership transfers, publish marketplace opportunities, and record capital activities directly via API.
- **Analytics & Logs**: Platform-wide KPIs, user analytics, AUM trends, and an immutable security audit trail.

### 👥 Investor Network
- **Directory**: Connect with other accredited investors
- **Profiles**: Customizable investor profiles with privacy controls
- **Connections**: Send/accept connection requests
- **Messaging**: Secure internal communication system

## 🛠 Tech Stack

- **Backend**: Django 4.2, Django REST Framework
- **Database**: PostgreSQL (Production), SQLite (Development)
- **Authentication**: SimpleJWT
- **Automation**: Management commands + Railway Cron
- **Science**: NumPy, SciPy (for financial calculations)

## 📚 API Documentation

The backend includes comprehensive, interactive API documentation.

| Type | URL | Description |
|------|-----|-------------|
| **ReDoc** | `/api/docs/` | Beautiful, reference-style documentation (Recommended) |
| **Swagger UI** | `/api/swagger/` | Interactive testing tool |
| **OpenAPI Schema** | `/api/schema/` | Raw OpenAPI 3.0 specification |

> **Note**: For a detailed static reference, see [API_REFERENCE.md](API_REFERENCE.md).

## ⚡ Installation & Setup

### Prerequisites
- Python 3.8+
- pip
- Virtual environment tool

### Steps

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd privcap_hub
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   # Windows
   .\venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment**:
   Copy `.env.example` to `.env` (create one if missing):
   ```env
   DEBUG=True
   SECRET_KEY=your-secret-key-dev
   ALLOWED_HOSTS=localhost,127.0.0.1
   DATABASE_URL=sqlite:///db.sqlite3
   # Optional: REDIS_URL (RQ + shared throttling cache), MEDIA_ROOT, AUTH_THROTTLE_RATE,
   # NUM_PROXIES (trusted proxies in front of the app; default 1 in production), EMAIL_TIMEOUT
   ```

5. **Run Migrations**:
   ```bash
   python manage.py migrate
   ```

6. **Create Superuser**:
   ```bash
   python manage.py createsuperuser
   ```

7. **Run Server**:
   ```bash
   python manage.py runserver
   ```
   Access at: `http://localhost:8000/`

## 🔧 Management Commands (Background Tasks)

### Daily IRR Accrual
Automatically grow investment values based on opportunity target IRR using compound interest.
- **Task**: `investments.tasks.run_daily_irr_accrual`
- **Schedule**: Daily at midnight (Managed by `django-rq`).
- **Idempotency**: Each investment is accrued at most once per day; missed days are backfilled. Preview with:
  ```bash
  python manage.py accrue_daily_irr --dry-run
  ```

### Daily Clean-up
Flushes expired JWT tokens, old OTP codes and expired sessions.
- **Task**: `core.tasks.run_daily_cleanup`
- **Schedule**: Every 24 hours (Managed by `django-rq`).

### Opportunity Status Transitions
Transitions opportunities from `NEW` to `ACTIVE` after 24 hours.
- **Task**: `marketplace.tasks.run_transition_opportunities`
- **Schedule**: Every 6 hours (Managed by `django-rq`).

### Railway Worker (Production)
The Railway start command in `railway.toml` runs migrations, starts `run_worker.sh` in the background, then starts gunicorn. `run_worker.sh` handles:
1.  **Scheduler**: Triggers the tasks at the right time.
2.  **Worker**: Executes the tasks (kept in the foreground, so the script also works as a standalone worker process, e.g. the Procfile `worker`).

> ⚠️ `run_worker.sh` calls `setup_periodic_tasks` on every deploy, which schedules the IRR accrual for immediate execution. Accrual is idempotent per investment, so multiple deployments in a day never double-accrue. Run the worker in only one place (either the web start command or a separate worker service), not both.

To initialize the schedule, run this command once:
```bash
python manage.py setup_periodic_tasks
```

## 🧪 Testing

Run the test suite to ensure system stability:

```bash
python manage.py test accounts core marketplace admin_api investments
```

## 🚀 Production Deployment

1. **Environment Variables**:
   Set `DEBUG=False` and use a strong `SECRET_KEY`.
   Configure `DATABASE_URL` for PostgreSQL.

2. **Security Settings**:
   The application is configured for production security (HSTS, secure cookies, trusting the proxy's `X-Forwarded-Proto`) when `DEBUG=False`. `SECURE_SSL_REDIRECT` can be enabled safely; `/api/health/` is exempt so the platform health check keeps working.

3. **Web Server**:
   Use **Gunicorn** behind **Nginx**.
   ```bash
   gunicorn privcap_hub.wsgi:application
   ```

4. **Static Files**:
   ```bash
   python manage.py collectstatic
   ```

## 📂 Project Structure

```
privcap_hub/
├── accounts/           # User, Auth, Network, Profile management
├── core/               # Middleware, Exceptions, Shared utilities
├── investments/        # Portfolio, Analytics, Transfers
├── marketplace/        # Opportunities, Watchlist
├── media/              # User uploads (Profiles, Documents)
├── privcap_hub/        # Main configuration
└── templates/          # Email templates
```

## 📄 License

Proprietary - PrivCap Hub. All rights reserved.
