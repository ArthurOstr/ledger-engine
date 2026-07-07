# Ledger Engine API Contract

This document defines the strict inputs, outputs, and security requirements for the FastAPI backend. The frontend **MUST** adhere to these structures.

---

## 1. Infrastructure Operations

### System Health

Checks if the network, server, and database connection are alive.

- **Endpoint:** `GET /api/health`
- **Security:** Public (No token required)
- **Success Response `200 OK`:**

```json
{
  "status": "ok"
}
```

---

## 2. Authentication & Security (Vault Keys)

### Register User

Creates a new user in the database with a mathematically hashed password.

- **Endpoint:** `POST /api/users/register`
- **Security:** Public
- **Request Body (`application/json`):**

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

- **Success Response `201 Created`:**

```json
{
  "id": 1,
  "email": "user@example.com",
  "created_at": "2026-05-05T12:00:00"
}
```

- **Error Response `400 Bad Request`:** Returned if the email is already registered.

---

### Login (Mint Token)

Verifies credentials and returns a signed JSON Web Token (JWT) for subsequent API access.

- **Endpoint:** `POST /api/users/login`
- **Security:** Public
- **Content-Type:** `application/x-www-form-urlencoded` (OAuth2 Standard)
- **Payload:** `username` (email) and `password`
- **Success Response `200 OK`:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI...",
  "token_type": "bearer"
}
```

- **Error Response `401 Unauthorized`:** Returned if credentials fail verification.

---

## 3. Ingestion Engine

### Upload Ledger

Accepts a raw Excel export from the bank, dynamically hashes transactions for tenant isolation, validates against Pydantic, and writes to the database.

- **Endpoint:** `POST /api/transactions/upload`
- **Security:** Protected — requires `Authorization: Bearer <token>` header
- **Content-Type:** `multipart/form-data`
- **Payload:** `file` — binary `.xlsx` file
- **Success Response `202 OK`:**

```json
{
  "filename": "ledger_export.xlsx",
  "user_email": "user@example.com",
  "message": "File successfully passed to the broker.",
  "job_id": "893c83759df14d0382875ab947eb387f",
  "status": "queued"
}
```

- **Error Response `401 Unauthorized`:** Token missing or expired.
- **Error Response `400 Bad Request`:** Invalid data structure or parsing failure.

---

## 4. Vault Retrieval

### Get Transactions

Fetches the standardized financial data to populate the frontend dashboard. Strictly enforces multi-tenant isolation based on the provided JWT.

- **Endpoint:** `GET /api/transactions`
- **Security:** Protected — requires `Authorization: Bearer <token>` header
- **Query Parameters (optional):**

| Parameter | Type  | Default | Description                 |
|-----------|-------|---------|-----------------------------|
| `limit`   | `int` | `50`    | Number of records to return |
| `offset`  | `int` | `0`     | Pagination offset           |

- **Success Response `200 OK`:**

```json
[
  {
    "id": 1,
    "date": "2026-04-10T14:30:00",
    "category": "Groceries",
    "card": "****1234",
    "description": "Local Market",
    "amount": -45.50,
    "currency": "UAH",
    "balance_after": 1500.00,
    "balance_currency": "UAH",
    "transaction_currency": "UAH",
    "transaction_amount": -45.50,
    "created_at": "2026-04-15T21:00:00"
  }
]
```

- **Error Response `401 Unauthorized`:** Token missing or expired.

---

## 5. Categorization Rules Engine (Automation Layer)

### Create and Apply Rule

Creates a dynamic categorization blueprint and instantly triggers a push-down retroactive sweep across the PostgreSQL C-kernel to assign the category to all existing uncategorized transactions matching the substring.

- **Endpoint:** `POST /api/rules`
- **Security:** Protected — requires `Authorization: Bearer <token>` header
- **Content-Type:** `application/json`
- **Request Body (`CategoryRuleCreate`):**

```json
{
  "keyword": "атб",
  "assigned_category": "Groceries",
  "is_active": true
}
```

- **Success Response `201 Created` (`CategoryRuleResponse`):**

```json
{
  "keyword": "атб",
  "assigned_category": "Groceries",
  "is_active": true,
  "id": 1,
  "owner_id": 42
}
```

- **Error Response `400 Bad Request`:** Returned if the keyword is blank or empty.
- **Error Response `401 Unauthorized`:** Token missing or expired.
- **Error Response `409 Conflict`:** Returned if an active rule for this exact keyword already exists for the tenant.

---

### Get Active Rules

Retrieves all active categorization rules belonging strictly to the authenticated tenant. Rules marked as `is_active=false` are stripped at the database level.

- **Endpoint:** `GET /api/rules`
- **Security:** Protected — requires `Authorization: Bearer <token>` header
- **Success Response `200 OK` (`list[CategoryRuleResponse]`):**

```json
[
  {
    "keyword": "атб",
    "assigned_category": "Groceries",
    "is_active": true,
    "id": 1,
    "owner_id": 42
  },
  {
    "keyword": "аврора",
    "assigned_category": "Custom Home Repair",
    "is_active": true,
    "id": 2,
    "owner_id": 42
  }
]
```

- **Error Response `401 Unauthorized`:** Token missing or expired.

---

### Delete Rule

Executes an atomic Core statement to permanently destroy a categorization blueprint. Strictly verifies tenant ownership before deletion to prevent cross-tenant breaches.

- **Endpoint:** `DELETE /api/rules/{rule_id}`
- **Security:** Protected — requires `Authorization: Bearer <token>` header
- **Success Response `204 No Content`:** No body returned upon successful deallocation.
- **Error Response `401 Unauthorized`:** Token missing or expired.
- **Error Response `404 Not Found`:** Returned if the rule ID does not exist or belongs to a different user.
