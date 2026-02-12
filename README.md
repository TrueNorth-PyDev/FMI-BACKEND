# PrivCap Hub Backend

A secure, production-ready Django REST Framework backend for **PrivCap Hub**, a private portfolio application for investors to monitor their investments, manage ownership transfers, and explore marketplace opportunities.

![Dashboard Preview](file:///C:/Users/HP/.gemini/antigravity/brain/f1d70b52-3e97-41df-a7c4-4fb31359e010/api_docs_redoc_1768416652193.png)

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
- **Dual IRR Metrics**: Track both target IRR (from opportunity) and calculated IRR (from capital activities)
- **Analytics Dashboard**: Real-time performance metrics, sector allocation, and risk analysis
- **Capital Activities**: Track contributions, distributions, and valuations
- **Document Management**: Secure storage for investment documents

### 🔄 Ownership Transfers
- **Digital Workflow**: End-to-end management of ownership transfers
- **Status Tracking**: Draft → Pending → Approved → Completed
- **Fee Calculation**: Automated 2.5% transfer fee processing
- **Document Generation**: Automated transfer paperwork

### 🏪 Marketplace
- **Opportunity Discovery**: Browse and search investment opportunities
- **Watchlist**: Track interesting deals
- **Due Diligence**: Access virtual data rooms and documents
- **Investment Interest**: Express interest and contact sponsors

### 👥 Investor Network
- **Directory**: Connect with other accredited investors
- **Profiles**: customizable investor profiles with privacy controls
- **Connections**: Send/accept connection requests
- **Messaging**: Secure internal communication system

## 🛠 Tech Stack

- **Backend**: Django 4.2, Django REST Framework
- **Database**: PostgreSQL (Production), SQLite (Development)
- **Authentication**: SimpleJWT
- **Documentation**: drf-spectacular (ReDoc, Swagger UI)
- **Utilities**: django-environ, django-cors-headers, Pillow
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

## 🔧 Management Commands

### Daily IRR Accrual

Automatically grow investment values based on opportunity target IRR using compound interest.

**Dry-Run (Test Without Changes):**
```bash
python manage.py accrue_daily_irr --dry-run
```

**Live Accrual:**
```bash
python manage.py accrue_daily_irr
```

**Scheduling (Recommended: Daily at 00:00 UTC):**

**Windows Task Scheduler:**
```powershell
schtasks /create /tn "Django IRR Accrual" /tr "python C:\path\to\manage.py accrue_daily_irr" /sc daily /st 00:00
```

**Linux/Unix Cron:**
```bash
# Edit crontab
crontab -e

# Add line for daily execution at midnight UTC
0 0 * * * cd /path/to/project && python manage.py accrue_daily_irr
```

**Features:**
- ✅ Grows `current_value` daily using compound interest formula
- ✅ Keeps `total_invested` fixed (original investment amount)
- ✅ Creates performance snapshots for tracking
- ✅ Only processes active investments with linked opportunities
- ✅ Comprehensive error handling and logging

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
