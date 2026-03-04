# PrivCap Hub - API Reference

This document serves as a comprehensive reference for the PrivCap Hub Backend API (v1.1.0).

> **Interactive Documentation**: For testing and interactive exploration, please use the live [ReDoc](/api/docs/) or [Swagger UI](/api/swagger/) endpoints.

## 🔐 Authentication

All API requests (except login/registration) require a valid JWT Access Token.

**Header Format**:
```http
Authorization: Bearer <access_token>
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/accounts/register/` | Register new user account |
| POST | `/api/accounts/verify-email/` | Verify email with OTP |
| POST | `/api/accounts/login/` | Obtain access & refresh tokens |
| POST | `/api/accounts/token/refresh/` | Get new access token |

---

## 👥 Accounts Management

### Profile
**Base URL**: `/api/accounts/account/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `profile/` | Get current user profile |
| PATCH | `profile/` | Update profile information |
| POST | `upload_photo/` | Upload profile picture |
| POST | `change_password/` | Change account password |

---

## 💰 Portfolio Management

### Investments
**Base URL**: `/api/investments/investments/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List all investments |
| POST | `/` | Create new investment (can link to opportunity) |
| GET | `/{id}/` | Get detailed investment view |
| PATCH | `/{id}/` | Update investment details |
| GET | `/{id}/performance_history/` | Get performance history (days param) |

**Features:**
- ✨ **Opportunity Integration**: Investments can be linked to marketplace opportunities
- 📊 **Derived Fields**: `name`, `sector`, and `target_irr` derive automatically from the linked opportunity
- 🔄 **Daily IRR Accrual**: Values grow daily based on target IRR (runs once/day — idempotent across Railway deployments)

### Capital Activities
**Base URL**: `/api/investments/capital-activities/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List activities |
| POST | `/` | Record new capital activity |
| GET | `/?investment={id}` | Filter by investment |
| GET | `/?activity_type={type}` | Filter by type |

**Activity Types**:
| Type | Direction | Description |
|------|-----------|-------------|
| `INITIAL_INVESTMENT` | Negative (outflow) | First capital deployed |
| `CAPITAL_CALL` | Negative (outflow) | Follow-on capital call |
| `DISTRIBUTION` | Positive (inflow) | Return of capital/profits |
| `PARTIAL_EXIT` | Positive (inflow) | Partial secondary market sale |
| `FULL_EXIT` | Positive (inflow) | Complete buyout — entire position sold |

---

## 📊 Analytics Dashboard

**Base URL**: `/api/investments/analytics/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `overview/` | Key metrics & sector performance |
| GET | `performance_analysis/` | Quarterly returns & risk ratios |
| GET | `asset_allocation/` | Current vs Target allocation |
| GET | `risk_metrics/` | Volatility, stress tests, concentration |

---

## 🔧 Management Commands

### Daily IRR Accrual
Automatic daily growth of investment values based on opportunity target IRR.
- **Command**: `python manage.py accrue_daily_irr`
- **Schedule**: Daily at 00:00 UTC via `django-rq`
- **Idempotency**: Skips if already run today. Override:
  ```bash
  python manage.py accrue_daily_irr --force
  ```
- **Guard note**: `run_worker.sh` calls `setup_periodic_tasks` on every Railway deploy (fires the task immediately). The guard prevents double-accrual.

### Opportunity Status Transitions
- **Command**: `python manage.py transition_opportunities`
- **Behavior**: Transitions `NEW` → `ACTIVE` after 24 hours
- **Schedule**: Every 6 hours via `django-rq`

---

## 🔄 Ownership Transfers
**Base URL**: `/api/investments/transfers/`

### Workflow
1. **Create Draft**: POST `/`
2. **Submit**: POST `/{id}/submit/`
3. **Review**: Admin sets Pending → Approved
4. **Complete**: Admin finalises (status: Completed) — triggers signal to deduct from seller and credit buyer

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List transfers (filter by `status`, `direction`) |
| POST | `/` | Initiate new transfer |
| GET | `/{id}/` | Transfer details |
| DELETE | `/{id}/` | Cancel transfer (DRAFT/PENDING only) |
| POST | `/{id}/submit/` | Submit draft for review |
| POST | `/{id}/approve/` | *(Admin)* Approve pending transfer |
| POST | `/{id}/complete/` | *(Admin)* Complete approved transfer |

**Transfer Fee**: Currently **0%** (waived). `transfer_fee` is always `0.00` and `net_amount` equals `transfer_amount`.

---

## 🏪 Marketplace (Primary)
**Base URL**: `/api/marketplace/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `opportunities/` | Search/filter opportunities |
| GET | `opportunities/{id}/` | Detailed opportunity view |
| POST | `opportunities/{id}/request_information/` | Request deal access |
| POST | `watchlist/add/` | Add to watchlist |
| DELETE | `watchlist/remove/` | Remove from watchlist |

### Investor Interest
**Base URL**: `/api/marketplace/investor-interests/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List your interests |
| POST | `/` | Express interest in an opportunity |
| PATCH | `/{id}/` | Update interest (`status: CONVERTED` triggers auto-conversion) |

**Auto-conversion (PENDING → CONVERTED)**:
When an `InvestorInterest` status is set to `CONVERTED`, the system automatically:
1. Creates an `Investment` for the user (or tops up an existing one)
2. Logs an `INITIAL_INVESTMENT` `CapitalActivity`
3. Increments `MarketplaceOpportunity.current_raised_amount`

### Automatic Status Transitions
- **`NEW` → `ACTIVE`**: After 24 hours
- **`ACTIVE` → `CLOSING_SOON`**: At 90% funding
- **`CLOSING_SOON` → `CLOSED`**: At 100% funding

### Detailed Opportunity Metrics
Available in `/api/marketplace/opportunities/{id}/`:
- **Cash Flow**: `monthly_revenue`, `operating_expenses`, `net_cash_flow`, `cash_runway`
- **Team**: `total_staff_count`, `staff_departments`, `leadership_experience_years`
- **Operations**: `current_capacity`, `utilization_rate_pct`, `growth_capacity`

---

## 🔁 Secondary Marketplace
**Base URL**: `/api/investments/secondary-market/`

Read-only listing of all `PENDING` ownership transfers available for purchase.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Browse all available listings |
| GET | `/{id}/` | Listing detail |
| POST | `/{id}/express_interest/` | Register buyer interest (see below) |

**Filters**: `sector`, `transfer_type` (`FULL`/`PARTIAL`), `min_amount`, `max_amount`

### Buyer Interest — Two-Step Flow

#### Step 1 — Express Interest
```http
POST /api/investments/secondary-market/{transfer_id}/express_interest/
```
Optional body: `{ "amount": 15000.00 }` (defaults to the full listing amount)

**Effect**: Creates a `SecondaryMarketInterest` record with status `PENDING`. **No financial changes occur yet.**

**Response**:
```json
{
  "message": "Interest registered successfully.",
  "interest_id": 7,
  "created": true,
  "transfer_id": 3,
  "amount": "15000.00",
  "status": "PENDING",
  "note": "Update the interest status to CONVERTED to execute the transfer."
}
```

#### Step 2 — Convert (Execute Transfer)
**Base URL**: `/api/investments/secondary-market-interests/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List your buyer interests |
| GET | `/{id}/` | Interest detail |
| PATCH | `/{id}/` | Update status |

```http
PATCH /api/investments/secondary-market-interests/{id}/
{ "status": "CONVERTED" }
```

**What happens atomically**:
1. **Seller's Investment deducted** by the interest `amount`
   - `PARTIAL_EXIT` capital activity if seller retains a remaining balance
   - `FULL_EXIT` capital activity if seller's entire position is wiped out (investment marked `EXITED`)
2. **Buyer's Investment created** (or topped-up) for the same amount, with an `INITIAL_INVESTMENT` capital activity
3. **OwnershipTransfer** marked `COMPLETED` and `is_processed = True`
4. **`current_raised_amount` is NOT modified** — no new capital enters the opportunity; only existing ownership moves between investors

To **cancel** an interest: `PATCH /{id}/` `{ "status": "CANCELLED" }`

---

## 🌐 Investor Network
**Base URL**: `/api/accounts/network/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `directory/` | Search investor directory |
| GET | `profile/{id}/` | View investor profile |
| POST | `connect/` | Send connection request |
| GET | `connections/` | List connections |
| PATCH | `my_profile/` | Manage network visibility |

---

## ⚠️ Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 400 | `validation_error` | Invalid input data |
| 401 | `authentication_failed` | Invalid or expired token |
| 403 | `permission_denied` | Insufficient rights (e.g. seller trying to buy own listing) |
| 404 | `not_found` | Resource does not exist |
| 429 | `throttled` | Request limit exceeded |

## 📦 Data Types

**Currency**: Primary values in **USD**. Localized metrics (e.g., Monthly Revenue) may use **NGN**.  
**Dates**: ISO 8601 format (`YYYY-MM-DD`).  
**Timestamps**: ISO 8601 with timezone (`YYYY-MM-DDThh:mm:ssZ`).  
**Decimal amounts**: Precision to 2 decimal places.
