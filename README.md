````
# AI Payment Recovery

An AI-powered payment failure detection and recovery system built for the Razorpay Buildathon.

## 🚀 Overview

AI Payment Recovery helps identify failed payments, analyze the reason for failure, and generate an intelligent recovery recommendation for the customer.

Instead of simply showing "Payment Failed", the system explains the failure and suggests the most suitable next action, such as retrying with UPI, NetBanking, or another payment method.

## 🎯 Problem Statement

Payment failures are common in digital payments. However, users often receive generic failure messages and don't know what to do next.

This can lead to:

- Abandoned payments
- Poor user experience
- Lost conversions
- Repeated failed attempts

## 💡 Solution

AI Payment Recovery creates a recovery workflow:

Payment Attempt  
↓  
Payment Success / Failure Detection  
↓  
Failure Stored in Database  
↓  
Failure Reason Analysis  
↓  
Recovery Recommendation  
↓  
Alternative Payment Method / Retry

## ✨ Key Features

- Razorpay Test Mode payment integration
- Payment success and failure tracking
- SQLite payment history
- Failed payment analysis
- Failure categorization
- Severity detection
- Recovery recommendations
- Alternative payment method suggestions
- Retry payment functionality
- Recovery dashboard
- Test Mode support

## 🧠 Recovery Engine

The system analyzes payment failures and generates recommendations based on the failure category.

Example:

**Failure Category:** `BANK_DECLINED`

**Severity:** `HIGH`

**Recommendation:**  
Try another payment method such as UPI or NetBanking.

Another example:

**Failure Category:** `USER_CANCELLED`

**Severity:** `MEDIUM`

**Recommendation:**  
Retry the payment using UPI.

## 🛠️ Technology Stack

### Backend
- Python
- FastAPI
- Uvicorn

### Frontend
- HTML
- CSS
- JavaScript

### Database
- SQLite

### Payment Gateway
- Razorpay Test Mode

### API Testing
- Swagger UI

## 📁 Project Structure

```text
AI_Payment_Recovery/
│
├── templates/
│   └── index.html
│
├── main.py
├── requirement.txt
├── .gitignore
└── README.md
````

## 🔌 API Endpoints

| Method | Endpoint                   | Purpose                          |
| ------ | -------------------------- | -------------------------------- |
| GET    | `/`                        | Payment Recovery UI              |
| GET    | `/health`                  | Application health check         |
| GET    | `/config-check`            | Configuration check              |
| POST   | `/create-order`            | Create Razorpay order            |
| POST   | `/verify-payment`          | Verify payment                   |
| POST   | `/payment-failed`          | Record failed payment            |
| POST   | `/analyze-failure`         | Analyze payment failure          |
| POST   | `/recovery-recommendation` | Generate recovery recommendation |
| GET    | `/payments`                | Get payment history              |
| GET    | `/payment-stats`           | Get payment statistics           |

## ▶️ Run Locally

### 1. Clone the repository

```bash
git clone https://github.com/Pulkit-barola/AI_Payment_recovery.git
cd AI_Payment_recovery
```

### 2. Create virtual environment

```bash
python -m venv venv
```

### 3. Activate virtual environment

Windows:

```bash
venv\Scripts\activate
```

### 4. Install dependencies

```bash
pip install -r requirement.txt
```

### 5. Configure environment variables

Create a `.env` file:

```env
RAZORPAY_KEY_ID=your_test_key_id
RAZORPAY_KEY_SECRET=your_test_key_secret
```

**Never commit your `.env` file or API credentials to GitHub.**

### 6. Start the server

```bash
uvicorn main:app --reload --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

## 🧪 Testing

The project can be tested through:

* Frontend payment flow
* Razorpay Test Mode
* Swagger UI
* Payment failure scenarios
* Failure analysis API
* Recovery recommendation API
* Payment history API

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

## 📊 Dashboard

The dashboard provides:

* Total payments
* Successful payments
* Failed payments
* Recovery rate
* Payment recovery information
* Failure reason
* Failure category
* Recommended payment method
* Priority
* AI recommendation

## 🔐 Security

Sensitive configuration is kept outside the repository using environment variables.

The following files are excluded using `.gitignore`:

```text
.env
venv/
.venv/
__pycache__/
*.pyc
payment.db
```

## 🔮 Future Improvements

* Real-time payment failure webhooks
* More advanced ML-based failure prediction
* Customer-specific recovery recommendations
* Payment success probability prediction
* Analytics dashboard
* Email/SMS recovery notifications
* Production Razorpay integration
* Deployment on cloud infrastructure

## 👨‍💻 Author

**Pulkit Barola**

AI Payment Recovery — Razorpay Buildathon
```
