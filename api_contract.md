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
- **Success Response `200 OK`:**

```json
{
  "filename": "ledger_export.xlsx",
  "content_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "user_email": "user@example.com",
  "message": "File successfully passed the airlock.",
  "records_processed": 142
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

| Parameter | Type  | Default | Description              |
|-----------|-------|---------|--------------------------|
| `limit`   | `int` | `50`    | Number of records to return |
| `offset`  | `int` | `0`     | Pagination offset         |

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