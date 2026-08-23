from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

import os
import razorpay
import sqlite3
from datetime import datetime


# =========================================================
# ENV
# =========================================================

load_dotenv()


# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="AI Payment Recovery",
    description="AI-powered Razorpay payment recovery system",
    version="1.0.0"
)


# =========================================================
# RAZORPAY
# =========================================================

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)


# =========================================================
# DATABASE
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / "payment.db"


def get_db():
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            payment_id TEXT,
            amount REAL NOT NULL,
            currency TEXT DEFAULT 'INR',
            status TEXT NOT NULL,
            failure_reason TEXT,
            recovery_of_order_id TEXT,
            recovered_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    # -----------------------------------------------------
    # Migration for old database
    # -----------------------------------------------------

    columns = conn.execute(
        "PRAGMA table_info(payments)"
    ).fetchall()

    column_names = [column["name"] for column in columns]

    if "recovery_of_order_id" not in column_names:
        conn.execute("""
            ALTER TABLE payments
            ADD COLUMN recovery_of_order_id TEXT
        """)

    if "recovered_at" not in column_names:
        conn.execute("""
            ALTER TABLE payments
            ADD COLUMN recovered_at TEXT
        """)

    conn.commit()
    conn.close()


init_database()


# =========================================================
# MODELS
# =========================================================

class OrderRequest(BaseModel):
    amount: float
    recovery_of_order_id: str | None = None


class PaymentVerification(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


class PaymentFailure(BaseModel):
    razorpay_order_id: str
    error_description: str | None = None
    error_code: str | None = None


class RecoveryRequest(BaseModel):
    razorpay_order_id: str
    failure_category: str
    severity: str
    failure_reason: str


# =========================================================
# HOME
# =========================================================

@app.get("/", response_class=HTMLResponse)
def home():

    html_path = BASE_DIR / "templates" / "index.html"

    if not html_path.exists():

        return """
        <h1>AI Payment Recovery</h1>
        <p>FastAPI backend is connected.</p>
        """

    return html_path.read_text(encoding="utf-8")


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {
        "status": "healthy",
        "service": "AI Payment Recovery"
    }


# =========================================================
# CONFIG
# =========================================================

@app.get("/config-check")
def config_check():

    return {
        "razorpay_key_loaded": bool(RAZORPAY_KEY_ID),
        "razorpay_secret_loaded": bool(RAZORPAY_KEY_SECRET),
        "database": str(DATABASE)
    }


# =========================================================
# CREATE ORDER
# =========================================================

@app.post("/create-order")
async def create_order(data: OrderRequest):

    if data.amount <= 0:

        return {
            "success": False,
            "error": "Amount must be greater than 0."
        }

    try:

        amount_in_paise = int(round(data.amount * 100))

        order_data = {
            "amount": amount_in_paise,
            "currency": "INR",
            "payment_capture": 1
        }

        order = razorpay_client.order.create(
            data=order_data
        )

        now = datetime.now().isoformat()

        conn = get_db()

        conn.execute("""
            INSERT INTO payments
            (
                order_id,
                payment_id,
                amount,
                currency,
                status,
                failure_reason,
                recovery_of_order_id,
                recovered_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order["id"],
            None,
            data.amount,
            "INR",
            "CREATED",
            None,
            data.recovery_of_order_id,
            None,
            now,
            now
        ))

        conn.commit()
        conn.close()

        return {
            "success": True,
            "order_id": order["id"],
            "amount": order["amount"],
            "currency": order["currency"],
            "key_id": RAZORPAY_KEY_ID,
            "recovery_of_order_id": data.recovery_of_order_id
        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }


# =========================================================
# VERIFY PAYMENT
# =========================================================

@app.post("/verify-payment")
def verify_payment(data: PaymentVerification):

    try:

        razorpay_client.utility.verify_payment_signature({

            "razorpay_order_id": data.razorpay_order_id,

            "razorpay_payment_id": data.razorpay_payment_id,

            "razorpay_signature": data.razorpay_signature

        })

        now = datetime.now().isoformat()

        conn = get_db()

        # -------------------------------------------------
        # Get current order
        # -------------------------------------------------

        current_payment = conn.execute("""
            SELECT *
            FROM payments
            WHERE order_id = ?
        """, (
            data.razorpay_order_id,
        )).fetchone()

        if current_payment is None:

            conn.close()

            return {
                "success": False,
                "message": "Order not found in database.",
                "order_id": data.razorpay_order_id
            }

        # -------------------------------------------------
        # Current payment -> SUCCESS
        # -------------------------------------------------

        result = conn.execute("""
            UPDATE payments
            SET
                payment_id = ?,
                status = 'SUCCESS',
                failure_reason = NULL,
                updated_at = ?
            WHERE order_id = ?
        """, (
            data.razorpay_payment_id,
            now,
            data.razorpay_order_id
        ))

        # -------------------------------------------------
        # RECOVERY LOGIC
        # -------------------------------------------------

        recovery_of_order_id = current_payment[
            "recovery_of_order_id"
        ]

        recovered_order = None

        if recovery_of_order_id:

            recovered_order = conn.execute("""
                SELECT *
                FROM payments
                WHERE order_id = ?
                AND status = 'FAILED'
            """, (
                recovery_of_order_id,
            )).fetchone()

            if recovered_order:

                conn.execute("""
                    UPDATE payments
                    SET
                        status = 'RECOVERED',
                        payment_id = ?,
                        recovered_at = ?,
                        updated_at = ?
                    WHERE order_id = ?
                """, (
                    data.razorpay_payment_id,
                    now,
                    now,
                    recovery_of_order_id
                ))

        conn.commit()

        updated_rows = result.rowcount

        conn.close()

        if updated_rows == 0:

            return {
                "success": False,
                "message": "Payment verification failed.",
                "order_id": data.razorpay_order_id
            }

        return {

            "success": True,

            "message": (
                "Payment recovered successfully"
                if recovered_order
                else "Payment verified successfully"
            ),

            "payment_id": data.razorpay_payment_id,

            "order_id": data.razorpay_order_id,

            "status": "SUCCESS",

            "recovered_order_id": (
                recovery_of_order_id
                if recovered_order
                else None
            ),

            "recovered": bool(recovered_order)

        }

    except Exception as e:

        return {

            "success": False,

            "message": "Payment verification failed",

            "error": str(e)

        }


# =========================================================
# PAYMENT FAILED
# =========================================================

@app.post("/payment-failed")
def payment_failed(data: PaymentFailure):

    try:

        now = datetime.now().isoformat()

        failure_reason = (
            data.error_description
            or "Payment failed"
        )

        conn = get_db()

        payment = conn.execute("""
            SELECT *
            FROM payments
            WHERE order_id = ?
        """, (
            data.razorpay_order_id,
        )).fetchone()

        if payment is None:

            conn.close()

            return {
                "success": False,
                "error": "Payment order not found.",
                "searched_order_id": data.razorpay_order_id
            }

        result = conn.execute("""
            UPDATE payments
            SET
                status = 'FAILED',
                failure_reason = ?,
                updated_at = ?
            WHERE order_id = ?
        """, (
            failure_reason,
            now,
            data.razorpay_order_id
        ))

        conn.commit()
        conn.close()

        return {

            "success": True,

            "message": "Failed payment recorded",

            "order_id": data.razorpay_order_id,

            "status": "FAILED",

            "failure_reason": failure_reason,

            "updated_rows": result.rowcount

        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }


# =========================================================
# GET PAYMENTS
# =========================================================

@app.get("/payments")
def get_payments():

    conn = get_db()

    payments = conn.execute("""
        SELECT *
        FROM payments
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return {

        "success": True,

        "count": len(payments),

        "payments": [
            dict(payment)
            for payment in payments
        ]

    }


# =========================================================
# PAYMENT STATISTICS
# =========================================================

@app.get("/payment-stats")
def payment_stats():

    conn = get_db()

    total = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
    """).fetchone()["count"]

    successful = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'SUCCESS'
    """).fetchone()["count"]

    failed = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'FAILED'
    """).fetchone()["count"]

    recovered = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'RECOVERED'
    """).fetchone()["count"]

    created = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'CREATED'
    """).fetchone()["count"]

    conn.close()

    # -----------------------------------------------------
    # ACTUAL RECOVERY RATE
    # -----------------------------------------------------

    recovery_attempts = failed + recovered

    recovery_rate = 0

    if recovery_attempts > 0:

        recovery_rate = round(
            (recovered / recovery_attempts) * 100,
            2
        )

    return {

        "total_payments": total,

        "successful_payments": successful,

        "failed_payments": failed,

        "recovered_payments": recovered,

        "pending_payments": created,

        "recovery_rate": f"{recovery_rate}%"

    }


# =========================================================
# RECOVERY STATS
# =========================================================

@app.get("/recovery-stats")
def recovery_stats():

    conn = get_db()

    recovered = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'RECOVERED'
    """).fetchone()["count"]

    failed = conn.execute("""
        SELECT COUNT(*) AS count
        FROM payments
        WHERE status = 'FAILED'
    """).fetchone()["count"]

    conn.close()

    total_recovery_cases = recovered + failed

    rate = 0

    if total_recovery_cases > 0:

        rate = round(
            (recovered / total_recovery_cases) * 100,
            2
        )

    return {

        "recovered": recovered,

        "failed": failed,

        "total_recovery_cases": total_recovery_cases,

        "recovery_rate": f"{rate}%"

    }


# =========================================================
# FAILURE ANALYSIS
# =========================================================

def analyze_failure(failure_reason: str):

    reason = failure_reason.lower()

    if "declined" in reason or "bank" in reason:

        return {
            "category": "BANK_DECLINED",
            "severity": "MEDIUM",
            "recommendation":
                "Try another payment method such as UPI or NetBanking."
        }

    elif "insufficient" in reason or "balance" in reason:

        return {
            "category": "INSUFFICIENT_BALANCE",
            "severity": "HIGH",
            "recommendation":
                "Ask the customer to use another account or payment method."
        }

    elif "cancel" in reason or "closed" in reason:

        return {
            "category": "USER_CANCELLED",
            "severity": "LOW",
            "recommendation":
                "Encourage the customer to retry the payment."
        }

    elif "timeout" in reason or "timed out" in reason:

        return {
            "category": "TIMEOUT",
            "severity": "MEDIUM",
            "recommendation":
                "Retry the payment after a short delay."
        }

    elif "network" in reason or "connection" in reason:

        return {
            "category": "NETWORK_ERROR",
            "severity": "MEDIUM",
            "recommendation":
                "Check the internet connection and retry the payment."
        }

    else:

        return {
            "category": "UNKNOWN",
            "severity": "MEDIUM",
            "recommendation":
                "Try another payment method or retry the payment."
        }


# =========================================================
# ANALYZE FAILED PAYMENT
# =========================================================

@app.post("/analyze-failure")
def analyze_failed_payment(data: PaymentFailure):

    try:

        conn = get_db()

        payment = conn.execute("""
            SELECT *
            FROM payments
            WHERE order_id = ?
        """, (
            data.razorpay_order_id,
        )).fetchone()

        if payment is None:

            conn.close()

            return {
                "success": False,
                "error": "Payment order not found.",
                "searched_order_id": data.razorpay_order_id
            }

        failure_reason = (
            data.error_description
            or payment["failure_reason"]
            or "Payment failed"
        )

        analysis = analyze_failure(
            failure_reason
        )

        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE payments
            SET
                status = 'FAILED',
                failure_reason = ?,
                updated_at = ?
            WHERE order_id = ?
        """, (
            failure_reason,
            now,
            data.razorpay_order_id
        ))

        conn.commit()
        conn.close()

        return {

            "success": True,

            "order_id": data.razorpay_order_id,

            "amount": payment["amount"],

            "currency": payment["currency"],

            "status": "FAILED",

            "failure_reason": failure_reason,

            "error_code": data.error_code,

            "category": analysis["category"],

            "severity": analysis["severity"],

            "recommendation": analysis["recommendation"]

        }

    except Exception as e:

        return {
            "success": False,
            "error": str(e)
        }


# =========================================================
# RECOVERY ENGINE
# =========================================================

@app.post("/recovery-recommendation")
def recovery_recommendation(data: RecoveryRequest):

    category = data.failure_category.upper()
    severity = data.severity.upper()

    action = "RETRY_PAYMENT"
    payment_method = "UPI"
    message = "Please try the payment again using UPI."
    priority = "MEDIUM"

    if category == "BANK_DECLINED":

        action = "TRY_ALTERNATIVE_METHOD"
        payment_method = "UPI_OR_NETBANKING"

        message = (
            "Your bank declined the payment. "
            "Please retry using UPI or NetBanking."
        )

        priority = "HIGH"

    elif category == "INSUFFICIENT_BALANCE":

        action = "TRY_DIFFERENT_ACCOUNT"
        payment_method = "UPI_OR_OTHER_BANK"

        message = (
            "The payment could not be completed because "
            "of insufficient funds. Try another bank account."
        )

        priority = "HIGH"

    elif category == "USER_CANCELLED":

        action = "RETRY_PAYMENT"
        payment_method = "UPI"

        message = (
            "The payment was cancelled. "
            "Please retry the payment using UPI."
        )

        priority = "LOW"

    elif category == "NETWORK_ERROR":

        action = "RETRY_PAYMENT"
        payment_method = "SAME_METHOD"

        message = (
            "A temporary network issue occurred. "
            "Please retry the payment."
        )

        priority = "LOW"

    elif category == "TIMEOUT":

        action = "RETRY_PAYMENT"
        payment_method = "UPI"

        message = (
            "The payment request timed out. "
            "Please retry using UPI."
        )

        priority = "MEDIUM"

    elif category == "INVALID_DETAILS":

        action = "CORRECT_DETAILS"
        payment_method = "SAME_METHOD"

        message = (
            "Some payment details appear to be incorrect. "
            "Please verify your details and try again."
        )

        priority = "MEDIUM"

    else:

        action = "TRY_ALTERNATIVE_METHOD"
        payment_method = "UPI"

        message = (
            "We could not identify the exact reason "
            "for the payment failure. Please try UPI."
        )

        priority = "MEDIUM"

    if severity == "HIGH":
        priority = "URGENT"

    return {

        "success": True,

        "order_id": data.razorpay_order_id,

        "failure_category": category,

        "severity": severity,

        "recovery_action": action,

        "recommended_payment_method": payment_method,

        "priority": priority,

        "message": message

    }