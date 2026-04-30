# Ledger Engine API Contract

This document defines the strict inputs and outputs for the FastAPI backend. The frontend MUST adhere to these structures.

---

## 1. Infrastructure Operations

### System Health
Checks if the network, server, and database connection are alive.

* **Endpoint:** `GET /api/health`
* **Request Body:** None
* **Success Response (200 OK):**
  ```json
  {
    "status": "ok"
  }

## 2. Ingestion Engine

### Upload Ledger
Accepts a raw Excel export from the bank, runs it through the Pandas ETL script, validates it against Pydantic, and writes to the database.

* **Endpoint:** `POST /api/transactions/upload`
* **Content-Type:** multipart/form-data
* **Payload:** * file: (Binary .xlsx file)
* **Success Response (201 Created):**
  ```json
  {
    "filename": "Xlsx.xlsx",
    "status": "success",
    "records_processed": 142,
    "total_amount_inserted": 4500.50,
    "message": "Ledger successfully synchronized with the vault."
  }

* **Error Response (400 Bad Request - Invalid Data):**
  ```json
    {
      "detail": "Validation Error: Row 15 contains NaN in required field 'amount'."
    }
* **Error Response (415 Unsupported Media Type):**
  ```json
    {
      "detail": "Invalid file type. Only .xlsx files are permitted."
    }

## 3. Vault Retrieval

### Get Transactions
Fetches the standardized financial data to populate the frontend dashboard. Supports basic pagination and date filtering. 
* **Endpoint:** `GET /api/transactions`
* **Query Parameters (Optional):**
  * `limit` (int): Default 50, Max 100
  * `offset` (int): Default 0
  * `start_date` (string): YYYY-MM-DD
  * `end_date` (string): YYYY-MM-DD
* **Success Response (200 OK):**
  ```json
     {
        "data": [
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
        ],
        "pagination": {
          "total_records": 1,
          "limit": 50,
          "offset": 0
        }
      }