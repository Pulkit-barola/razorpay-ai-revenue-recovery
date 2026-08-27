from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

import os
import razorpay
import sqlite3
import requests
import json
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

app.mount("/static", StaticFiles(directory="static"), name="static")


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
            escalated INTEGER DEFAULT 0,
            recommendation_en TEXT,
            recommendation_hinglish TEXT,
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

    if "escalated" not in column_names:
        conn.execute("""
            ALTER TABLE payments
            ADD COLUMN escalated INTEGER DEFAULT 0
        """)

    if "recommendation_en" not in column_names:
        conn.execute("""
            ALTER TABLE payments
            ADD COLUMN recommendation_en TEXT
        """)

    if "recommendation_hinglish" not in column_names:
        conn.execute("""
            ALTER TABLE payments
            ADD COLUMN recommendation_hinglish TEXT
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

def analyze_failure_with_gemini(failure_reason: str):
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        print("Gemini: No API key found, using fallback.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
    
    prompt = f"""You are an expert AI payment recovery assistant for Razorpay.
Analyze the following payment failure reason: "{failure_reason}"

Provide the output strictly in JSON format with the following keys:
- category: Choose exactly one of: "BANK_DECLINED", "INSUFFICIENT_BALANCE", "TIMEOUT", "NETWORK_ERROR", "USER_CANCELLED", or "UNKNOWN".
- severity: "LOW", "MEDIUM", "HIGH", or "URGENT".
- recommendation_en: A short English recommendation for recovery.
- recommendation_hinglish: A friendly Hinglish recommendation for recovery.

Output ONLY the raw JSON object, no markdown formatting."""
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        print(f"Gemini API Status: {response.status_code}")
        if response.status_code == 200:
            res_data = response.json()
            text = res_data['candidates'][0]['content']['parts'][0]['text']
            
            # Clean up potential markdown formatting
            text = text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            
            print(f"Gemini parsed text: {text[:200]}")
            return json.loads(text)
        else:
            print(f"Gemini API Error Response: {response.text[:300]}")
    except Exception as e:
        print(f"Gemini API Exception: {e}")
    return None


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

        category = None
        severity = None
        rec_en = None
        rec_hinglish = None

        ai_analysis = analyze_failure_with_gemini(failure_reason)
        if ai_analysis:
            category = ai_analysis.get("category", "UNKNOWN").upper()
            severity = ai_analysis.get("severity", "MEDIUM").upper()
            rec_en = ai_analysis.get("recommendation_en")
            rec_hinglish = ai_analysis.get("recommendation_hinglish")

        if not category:
            fallback = analyze_failure(failure_reason)
            category = fallback["category"]
            severity = fallback["severity"]
            rec_en = fallback["recommendation"]
            rec_hinglish = "Payment fail ho gaya hai, kripya retry karein ya doosra method use karein."

        now = datetime.now().isoformat()

        conn.execute("""
            UPDATE payments
            SET
                status = 'FAILED',
                failure_reason = ?,
                recommendation_en = ?,
                recommendation_hinglish = ?,
                updated_at = ?
            WHERE order_id = ?
        """, (
            failure_reason,
            rec_en,
            rec_hinglish,
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

            "category": category,

            "severity": severity,

            "recommendation": rec_en,
            
            "recommendation_hinglish": rec_hinglish

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


# =========================================================
# BATCH SIMULATION
# =========================================================

@app.post("/simulate-batch")
def simulate_batch():
    try:
        now = datetime.now().isoformat()
        conn = get_db()
        
        mock_failures = [
            ("The bank declined the transaction as the card is inactive.", "BANK_DECLINED"),
            ("The transaction could not be processed due to insufficient funds.", "INSUFFICIENT_BALANCE"),
            ("Customer closed the payment window before entering OTP.", "USER_CANCELLED"),
            ("Payment request timed out due to bank network latency.", "TIMEOUT"),
            ("Connection lost between merchant and gateway.", "NETWORK_ERROR"),
            ("Incorrect PIN entered by user.", "INVALID_DETAILS"),
            ("Insufficient balance in UPI linked account.", "INSUFFICIENT_BALANCE"),
            ("Card transaction declined by issuer bank limit.", "BANK_DECLINED"),
            ("User cancelled UPI transaction.", "USER_CANCELLED"),
            ("Payment gateway timed out during processing.", "TIMEOUT")
        ]
        
        simulated_orders = []
        
        for idx, (reason, category) in enumerate(mock_failures):
            order_id = f"order_sim_{random.randint(100000, 999999)}_{idx}"
            amount = round(random.uniform(100, 5000), 2)
            
            # 1. Create failed payment record
            conn.execute("""
                INSERT INTO payments
                (order_id, payment_id, amount, currency, status, failure_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, None, amount, "INR", "FAILED", reason, now, now))
            
            # Run local analysis to set initial recommendations
            analysis = analyze_failure(reason)
            rec_en = analysis["recommendation"]
            rec_hinglish = "Payment fail ho gaya hai, kripya doosra account use karein."
            
            conn.execute("""
                UPDATE payments
                SET recommendation_en = ?, recommendation_hinglish = ?
                WHERE order_id = ?
            """, (rec_en, rec_hinglish, order_id))
            
            simulated_orders.append((order_id, amount))
            
        # 2. Simulate recovery for 4 out of 10 orders (40% recovery rate)
        recovered_indices = random.sample(range(10), 4)
        for idx in recovered_indices:
            orig_order_id, amount = simulated_orders[idx]
            recovery_order_id = f"order_sim_rec_{random.randint(100000, 999999)}_{idx}"
            payment_id = f"pay_sim_{random.randint(1000000, 9999999)}"
            
            # Create successful recovery payment
            conn.execute("""
                INSERT INTO payments
                (order_id, payment_id, amount, currency, status, failure_reason, recovery_of_order_id, recovered_at, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (recovery_order_id, payment_id, amount, "INR", "SUCCESS", None, orig_order_id, now, now, now))
            
            # Update original failed payment to RECOVERED
            conn.execute("""
                UPDATE payments
                SET status = 'RECOVERED', payment_id = ?, recovered_at = ?, updated_at = ?
                WHERE order_id = ?
            """, (payment_id, now, now, orig_order_id))
            
        conn.commit()
        conn.close()
        return {"success": True, "message": "Successfully simulated 10 payment recovery cohort cases."}
    except Exception as e:
        return {"success": False, "error": str(e)}


# =========================================================
# AUDIT TRAIL EXPORT
# =========================================================

from fastapi.responses import StreamingResponse
import io
import csv
import random

@app.get("/export-audit")
def export_audit():
    try:
        conn = get_db()
        cursor = conn.execute("""
            SELECT id, order_id, payment_id, amount, currency, status, failure_reason, recovery_of_order_id, recovered_at, escalated, recommendation_en, recommendation_hinglish, created_at, updated_at
            FROM payments
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        conn.close()
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "ID", "Order ID", "Payment ID", "Amount", "Currency", "Status", 
            "Failure Reason", "Recovery of Order ID", "Recovered At", "Escalated",
            "Recommendation (English)", "Recommendation (Hinglish)", "Created At", "Updated At"
        ])
        
        # Write data rows
        for row in rows:
            writer.writerow(list(row))
            
        output.seek(0)
        
        return StreamingResponse(
            io.StringIO(output.getvalue()), 
            media_type="text/csv", 
            headers={"Content-Disposition": "attachment; filename=payment_recovery_audit_trail.csv"}
        )
    except Exception as e:
        return {"success": False, "error": str(e)}