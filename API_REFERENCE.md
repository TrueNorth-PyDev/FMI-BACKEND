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

### Security
**Base URL**: `/api/accounts/account/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `sessions/` | List active sessions |
| DELETE | `revoke_session/` | Terminate a session |
| GET | `activity/` | View recent account activity |

---

## 💰 Portfolio Management

### Investments
**Base URL**: `/api/investments/investments/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List all investments |
| POST | `/` | Create new investment record |
| GET | `/{id}/` | Get detailed investment view |
| GET | `/{id}/performance/` | Get performance history |
| GET | `/{id}/irr/` | Calculate IRR for investment |

### Capital Activities
**Base URL**: `/api/investments/capital-activities/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | List activities (calls, distributions) |
| POST | `/` | Record new capital activity |

---

## 📊 Analytics Dashboard

**Base URL**: `/api/investments/portfolio/`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `overview/` | Key metrics & sector performance |
| GET | `performance_analysis/` | Quarterly returns & risk ratios |
| GET | `asset_allocation/` | Current vs Target allocation |
| GET | `risk_metrics/` | Volatility, stress tests, concentration |

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
| GET | `opportunities/{id}/` | detailed opportunity view |
| POST | `opportunities/{id}/request_information/` | Request deal access |
| POST | `watchlist/add/` | Add to watchlist |
| DELETE | `watchlist/remove/` | Remove from watchlist |

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
| 400 | `validation_error` | Invalid input data |
| 401 | `authentication_failed` | Invalid or expired token |
| 403 | `permission_denied` | Insufficient rights |
| 404 | `not_found` | Resource does not exist |
| 429 | `throttled` | Request limit exceeded |

## 📦 Data Types

**Currency**: All monetary values are in **USD**.  
**Dates**: ISO 8601 format (`YYYY-MM-DD`).  
**Timestamps**: ISO 8601 with timezone (`YYYY-MM-DDThh:mm:ssZ`).
