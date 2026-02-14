# PrivCap Hub - API Reference

This document serves as a comprehensive reference for the PrivCap Hub Backend API (v1.0.0).

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

**New Features:**
- ✨ **Opportunity Integration**: Investments can now be linked to marketplace opportunities.
- 📊 **Derived Fields**: Investment `name`, `sector`, and `target_irr` automatically derive from linked opportunity.
- 🔄 **Daily IRR Accrual**: Investment values automatically grow based on opportunity target IRR.

### Capital Activities
**Base URL**: `/api/investments/capital-activities/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List activities (calls, distributions) |
| POST | `/` | Record new capital activity |
| GET | `/?investment={id}` | Filter by investment |
| GET | `/?activity_type={type}` | Filter by activity type |

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

#### Daily IRR Accrual
Automatic daily growth of investment values based on opportunity target IRR.
- **Command**: `python manage.py accrue_daily_irr`
- **Schedule**: Recommended daily at 00:00 UTC.

#### Opportunity Status Transitions
Automatic lifecycle management for marketplace opportunities.
- **Command**: `python manage.py transition_opportunities`
- **Behavior**: Transitions `NEW` opportunities to `ACTIVE` after 24 hours.
- **Schedule**: Recommended every 6 hours (`0 */6 * * *`).

---

## 🔄 Ownership Transfers
**Base URL**: `/api/investments/transfers/`

### Workflow
1. **Create Draft**: POST `/`
2. **Submit**: POST `/{id}/submit/`
3. **Review**: Managed by admin (Status: Pending → Approved)
4. **Complete**: Finalized by admin (Status: Completed)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List transfers (filter by status) |
| POST | `/` | Initiate new transfer |
| GET | `/{id}/` | Get transfer details |
| DELETE | `/{id}/` | Cancel/Delete transfer |

---

## 🏪 Marketplace
**Base URL**: `/api/marketplace/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `opportunities/` | Search/Filter opportunities |
| GET | `opportunities/{id}/` | Detailed opportunity view |
| POST | `opportunities/{id}/request_information/` | Request deal access |
| POST | `watchlist/add/` | Add to watchlist |
| DELETE | `watchlist/remove/` | Remove from watchlist |

### 🛡️ Investment Safeguards
- **Over-investment Protection**: System prevents any investment that would exceed the `target_raise_amount`.
- **Validation Message**: `Total investment exceeds the target amount. Please buy less as your amount is greater than the target raised amount.`

### 📈 Automatic Status Transitions
- **`NEW` ➔ `ACTIVE`**: Triggered after 24 hours via `transition_opportunities` command.
- **`ACTIVE` ➔ `CLOSING_SOON`**: Automatically triggered when funding reaches **90%**.
- **`CLOSING_SOON` ➔ `CLOSED`**: Automatically triggered when funding reaches **100%**.

### 📊 Detailed Opportunity Metrics
The Detail API (`/api/marketplace/opportunities/{id}/`) now includes:
- **Cash Flow**: `monthly_revenue`, `operating_expenses`, `net_cash_flow`, `cash_runway`.
- **Team**: `total_staff_count`, `staff_departments`, `leadership_experience_years`.
- **Operations**: `current_capacity`, `utilization_rate_pct`, `growth_capacity`.

---

## 🌐 Investor Network
**Base URL**: `/api/accounts/network/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `directory/` | Search investor directory |
| GET | `profile/{id}/` | View another investor's profile |
| POST | `connect/` | Send connection request |
| GET | `connections/` | List my connections |
| PATCH | `my_profile/` | Manage your network visibility |

---

## ⚠️ Error Codes

| Status | Code | Description |
|--------|------|-------------|
| 400 | `validation_error` | Invalid input data (e.g., over-investment) |
| 401 | `authentication_failed` | Invalid or expired token |
| 403 | `permission_denied` | Insufficient rights |
| 404 | `not_found` | Resource does not exist |
| 429 | `throttled` | Request limit exceeded |

## 📦 Data Types

**Currency**: Primary values in **USD**. Localized metrics (e.g., Monthly Revenue) may use **NGN**.  
**Dates**: ISO 8601 format (`YYYY-MM-DD`).  
**Timestamps**: ISO 8601 with timezone (`YYYY-MM-DDThh:mm:ssZ`).
