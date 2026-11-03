# PrivCap Hub - API Reference

This document serves as a comprehensive reference for the PrivCap Hub Backend API (v1.2.0).

> **Interactive Documentation**: For testing and interactive exploration, please use the live [ReDoc](/api/docs/) or [Swagger UI](/api/swagger/) endpoints.

## 🔐 Authentication

All API requests (except login/registration and the public marketplace listing) require a valid JWT Access Token.

**Header Format**:
```http
Authorization: Bearer <access_token>
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/accounts/register/` | Register new user account (sends a 6-digit email code) |
| POST | `/api/accounts/verify-email/` | Verify email with OTP — returns tokens |
| POST | `/api/accounts/resend-otp/` | Resend a code (`otp_type`: `EMAIL_VERIFICATION` / `PASSWORD_RESET`) |
| POST | `/api/accounts/login/` | Obtain access & refresh tokens |
| POST | `/api/accounts/token/refresh/` | Get a new access token (the refresh token is rotated) |
| POST | `/api/accounts/password-reset/request/` | Email a password reset code |
| POST | `/api/accounts/password-reset/verify/` | Check a reset code |
| POST | `/api/accounts/password-reset/confirm/` | Set a new password (signs out all sessions) |

**Security notes**
- Each code allows 5 wrong attempts before it is invalidated; request a new one with `resend-otp/`.
- `resend-otp/` and `password-reset/request/` respond identically whether or not the email is registered.
- These endpoints are rate limited (default `30/minute` per client IP, `AUTH_THROTTLE_RATE` env var) → `429`. Behind a proxy, set `NUM_PROXIES` (default `1` in production) so the real client IP is used.
- Each login creates a session; its tokens carry the session id (`sid` claim). Revoking a session blacklists its refresh token **and** rejects its access tokens immediately (`401`, code `session_revoked`).
- Changing your password signs out all your other sessions; resetting it signs out all sessions.

---

## 👥 Accounts Management

**Base URL**: `/api/accounts/account/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET / PATCH | `profile/` | Get / update current user profile |
| POST | `upload_photo/` | Upload profile picture (image files, max 5MB) |
| POST | `change_password/` | Change account password |
| GET | `sessions/` | List recent sessions (`is_current` marks the session making the request) |
| DELETE | `revoke_session/` | Revoke another session `{ "session_id": 3 }` (not the current one) |
| GET / PATCH | `notification_preferences/` | Notification settings |
| GET / POST | `documents/` | List / upload documents (max 20MB) |
| GET | `document_download/?id={id}` | Download a document (documents are **not** served from `/media/`) |
| DELETE | `delete_document/` | Delete a document `{ "id": 5 }` |
| GET | `activity/` | Last 50 account activities |

---

## 💰 Portfolio Management

### Investments (read-only)
**Base URL**: `/api/investments/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List your investments |
| GET | `/{id}/` | Detailed investment view (incl. capital activities and calculated IRR) |
| GET | `/{id}/performance_history/?days=365` | Daily value history (1–3650 days) |

Investments are **not** created or edited by investors. They come from:
- staff converting a marketplace pledge (`/api/admin/investor-interests/{id}/convert/`),
- a completed ownership transfer or secondary-market purchase,
- staff via `/api/admin/investments/`.

**Features:**
- 📊 **Derived Fields**: `name`, `sector`, and `target_irr` derive automatically from the linked opportunity
- 🔄 **Daily IRR Accrual**: Values grow daily based on the opportunity's target IRR (see Management Commands)

### Capital Activities (read-only)
**Base URL**: `/api/capital-activities/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List activities on your investments |
| GET | `/?investment={id}` | Filter by investment |
| GET | `/?activity_type={type}` | Filter by type |

Staff record activities with `POST /api/admin/investments/{id}/capital-activities/`; the sign is applied automatically.

**Activity Types**:
| Type | Direction | Description |
|------|-----------|-------------|
| `INITIAL_INVESTMENT` | Negative (outflow) | Capital deployed (pledge conversion or purchase) |
| `CAPITAL_CALL` | Negative (outflow) | Follow-on capital call |
| `DISTRIBUTION` | Positive (inflow) | Return of capital/profits |
| `PARTIAL_EXIT` | Positive (inflow) | Part of the position sold or transferred |
| `FULL_EXIT` | Positive (inflow) | Entire position sold or transferred |

---

## 📊 Analytics Dashboard

**Base URL**: `/api/portfolio/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `overview/` | Key metrics & sector performance |
| GET | `performance_analysis/` | Quarterly returns vs benchmark & risk ratios |
| GET | `asset_allocation/` | Current vs target allocation |
| GET | `risk_metrics/` | Volatility, stress tests, concentration |

Quarterly returns, max drawdown and volatility use a cash-flow-adjusted (time-weighted) daily index, so purchases, sales and exits are not counted as gains or losses. The benchmark is a fixed 10% annual return. Volatility is annualized.

`overview.key_metrics.distributions_received` is the cash received from distributions and exits. Realized gains are distributions plus exit proceeds minus the cost basis sold (each exit records its `cost_basis`).

---

## 🔄 Ownership Transfers
**Base URL**: `/api/transfers/`

### Workflow
1. **Create**: `POST /` with `status` `DRAFT` (default) or `PENDING` (submit straight away)
2. **Edit** (drafts only): `PATCH /{id}/`
3. **Submit**: `POST /{id}/submit/` (DRAFT → PENDING)
4. **Review** *(staff)*: `POST /api/admin/transfers/{id}/approve/` (PENDING → APPROVED) or `.../reject/`
5. **Complete** *(staff)*: `POST /api/admin/transfers/{id}/complete/` — moves the position to `to_user`

A transfer needs a registered recipient (`to_user`) to be completed; otherwise completion returns `400` and the transfer stays APPROVED. A `PENDING` transfer **without** `to_user` is a public listing on the secondary market.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List transfers (filter by `status`, `direction=outgoing|incoming`) |
| POST | `/` | Initiate new transfer |
| GET | `/{id}/` | Transfer details (incl. documents) |
| PATCH | `/{id}/` | Edit a draft (owner only) |
| DELETE | `/{id}/` | Cancel transfer (DRAFT/PENDING only) |
| POST | `/{id}/submit/` | Submit draft for review |
| GET | `/pending/` | Pending and approved transfers |
| GET | `/history/` | Completed, cancelled and rejected transfers |
| GET | `/{id}/documents/{doc_id}/download/` | Download a transfer document (sender/recipient) |

**Rules**: `transfer_amount` cannot exceed the investment's current value. A `FULL` transfer always moves the entire position (its `transfer_amount` is updated to the amount actually moved).

**Cost basis**: the seller's `total_invested` is reduced in proportion to the share of value transferred; the recipient's cost basis is the amount received. The same share of the seller's `primary_capital` (its contribution to the opportunity's raised amount) moves to the recipient, so an opportunity's `current_raised_amount` always equals the sum of its holders' primary capital.

**Transfer Fee**: Currently **0%** (waived). `transfer_fee` is always `0.00` and `net_amount` equals `transfer_amount`.

---

## 🏪 Marketplace (Primary)
**Base URL**: `/api/marketplace/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `opportunities/` | Search/filter open opportunities (public) |
| GET | `opportunities/{id}/` | Detailed opportunity view (public) |
| POST | `opportunities/{id}/request_information/` | Request deal information |
| POST | `opportunities/{id}/bookmark/` | Add to watchlist |
| DELETE | `opportunities/{id}/remove_bookmark/` | Remove from watchlist (works for closed opportunities too) |
| GET | `watchlist/` | Your watchlist |

### Investor Interest (pledges)
**Base URL**: `/api/marketplace/investor-interest/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List your pledges |
| POST | `/` | Pledge an amount to an open opportunity |
| PATCH | `/{id}/` | Change `amount` / `investment_date` while PENDING |
| POST | `/{id}/cancel/` | Cancel a PENDING pledge |

A pledge must be at least the opportunity's `min_investment` and within its remaining capacity. `status` is read-only for investors.

**Conversion** *(staff)*: `POST /api/admin/investor-interests/{id}/convert/`
1. Creates an `Investment` for the investor (or tops up an existing one)
2. Logs an `INITIAL_INVESTMENT` `CapitalActivity`
3. Increments `MarketplaceOpportunity.current_raised_amount` and `investors_count`

`CONVERTED` is final. Conversion that would exceed the opportunity's target returns `400` and the pledge stays `PENDING`.

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
**Base URL**: `/api/secondary-market/`

Read-only listing of `PENDING` ownership transfers that have no named recipient.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Browse all available listings |
| GET | `/{id}/` | Listing detail |
| POST | `/{id}/express_interest/` | Register buyer interest (see below) |

**Filters**: `sector`, `transfer_type` (`FULL`/`PARTIAL`), `min_amount`, `max_amount`

### Buying — Interest, then Staff Approval

#### Step 1 — Express Interest (buyer)
```http
POST /api/secondary-market/{transfer_id}/express_interest/
```
Optional body: `{ "amount": 15000.00 }` (defaults to the full listing amount)

**Effect**: Creates a `SecondaryMarketInterest` record with status `PENDING`. **No financial changes occur.**

```json
{
  "message": "Interest registered successfully.",
  "interest_id": 7,
  "created": true,
  "transfer_id": 3,
  "amount": "15000.00",
  "status": "PENDING",
  "note": "Your interest will be reviewed; the purchase executes once approved by staff."
}
```

Buyers manage their interests at **`/api/secondary-market-interests/`**:

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List your buyer interests |
| GET | `/{id}/` | Interest detail |
| PATCH | `/{id}/` | Change `amount` while PENDING |
| POST | `/{id}/cancel/` | Withdraw a PENDING interest |

#### Step 2 — Execute (staff)
```http
PATCH /api/admin/secondary-interests/{id}/
{ "status": "CONVERTED" }      // or "CANCELLED" to decline
```

**What happens atomically**:
1. **Seller's Investment reduced** by the interest `amount` (cost basis reduced proportionally)
   - `PARTIAL_EXIT` capital activity if the seller keeps a balance
   - `FULL_EXIT` if the whole position is sold (investment marked `EXITED`)
2. **Buyer's Investment created** (or topped up) for the same amount, with an `INITIAL_INVESTMENT` capital activity
3. **OwnershipTransfer** marked `COMPLETED` (`to_user` = buyer); other pending interests in the listing are cancelled
4. **`current_raised_amount` is NOT modified** — ownership moves between investors; no new capital enters

If the purchase can't be executed (listing no longer available, amount exceeds the seller's value) the request returns `400` and nothing changes.

---

## 🛠 Admin API (Staff Only)
**Base URL**: `/api/admin/`

REST API to power the custom PrivCap Hub admin panel. **Requires `is_staff=True`**.

| Category | Endpoints (Examples) | Description |
|----------|----------------------|-------------|
| **Dashboard** | `GET /dashboard/` | Platform-wide KPIs (users, AUM, transfers) |
| **Users** | `GET /users/`, `POST /users/{id}/suspend/` | User management; suspending or terminating sessions (`/users/{id}/terminate-sessions/`) signs the user out immediately. Users are created via registration, not here. Granting/removing staff and modifying staff accounts require a **superuser**. |
| **Opportunities** | `GET /opportunities/`, `POST /opportunities/{id}/publish/` | Edit opportunities, toggle features, manage documents |
| **Investments** | `GET /investments/`, `POST /investments/{id}/capital-activities/` | All investments; create/edit and manual capital activity tracking |
| **Investor interests** | `POST /investor-interests/{id}/convert/`, `.../cancel/` | Convert or cancel pledges (PATCH edits amount/date of PENDING pledges) |
| **Transfers** | `POST /transfers/{id}/approve/`, `.../complete/`, `.../reject/` | Approve, complete or reject ownership transfers |
| **Secondary interests** | `PATCH /secondary-interests/{id}/` | Execute (`CONVERTED`) or decline (`CANCELLED`) a purchase |
| **Analytics** | `GET /analytics/users/`, `GET /analytics/aum/` | Staff-only charts (user growth, AUM trend, transfer volume) |
| **System** | `GET /activity-log/`, `GET /audit-log/`, `GET /sessions/` | Platform-wide security logs |

---

## 🔧 Management Commands

### Daily IRR Accrual
Automatic daily growth of investment values based on opportunity target IRR.
- **Command**: `python manage.py accrue_daily_irr` (`--dry-run` to preview)
- **Schedule**: Every 24 hours via `django-rq` (first run immediately on deploy)
- **Idempotency**: Each investment records `last_accrued_date`; a run accrues every day since then (backfilling any missed days) and nothing more, so repeated runs on the same day are no-ops.

### Daily Clean-up
- **Task**: `core.tasks.run_daily_cleanup` (every 24 hours)
- **Behavior**: Flushes expired JWT refresh tokens, deletes OTP codes older than a day, and removes sessions idle longer than the refresh-token lifetime (7 days)

### Opportunity Status Transitions
- **Command**: `python manage.py transition_opportunities`
- **Behavior**: Transitions `NEW` → `ACTIVE` after 24 hours
- **Schedule**: Every 6 hours via `django-rq`

---

## 🌐 Investor Network
**Base URL**: `/api/accounts/network/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `directory/` | Search investor directory (`search`, `sector`, `min_investment`, `location`, `page`, `page_size` ≤ 100) |
| GET | `{profile_id}/profile/` | View investor profile |
| POST | `connect/` | Send connection request |
| GET | `connections/?status=ACCEPTED` | List connections |
| PATCH | `{connection_id}/update_connection/` | Accept or reject a pending request |
| GET / PATCH | `my_profile/` | Manage your profile and network visibility |

---

## ⚠️ Error Codes

| Status | Description |
|--------|-------------|
| 400 | Invalid input data, or a business rule was violated (e.g. over-funding) |
| 401 | Invalid or expired token |
| 403 | Insufficient rights (e.g. seller trying to buy own listing) |
| 404 | Resource does not exist |
| 405 | Method not allowed (e.g. investors writing investments) |
| 429 | Request limit exceeded |
| 500 | Unexpected error — details are logged server-side, never returned |

All error bodies have the shape `{ "error": true, "message": "...", "details": ... }`.

## 📦 Data Types

**Currency**: Opportunities carry a `currency` code (default **NGN**).  
**Dates**: ISO 8601 format (`YYYY-MM-DD`).  
**Timestamps**: ISO 8601 with timezone (`YYYY-MM-DDThh:mm:ssZ`).  
**Decimal amounts**: Precision to 2 decimal places.
