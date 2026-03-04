# PrivCap Hub Backend

A secure, production-ready Django REST Framework backend for **PrivCap Hub**, a private portfolio application for investors to monitor their investments, manage ownership transfers, and explore marketplace opportunities.

## 🚀 Key Features

### 🔐 Authentication & Security
- **JWT Authentication** with access (15m) and refresh (7d) tokens
- **Email Verification** using 6-digit OTP
- **Account Lockout** protection (5 failed attempts, 30m lockout)
- **Password Policies** enforcement
- **Comprehensive Logging** of security events

### 📊 Portfolio Management
- **Investment Tracking**: Monitor private equity, VC, and real estate investments
- **Opportunity Integration**: Link investments to marketplace opportunities for automatic data synchronization
- **Daily IRR Accrual**: Automatic daily growth of investment values based on target IRR (compound interest)
  - **Idempotency Guard**: Runs at most once per calendar day — safe across multiple Railway deploys. Use `--force` to override manually.
- **Dual IRR Metrics**: Track both target IRR (from opportunity) and calculated IRR (from capital activities)
- **Analytics Dashboard**: Real-time performance metrics, sector allocation, and risk analysis
- **Capital Activities**: Track contributions, distributions, partial exits, and full exits
  - Types: `INITIAL_INVESTMENT`, `CAPITAL_CALL`, `DISTRIBUTION`, `PARTIAL_EXIT`, `FULL_EXIT`
- **Document Management**: Secure storage for investment documents

### 🔄 Ownership Transfers
- **Digital Workflow**: End-to-end management of ownership transfers
- **Status Tracking**: Draft → Pending → Approved → Completed
- **Fee Calculation**: Transfer fee is currently **0%** (waived — configurable in `OwnershipTransfer.save()`)
- **Document Generation**: Automated transfer paperwork

### 🏪 Marketplace
- **Opportunity Discovery**: Browse and search with detailed metrics (Cash Flow, Team, Capacity)
- **Watchlist**: Track interesting deals
- **Due Diligence**: Access virtual data rooms and secure documents
- **Investor Interest**: Express interest in opportunities; auto-converts to `Investment` when status is set to `CONVERTED`
- **Automated Lifecycle**:
    - `NEW` ➔ `ACTIVE` after 24 hours
    - `ACTIVE` ➔ `CLOSING_SOON` at 90% funding
    - `CLOSING_SOON` ➔ `CLOSED` at 100% funding
- **Investment Safeguards**: Automatic prevention of over-funding beyond target

### 🔁 Secondary Marketplace
- **Browse Listings**: View all `PENDING` ownership transfers listed by other investors
- **Buyer Interest (Two-Step Flow)**:
  1. `POST /{id}/express_interest/` → creates a `SecondaryMarketInterest` record (`PENDING`). No money moves.
  2. `PATCH /secondary-market-interests/{id}/` `{ "status": "CONVERTED" }` → atomically executes the transfer:
     - Deducts amount from seller's investment (`PARTIAL_EXIT` or `FULL_EXIT` capital activity)
     - Creates / tops-up buyer's investment with an `INITIAL_INVESTMENT` capital activity
     - Marks the `OwnershipTransfer` as `COMPLETED`
- **Full Exit Detection**: Logs a `FULL_EXIT` activity (instead of `PARTIAL_EXIT`) when a buyout wipes the seller's entire position
- **Raised-Amount Integrity**: Secondary market transfers do **not** modify `MarketplaceOpportunity.current_raised_amount` — no new capital enters the opportunity; only existing ownership changes hands

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
- **Idempotency**: Skips automatically if already executed today. Override with `--force`:
  ```bash
  python manage.py accrue_daily_irr --force
  ```

### Opportunity Status Transitions
Transitions opportunities from `NEW` to `ACTIVE` after 24 hours.
- **Task**: `marketplace.tasks.run_transition_opportunities`
- **Schedule**: Every 6 hours (Managed by `django-rq`).

### Railway Worker (Production)
In Railway, use the **Worker Service** running `sh run_worker.sh`. This process handles:
1.  **Scheduler**: Triggers the tasks at the right time.
2.  **Worker**: Executes the tasks in the background.

> ⚠️ `run_worker.sh` calls `setup_periodic_tasks` on every deploy, which schedules the IRR accrual for immediate execution. The built-in idempotency guard prevents double-accrual on days with multiple deployments.

To initialize the schedule, run this command once:
```bash
python manage.py setup_periodic_tasks
```

## 🧪 Testing

Run the test suite to ensure system stability:

```bash
python manage.py test
```

## 🚀 Production Deployment

1. **Environment Variables**:
   Set `DEBUG=False` and use a strong `SECRET_KEY`.
   Configure `DATABASE_URL` for PostgreSQL.

2. **Security Settings**:
   The application is configured for production security (SSL, HSTS, secure cookies) when `DEBUG=False`.

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
