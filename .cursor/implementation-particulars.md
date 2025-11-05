GRN Pipeline V2 - Email & Snowflake Implementation Details
This document provides exact implementation details for email sending and Snowflake connection establishment in grn_pipeline_v2.

📧 Email Sending Implementation
Configuration Location
File: grn_pipeline_v2/config/email.yaml

smtp:
  host: "smtp.office365.com"
  port: 587
  use_tls: true
  
  # Credentials (loaded from environment or key vault)
  sender_email: "ds-support@marico.com"
  password_sources:
    - environment_variable: "EMAIL_PASSWORD"
    - key_vault: "email-password"
  
  # Recipients
  recipients:
    - "abhinav.tripathi@marico.com"
  
  cc_recipients: []
Implementation Details
File: grn_pipeline_v2/src/writers/email_writer.py

Key Components:
Python Libraries Used:

smtplib - For SMTP connection
ssl - For TLS encryption
email.message.EmailMessage - For email message construction
pandas - For CSV attachment generation
io.StringIO - For in-memory CSV buffer
Initialization (lines 26-37):

def __init__(self, config: Dict[str, Any]):
    self.config = config
    self.smtp_config = config.get('smtp', {})
    self.recipients = self.smtp_config.get('recipients', [])
    self.cc_recipients = self.smtp_config.get('cc_recipients', [])
    self.sender_email = self.smtp_config.get('sender_email', 'ds-support@marico.com')
    
    # Get password from environment or config
    self.password = os.getenv("EMAIL_PASSWORD")
    if not self.password:
        # Fallback to hardcoded password (not recommended for production)
        self.password = 'Science&Data111'
Email Sending Method (lines 183-217):
def _send_email(self, subject: str, body: str, df: pd.DataFrame, filename: str):
    """Send email with attachment"""
    
    SMTP_HOST = self.smtp_config.get('host', 'smtp.office365.com')
    SMTP_PORT = self.smtp_config.get('port', 587)
    
    # Create email message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = self.sender_email
    msg["To"] = ", ".join(self.recipients)
    
    if self.cc_recipients:
        msg["Cc"] = ", ".join(self.cc_recipients)
    
    msg.set_content(body)
    
    # Convert DataFrame to CSV in memory
    csv_buffer = StringIO()
    df.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue().encode("utf-8")
    
    # Add CSV attachment
    msg.add_attachment(
        csv_bytes,
        maintype="text",
        subtype="csv",
        filename=filename,
    )
    
    # Establish SMTP connection with TLS
    context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=context)  # Enable TLS
        smtp.login(self.sender_email, self.password)
        smtp.send_message(msg)
    
    logger.info(f"Email sent to {', '.join(self.recipients)}")
Step-by-Step Email Sending Process:
Read Configuration: Load SMTP settings from YAML config
Get Password: Retrieve from EMAIL_PASSWORD environment variable (fallback to hardcoded)
Create Email Message: Use EmailMessage() class
Set Headers: Subject, From, To, Cc (if any)
Set Body: Plain text email body
Add Attachment: Convert pandas DataFrame to CSV in memory, encode as UTF-8, attach to email
Connect to SMTP: Connect to smtp.office365.com:587
Enable TLS: Call starttls() with SSL context
Authenticate: Login with sender email and password
Send: Call send_message() to send the email
Important Notes:
SMTP Server: smtp.office365.com on port 587
TLS Required: Must use starttls() before login
Password Source: Environment variable EMAIL_PASSWORD (fallback to hardcoded)
Attachment Format: CSV generated from pandas DataFrame, encoded as UTF-8 bytes
# Snowflake Connector Overview

Comprehensive summary of the Snowflake access pattern that can be transplanted into another codebase.

## Connection Configuration

- Environment variables feed a `_conn_kwargs()` helper that builds the keyword arguments for `snowflake.connector.connect`.

- Required keys: `SNOWFLAKE_ACCOUNT`, `SNOWFLAKE_USER`, `SNOWFLAKE_PASSWORD`, `SNOWFLAKE_DATABASE`, `SNOWFLAKE_SCHEMA`. Fail fast with a `RuntimeError` if any are missing.

- Optional keys: `SNOWFLAKE_ROLE`, `SNOWFLAKE_WAREHOUSE`. When present, issue `USE ROLE` / `USE WAREHOUSE` after connecting. If your helper does not yet inject `SNOWFLAKE_WAREHOUSE` into the connector kwargs, add it before attempting the `USE` command.

- Local setups often use `python-dotenv` to load `.env` files, while production should rely on the platform’s secret store.

## Connection Lifecycle

- `connect()` is implemented as a context manager around `snowflake.connector.connect(**_conn_kwargs())` so cursors and connections close even when queries fail.

- Immediately after connecting, best-effort `USE ROLE`, `USE WAREHOUSE`, `USE DATABASE`, and `USE SCHEMA` are executed for whichever values are configured. Exceptions are swallowed so fully qualified SQL still works.

- Cursor and connection objects close inside `finally` blocks to avoid resource leaks in long-lived workers.

## Query Helpers

- `fetch_all(sql, params=None)`: returns raw tuple rows (ideal for simple version/health checks).

- `fetch_dicts(sql, params=None)`: returns list of dictionaries with lowercase keys (great for JSON payloads).

- `execute(sql, params=None)`: runs DML, commits, and closes the session.

- Every helper opens a new connection via the context manager to keep request scope isolated and avoid shared mutable state.

- Always pass query parameters as dictionaries so the driver handles binding and type conversion.

## Installation Requirements

- Core dependency: `snowflake-connector-python`.

- Optional helper: `python-dotenv` for loading env files during local development.

```bash
pip install snowflake-connector-python python-dotenv
```

## Minimal Helper Implementation

```python
import os
from contextlib import contextmanager
import snowflake.connector


def _conn_kwargs() -> dict:
    kwargs = {
        "account": os.environ["SNOWFLAKE_ACCOUNT"],
        "user": os.environ["SNOWFLAKE_USER"],
        "password": os.environ["SNOWFLAKE_PASSWORD"],
        "database": os.environ["SNOWFLAKE_DATABASE"],
        "schema": os.environ["SNOWFLAKE_SCHEMA"],
    }
    role = os.environ.get("SNOWFLAKE_ROLE")
    warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE")
    if role:
        kwargs["role"] = role
    if warehouse:
        kwargs["warehouse"] = warehouse
    return kwargs


@contextmanager
def connect():
    conn = snowflake.connector.connect(**_conn_kwargs())
    try:
        cur = conn.cursor()
        try:
            role = os.environ.get("SNOWFLAKE_ROLE")
            warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE")
            database = os.environ.get("SNOWFLAKE_DATABASE")
            schema = os.environ.get("SNOWFLAKE_SCHEMA")
            if role:
                cur.execute(f'USE ROLE "{role}"')
            if warehouse:
                cur.execute(f'USE WAREHOUSE "{warehouse}"')
            if database:
                cur.execute(f'USE DATABASE "{database}"')
            if schema:
                cur.execute(f'USE SCHEMA "{schema}"')
        finally:
            cur.close()
        yield conn
    finally:
        conn.close()


def fetch_dicts(sql: str, params: dict | None = None) -> list[dict]:
    with connect() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params or {})
            columns = [col[0].lower() for col in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]
        finally:
            cur.close()


def execute(sql: str, params: dict | None = None) -> None:
    with connect() as conn:
        cur = conn.cursor()
        try:
            cur.execute(sql, params or {})
            conn.commit()
        finally:
            cur.close()
```

## Sample Query Usage

```python
def load_recent_captures(limit: int = 10) -> list[dict]:
    return fetch_dicts(
        """
        SELECT ID, USER_ID, STATUS, COMPLETED_AT
        FROM CAPTURE_SESSIONS
        ORDER BY COMPLETED_AT DESC
        LIMIT %(limit)s
        """,
        {"limit": limit},
    )


def record_capture_session(payload: dict) -> None:
    execute(
        """
        INSERT INTO CAPTURE_SESSIONS (
            ID, USER_ID, PRODUCT_ID, STATUS, COMPLETED_AT
        ) VALUES (
            %(id)s, %(user_id)s, %(product_id)s, %(status)s, %(completed_at)s
        )
        """,
        payload,
    )
```

## Diagnostics & Troubleshooting

- Maintain a diagnostics CLI (e.g., `snowflake_diag.py`) that prints `CURRENT_ROLE`, `CURRENT_WAREHOUSE`, and runs targeted queries to confirm access.

- OCSP or networking errors usually indicate outbound HTTPS is blocked; allow Snowflake endpoints or configure the connector’s OCSP cache as documented by Snowflake.

- Unless you manage pooling explicitly, prefer the “connection per helper call” pattern—it keeps concurrency simple and predictable.