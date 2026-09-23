# DawaiFlow

![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?style=flat-square&logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python)
![React](https://img.shields.io/badge/Frontend-React-61DAFB?style=flat-square&logo=react)
![Flutter](https://img.shields.io/badge/Mobile-Flutter-02569B?style=flat-square&logo=flutter)
![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=flat-square&logo=postgresql)
![Gemini AI](https://img.shields.io/badge/AI-Gemini%203.1%20Flash--Lite-8E44AD?style=flat-square&logo=google)

> **"Making everyday pharmacy work faster, simpler and smarter."**

DawaiFlow is an AI-powered billing and inventory management platform designed for independent pharmacies in India. It connects medicine identification, purchase intake, inventory, POS billing, payments, expiry management, supplier workflows and reporting into one connected pharmacy workflow.

- **Hackathon:** Innovate Without Borders
- **Category:** Healthcare & MedTech

---

## The Problem

Independent pharmacists face demanding operational workloads that require high precision under continuous customer traffic. In day-to-day operations, pharmacists must manually manage multiple disconnected administrative tasks:

- Manual or repetitive counter billing
- Visual medicine identification and pack data entry
- Complex purchase invoice processing and line-item entry
- Multi-batch and expiry date tracking
- Instant inventory stock updates
- Supplier credit and purchase records
- Customer Khata ledger and outstanding payment tracking
- Customer and supplier returns
- GST-compliant invoice generation
- Handling separate, disconnected software tools or paper ledgers

The core issue facing independent pharmacies is that **every transaction can create additional disconnected administrative work**. While pharmacy operations—purchases, inventory, sales, customer credit, and compliance—are naturally interconnected, traditional tools force pharmacists to handle them as isolated, fragmented steps.

---

## The Solution

DawaiFlow addresses this friction by providing a single, unified operational pipeline:

```
Purchase → AI Scanning → Verification → Inventory → Billing → Payment → Reporting
```

DawaiFlow connects:
- AI-powered medicine strip & packaging scanning
- Prescription/document scanning where supported
- Multi-page purchase invoice/bill OCR extraction
- Automated product & catalog matching
- Batch-level inventory tracking & FEFO allocation
- High-speed POS billing with barcode support
- Purchase and sales return workflows
- Proactive expiry and low-stock monitoring
- Supplier directory and purchase ledgers
- Customer Khata management & payment settlement
- GST-compliant PDF invoice generation
- Thermal receipt printing (ESC/POS)
- Business reporting and CA/tax export workflows

The goal of DawaiFlow is to reduce repetitive administrative friction while keeping the pharmacist fully in control of verification and final operational actions.

---

## Key Features

### AI-Powered Scanning
- **AI Medicine Scanning:** Instant visual recognition of medicine strips and packaging via smartphone camera or uploaded image.
- **Multi-Medicine Strip Scanning:** Capture and identify multiple medicine items in a single photo workflow.
- **Purchase Invoice & Bill Scanning:** AI OCR extracts line items, batch numbers, expiry dates, quantities, PTR, MRP, and GST rates from supplier invoices.
- **Multi-Image Invoice Scanning:** Support for uploading multiple bill photos for multi-page supplier invoices.
- **Document & Prescription Scanning:** OCR extraction from supported pharmacy documents.
- **Catalog Matching:** Automatically maps extracted text to the pharmacy's catalog master.

> *Note: AI extraction is designed for operational assistance. Pharmacists verify extracted information before committing transactions. DawaiFlow does not provide medical diagnosis or automatic prescription validation.*

### Smart Pharmacy Billing
- **Fast POS Billing:** Streamlined checkout designed for rapid counter service.
- **Barcode Scanning:** Instant item lookup via standard product barcodes.
- **AI-Assisted Selection:** Quick medicine search and identification during billing.
- **Batch-Aware FEFO Billing:** Automatically suggests and allocates batches nearing expiry first (First Expiry, First Out).
- **Loose Tablet Dispensing:** Support for selling partial/strip-break tablet quantities with accurate price calculation.
- **Hold & Resume Bills:** Temporarily park customer transactions and resume them seamlessly.
- **Split & Multiple Payment Modes:** Accept cash, UPI, card, or credit combinations in a single bill.
- **Dynamic UPI QR Code:** Generates dynamic payment QR codes for instant customer scanning.
- **Doctor & Patient Tagging:** Tag bills with patient names and prescribing doctor details.
- **Schedule H / H1 Warnings:** Operational reminders for regulated prescription drugs where supported.

### Live Inventory
- **Real-Time Stock Updates:** Automatic inventory deduction upon sale and addition upon purchase confirmation.
- **Batch-Level Tracking:** Track separate batches, manufacture dates, MRP, PTR, and quantities for every SKU.
- **Stock Adjustments & Reconciliation:** Manually audit and adjust stock quantities when necessary.
- **Low-Stock Alerts:** Automated notifications when stock drops below reorder thresholds.
- **Bulk Import:** Excel/CSV template import for onboarding existing inventory.
- **Catalog Search & Matching:** Fast searching across extensive medicine catalogs.
- **Purchase & Sales Returns:** Complete inventory movement tracking for customer returns and supplier returns.

### Expiry Management
- **Batch-Level Expiry Tracking:** Monitor expiration dates at the individual batch level.
- **Expired Stock Identification:** Instantly isolate expired stock from active sales inventory.
- **Upcoming Expiry Alerts:** Proactive notifications for items expiring within 30, 60, or 90 days.
- **Inventory Value-at-Risk:** Financial visibility into the total monetary value of near-expiry stock.

### Supplier Management
- **Supplier Directory:** Complete contact, GSTIN, and profile management for wholesale suppliers.
- **Supplier Purchase Records:** Detailed invoice history and purchase item logs per supplier.
- **Supplier Credit Ledger:** Track outstanding purchase payables and payment history.
- **Purchase Invoice Intake:** Direct entry and AI-assisted processing of incoming supplier bills.
- **Purchase Returns:** Process return memos for damaged or near-expiry stock sent back to distributors.

### Customer Khata & Payments
- **Customer Directory:** Maintain customer profiles, contact numbers, and purchase history.
- **Customer Khata Ledger:** Digital credit ledger for managing trusted customer balance accounts.
- **Outstanding Payment Tracking:** Real-time visibility into pending receivables per customer.
- **Partial & Full Settlement:** Flexible payment entry for clearing customer balances over time.
- **WhatsApp Reminders:** One-tap dispatch of payment reminders directly via WhatsApp.

### Reports & Documents
- **Sales Analytics:** Daily, weekly, and monthly sales summaries, revenue trends, and payment breakdowns.
- **Inventory Analytics:** Fast-moving vs. slow-moving stock insights and category reports.
- **GST-Compliant Invoicing:** Generate professional PDF tax invoices compliant with Indian GST requirements.
- **CA Connect & Tax Export:** Export structured sales and purchase data (CSV/Excel) formatted for accounting and CA filing.
- **Thermal Receipt Printing:** Native support for ESC/POS thermal printers via direct Bluetooth/USB/Network connections.

### Notifications
- **WhatsApp Payment Reminders:** Quick customer notification dispatch for outstanding Khata accounts.
- **Firebase Push Notifications (FCM):** Real-time mobile push alerts for critical low-stock and expiry warnings.
- **System Alerts:** Dashboard notifications for operational reminders.

### Authentication & Multi-Tenancy
- **Stateless JWT Authentication:** Secure, token-based session management for web and mobile clients.
- **Multi-User Staff Accounts:** Staff account creation with customized operational roles.
- **Role-Based Access Control (RBAC):** Restrict sensitive financial settings and reports based on user permission level.
- **Shop-Level Tenant Isolation:** Application and database authorization strictly scoped by `shop_id` to guarantee total tenant data privacy.

---

## Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | FastAPI (Python) | High-performance asynchronous REST APIs and a Python ecosystem suitable for AI/data processing. |
| **Database** | PostgreSQL + SQLAlchemy | Reliable relational storage for pharmacy, inventory, billing and transaction data with structured ORM-based access. |
| **Web** | React | Responsive dashboard for pharmacy owners/staff and operational management. |
| **Mobile** | Flutter | Cross-platform mobile application for AI camera workflows and pharmacy operations. |
| **AI Engine** | Gemini API — Gemini 3.1 Flash-Lite | Vision/language processing for medicine, invoice and document understanding. |
| **OCR** | PaddleOCR | OCR support for extracting text from supported pharmacy documents/images. |
| **Infrastructure** | Railway | Cloud deployment for backend/database infrastructure. |
| **Web Hosting** | Cloudflare Pages | Deployment and delivery of the web frontend. |
| **Notifications** | Firebase Cloud Messaging | Push notifications to supported mobile devices. |
| **Authentication** | JWT | Stateless authentication for web/mobile clients. |
| **Multi-Tenancy** | `shop_id` Scoped Architecture | Keeps pharmacy data isolated at the application/data-access level. |
| **Printing** | ESC/POS | Supports thermal-printer workflows commonly used in POS environments. |

---

## Architecture Overview

DawaiFlow connects frontend client devices (web dashboard and Flutter mobile app) through a central asynchronous FastAPI backend to PostgreSQL database storage and external AI/notification services.

- **User Devices:** Pharmacists access DawaiFlow via mobile devices (Flutter app for camera workflows) or PCs (React dashboard for desk billing and operations).
- **FastAPI Backend:** Serves REST APIs, validates data schemas via Pydantic, enforces JWT authentication, and scopes database queries by tenant (`shop_id`).
- **PostgreSQL Database:** Safely stores relational models including pharmacy users, inventory batches, sales receipts, supplier invoices, and customer ledgers.
- **AI Vision Pipeline:** Requests containing medicine images or supplier invoices are processed asynchronously via Gemini 3.1 Flash-Lite and PaddleOCR for line-item extraction.
- **ESC/POS Printing:** Formats receipts directly for local thermal printers.

```mermaid
flowchart LR
    U["User Device<br/>Phone / PC"]
    API["FastAPI Backend<br/>Async REST & WebSockets"]
    DB[("PostgreSQL<br/>Pharmacy Data")]
    AI["AI Vision<br/>Gemini 3.1 Flash-Lite<br/>+ OCR"]
    PR["Thermal Printer<br/>ESC/POS"]

    U <--> API
    API <--> DB
    API <--> AI
    API --> PR
```

---

## How It Works

DawaiFlow follows a simple six-stage operational workflow:

### 1. Capture
The pharmacist captures or enters information using phone or PC.
- Photographing a medicine strip or packaging
- Uploading single or multi-page supplier purchase invoices
- Scanning product barcodes
- Searching the catalog manually

### 2. AI Understands
AI vision/OCR models process the document or image to extract structured operational data:
- Medicine names & dosage forms
- Batch numbers & expiry dates
- Quantities, Pack Sizes, MRP, & PTR values
- Supplier invoice header details & GST line item breakdowns

### 3. Verify
The extracted data is presented to the pharmacist in an interactive verification screen. The pharmacist reviews and approves the extracted details before committing the data.

### 4. Process
DawaiFlow executes backend business rules:
- Catalog item matching
- Automatic batch allocation using FEFO (First Expiry, First Out)
- GST and discount calculations
- Stock validation and payment processing

### 5. Update
Upon confirmation, the system atomically updates all relevant database stores:
- Inventory batch balances
- Sales & purchase ledgers
- Customer Khata balances & supplier accounts
- Financial & stock analytics

### 6. Act
The pharmacist completes the operational action:
- Generating and printing a GST-compliant thermal/PDF receipt
- Dispatching a WhatsApp payment reminder
- Updating supplier credit balances
- Exporting tax data for CA review

---

## Project Structure

```
ExpiryGuard_Backend/
├── app.py                   # FastAPI application entry point & middleware configuration
├── dependencies.py          # Centralized auth, DB session, & security dependencies
├── models.py                # SQLAlchemy relational database models
├── schemas.py               # Pydantic data validation & request/response schemas
├── crud.py                  # Database operations & business logic mapping
├── database.py              # PostgreSQL engine connection pool & session setup
├── notification_service.py  # Firebase Cloud Messaging (FCM) push notification engine
├── email_service.py         # SMTP email alert notification service
├── pdf_generator.py         # GST-compliant PDF invoice generation service
├── thermal_formatter.py     # Thermal ESC/POS print string formatting utility
├── requirements.txt         # Python backend dependencies
├── .env.example             # Environment configuration template
│
├── routes/                  # Modular APIRouter domain modules
│   ├── ai_routes.py         # AI Gemini vision & document extraction endpoints
│   ├── auth_routes.py       # Authentication, registration & user session routes
│   ├── customer_routes.py   # Customer Khata ledger & credit settlement routes
│   ├── document_routes.py   # PDF generation, backup/restore & bulk import routes
│   ├── gst_routes.py        # GST status, reminders & CA Connect export routes
│   ├── product_routes.py    # Inventory CRUD, stock search & alert routes
│   ├── purchase_routes.py   # Purchase entry & multi-image invoice intake routes
│   ├── report_routes.py     # Sales analytics, profit reports & CSV data exports
│   ├── sale_routes.py       # POS counter checkout, bill holding & returns routes
│   ├── setting_routes.py    # User profiles, shop settings & preferences routes
│   └── staff_routes.py      # Multi-staff RBAC role management routes
│
├── public_site/             # Web Dashboard & Landing Page (React + Vite)
│   ├── src/                 # React components, pages & state management
│   ├── package.json         # Node.js dependencies & scripts
│   └── vite.config.ts       # Vite build configuration
│
└── flutter/                 # Mobile Companion Application (Flutter SDK)
    ├── lib/                 # Dart UI screens, widgets, controllers & API clients
    └── pubspec.yaml         # Flutter project configuration & dependencies
```

---

## Setup & Installation

### A. Prerequisites
Ensure you have the following installed on your local development system:
- **Python**: Version 3.11 or higher
- **Node.js**: Version 18.0 or higher (with `npm`)
- **Flutter SDK**: Version 3.0 or higher (for mobile app testing)
- **PostgreSQL**: Version 14 or higher (or cloud PostgreSQL instance like Supabase/Neon)
- **Git**

### B. Backend Setup
1. Clone the repository and navigate to the project directory:
   ```bash
   git clone https://github.com/your-username/dawaiflow.git
   cd dawaiflow
   ```

2. Create and activate a Python virtual environment:
   ```bash
   # On macOS/Linux:
   python3 -m venv venv
   source venv/bin/activate

   # On Windows (PowerShell):
   python -m venv venv
   .\venv\Scripts\activate
   ```

3. Install backend dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables (see [Environment Variables](#environment-variables) section below).

5. Start the FastAPI server:
   ```bash
   uvicorn app:app --reload --host 0.0.0.0 --port 8000
   ```
   *Alternative:* You can also launch using `python start_server.py`.
   The API interactive documentation will be available at `http://localhost:8000/docs`.

### C. PostgreSQL Database Setup
Ensure PostgreSQL is running locally or accessible via a remote URI. Set your `DATABASE_URL` in `.env`. FastAPI will automatically initialize the required database tables on startup via SQLAlchemy ORM.

### D. Web Dashboard Setup
1. Navigate to the `public_site` directory:
   ```bash
   cd public_site
   ```

2. Install Node dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm run dev
   ```
   The web dashboard will open at `http://localhost:3000` (or `http://localhost:5173`).

### E. Flutter Mobile Setup
1. Navigate to the `flutter` directory:
   ```bash
   cd flutter
   ```

2. Fetch Flutter package dependencies:
   ```bash
   flutter pub get
   ```

3. Ensure a device or emulator is connected:
   ```bash
   flutter devices
   ```

4. Run the application:
   ```bash
   flutter run
   ```
   *Note: Ensure the mobile app API configuration points to your local backend server IP address (e.g., `http://192.168.x.x:8000`) rather than `localhost` when testing on physical mobile devices.*

### F. Running the Complete System
To run the complete system locally:
1. Start the PostgreSQL service.
2. Launch the FastAPI backend server (`port 8000`).
3. Launch the React web dashboard (`port 3000` / `5173`).
4. Launch the Flutter mobile app on an Android/iOS emulator or connected test device.

---

## Environment Variables

Create a `.env` file in the root directory by copying the provided `.env.example` file:

```bash
cp .env.example .env
```

Fill in the environment variables with your local configuration (placeholders shown below):

```env
# Runtime Environment
ENVIRONMENT=development
PORT=8000

# Database Connection (PostgreSQL)
DATABASE_URL=postgresql://username:password@localhost:5432/dawaiflow

# Cryptographic Security (JWT Signing)
SECRET_KEY=your_secure_random_64_character_hex_key_here

# CORS Allowed Origins
ALLOWED_ORIGINS=http://localhost:8000,http://localhost:3000,http://localhost:5173

# Google Gemini AI Configuration
GEMINI_API_KEY=your_google_ai_studio_gemini_api_key_here
GEMINI_PRIMARY_MODEL=gemini-3.1-flash-lite

# Firebase Cloud Messaging (Push Notifications)
FIREBASE_CREDENTIALS_PATH=credentials/firebase_key.json

# SMTP Email Notifications
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_16_character_app_password
MY_EMAIL=your_personal_receiving_email@gmail.com
SMTP_FROM_NAME="DawaiFlow Alerts"

# Web Dashboard (public_site/.env)
VITE_API_BASE_URL=http://localhost:8000
```

> ⚠️ **SECURITY WARNING:** Never commit real API keys, database passwords, JWT secret keys, Firebase service account credentials, or `.env` files to GitHub or any public source repository. Production AI credentials and service keys must always be secured server-side.

---

## Demo

### Video Demo
[Video Demo Link]

### Live Demo
[Live Demo Link]

---

## Real-World Impact

DawaiFlow is actively being tested through real-world pilot pharmacy workflows to evaluate and refine performance under actual retail operational conditions.

Pilot testing focuses on validating key core workflows in live environments:
- Fast visual medicine strip identification
- Multi-line purchase invoice OCR extraction & intake
- Batch-level stock reconciliation & FEFO verification
- High-speed POS billing and thermal receipt generation
- Expiry risk tracking and inventory value-at-risk monitoring
- Customer Khata balance tracking and WhatsApp payment reminders
- Supplier return and credit ledger management

### Pilot Results

[ADD PILOT PHARMACY / LOCATION IF PUBLIC]

[ADD NUMBER OF BILLS PROCESSED]

[ADD NUMBER OF MEDICINES / TRANSACTIONS TESTED]

[ADD TIME SAVED, IF MEASURED]

[ADD ERROR-REDUCTION / ACCURACY RESULT, IF MEASURED]

[ADD OTHER VERIFIED PILOT METRICS]

---

## Feasibility & Scalability

DawaiFlow is designed to work with devices pharmacies already use, including smartphones, computers and thermal printers. Its cloud-based backend separates core pharmacy operations from individual devices, while modular AI services allow additional capabilities to be added without redesigning the entire platform.

- **Infrastructure Scalability:** Designed to scale seamlessly from a single independent pharmacy to 100+ multi-branch pharmacy accounts.
- **Market Expansion Target:** Targeting deployment across 500+ independent retail pharmacies in the Delhi NCR region within the next 12 months.

---

## Security & Data Isolation

- **Stateless JWT Authentication:** User authentication tokens signed with secret key hashing.
- **Tenant Isolation (`shop_id`):** Every database model and query is explicitly scoped to the user's `shop_id` at the backend data access layer, preventing cross-tenant data access.
- **Role-Based Access Control (RBAC):** Granular permissions for pharmacy owners and staff members.
- **Backend Authorization Enforcement:** Authorization checks enforced on all endpoint requests before executing business operations.
- **Transactional DB Storage:** PostgreSQL ACID transactions ensure financial and inventory operations complete reliably or rollback safely.
- **Environment-Based Secret Management:** All credentials, keys, and database strings are managed through environment variables and strictly excluded from Git.

---

## What's Next / Roadmap

- **Expanded Multi-Branch Support:** Enhanced centralized inventory sharing and stock transfer tracking across multi-store pharmacy chains.
- **Advanced Predictive Analytics:** Machine learning models for demand forecasting and seasonal stocking recommendations.
- **Enhanced AI Vision Models:** Continuous refinement of medicine packaging and handwritten document recognition.
- **Integrations & Automation:** Expanded integration with major accounting suites and distributor EDI portals based on pilot feedback.

---

## Innovate Without Borders

### Hackathon Alignment
DawaiFlow was built for the **Innovate Without Borders** hackathon under the **Healthcare & MedTech** category.

- **Practical AI in Healthcare Operations:** DawaiFlow applies state-of-the-art vision models (Gemini 3.1 Flash-Lite) to solve real, everyday operational bottlenecks in community healthcare access points.
- **Empowering Independent Retail Pharmacies:** Independent pharmacies are vital healthcare touchpoints in India. DawaiFlow brings accessible digital tools to independent operators without requiring expensive dedicated hardware.
- **Bridging Physical & Digital Workflows:** Seamlessly connects physical medicine packages, paper invoices, and thermal printers with modern cloud software.
- **Human-Centric Automation:** Reduces repetitive administrative work around pharmacists while keeping the qualified professional in control of verification and dispensing decisions.

> *"Rather than replacing pharmacists, DawaiFlow is designed to reduce repetitive administrative work around them."*

> **Let pharmacists spend more time serving patients and less time managing software.**

---

## Team

### Team Name
[TEAM NAME]

### Members
- [MEMBER 1 — NAME] — [ROLE]
- [MEMBER 2 — NAME] — [ROLE]
- [MEMBER 3 — NAME] — [ROLE]
- [MEMBER 4 — NAME] — [ROLE]

**Institution:**  
Bharatiya Vidyapeeth College of Engineering, New Delhi

---

## License

[ADD LICENSE HERE]
