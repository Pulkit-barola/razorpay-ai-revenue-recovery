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
