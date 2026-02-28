# Remittance Reconciliation Tool

A local desktop tool that automatically matches your daily bank deposit reports against remittance documents from Microsoft 365 email. Everything runs on your own computer — no cloud service, no server, no administrator rights required.

---

## Table of Contents

1. [What This Tool Does](#what-this-tool-does)
2. [System Requirements](#system-requirements)
3. [Step 1 — Download the Project](#step-1--download-the-project)
4. [Step 2 — Run the Setup Script](#step-2--run-the-setup-script)
5. [Step 3 — Launch the App](#step-3--launch-the-app)
6. [Step 4 — Setup Wizard: Welcome](#step-4--setup-wizard-welcome)
7. [Step 5 — Setup Wizard: Microsoft Graph API (Recommended)](#step-5--setup-wizard-microsoft-graph-api-recommended)
   - [5a — Create an Azure App Registration](#5a--create-an-azure-app-registration)
   - [5b — Grant Mail.Read Permission](#5b--grant-mailread-permission)
   - [5c — Enter Credentials in the Wizard](#5c--enter-credentials-in-the-wizard)
   - [5d — Authenticate with Microsoft](#5d--authenticate-with-microsoft)
8. [Step 6 — Setup Wizard: IMAP Fallback](#step-6--setup-wizard-imap-fallback)
   - [6a — If Basic Auth Is Disabled: Create an App Password](#6a--if-basic-auth-is-disabled-create-an-app-password)
9. [Step 7 — Setup Wizard: Folder Watch](#step-7--setup-wizard-folder-watch)
10. [Step 8 — Setup Wizard: Access Priority](#step-8--setup-wizard-access-priority)
11. [Step 9 — Setup Wizard: Create Your First Payor Profile](#step-9--setup-wizard-create-your-first-payor-profile)
12. [Step 10 — Setup Wizard: Complete](#step-10--setup-wizard-complete)
13. [Daily Use: Processing Deposits](#daily-use-processing-deposits)
    - [Prepare Your CSV](#prepare-your-csv)
    - [Upload and Run a Batch](#upload-and-run-a-batch)
    - [Review the Results](#review-the-results)
14. [Understanding the Queues](#understanding-the-queues)
15. [Payor Profiles — Full Reference](#payor-profiles--full-reference)
16. [Email Tier Details](#email-tier-details)
17. [How Matching Works](#how-matching-works)
18. [PDF Output](#pdf-output)
19. [Changing Settings Later](#changing-settings-later)
20. [Troubleshooting](#troubleshooting)

---

## What This Tool Does

Each business day you receive a bank deposit report listing payments received from various payors. Separately, each payor sends a remittance document (email, PDF, or spreadsheet) telling you which invoices each payment covers.

This tool automates the job of connecting the two:

1. You upload a CSV of that day's deposits
2. The tool scans your Microsoft 365 inbox for remittance emails/documents matching each deposit
3. Matched documents are saved as organised PDFs in a local folder
4. Unmatched deposits carry forward into a queue and are retried on every future run
5. Low-confidence matches are held for your review before being saved

Everything is stored on your computer inside the project folder. Nothing is sent to the cloud.

---

## System Requirements

| Requirement | Details |
|---|---|
| **Operating System** | Windows 10/11, macOS 10.15+, or Linux |
| **Python** | Version 3.9 or later ([python.org](https://www.python.org/downloads/)) |
| **Internet access** | Needed only for email scanning; not needed for setup |
| **Microsoft 365 account** | Work or school account with mailbox access |
| **Administrator rights** | **Not required** — everything installs into the project folder |

**Check your Python version:**
```
python --version          (Windows)
python3 --version         (Mac/Linux)
```
If Python is not installed or is below 3.9, download it from [python.org](https://www.python.org/downloads/). On Windows, check "Add Python to PATH" during installation.

**Optional — OCR support:**
If any of your remittance documents are scanned images with no selectable text, install Tesseract:
- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **macOS:** `brew install tesseract`
- **Windows:** Download from [UB Mannheim Tesseract](https://github.com/UB-Mannheim/tesseract/wiki)

The tool works without Tesseract — it will skip OCR and use the PDF text layer directly for most documents.

---

## Step 1 — Download the Project

If you received the project as a ZIP file, extract it to a permanent folder — somewhere you won't accidentally delete it. Suggested locations:

- **Windows:** `C:\Users\YourName\Documents\RemittanceTool\`
- **Mac/Linux:** `~/Documents/RemittanceTool/`

If cloning from Git:
```bash
git clone <repository-url>
cd Autom8
```

The project folder should contain:
```
setup.sh   (Mac/Linux)
setup.bat  (Windows)
run.sh     (Mac/Linux)
run.bat    (Windows)
requirements.txt
app/
templates/
static/
```

---

## Step 2 — Run the Setup Script

This is a **one-time step**. The setup script creates a Python virtual environment inside the project folder and installs all dependencies. It does not touch anything outside the project folder and requires no administrator rights.

### Windows

Double-click **`setup.bat`**, or open Command Prompt in the project folder and run:
```
setup.bat
```

### Mac / Linux

Open Terminal in the project folder and run:
```bash
chmod +x setup.sh run.sh
./setup.sh
```

**What the setup script does:**
1. Verifies Python 3.9+ is available
2. Creates `venv/` (a Python virtual environment) inside the project folder
3. Runs `pip install -r requirements.txt` to install all packages
4. Creates the `data/` folder structure used at runtime
5. Checks whether Tesseract OCR is available (optional)

**Expected output:**
```
=======================================================
  Remittance Reconciliation Tool — Setup
=======================================================

Using Python 3.11.4

Creating virtual environment in ./venv ...
Virtual environment created.

Installing Python dependencies from requirements.txt ...
(This may take a few minutes on first run.)
...
=======================================================
  Setup complete!

  To launch the application:
    ./run.sh
=======================================================
```

If you see errors during `pip install`, the most common cause is a corporate proxy or firewall. Contact your IT team about pip access, or ask them to whitelist pypi.org.

---

## Step 3 — Launch the App

After setup completes, launch the app whenever you want to use it.

### Windows

Double-click **`run.bat`**, or:
```
run.bat
```

### Mac / Linux

```bash
./run.sh
```

**What happens:**
1. The virtual environment is activated
2. Flask starts on `http://localhost:5000`
3. Your default browser opens automatically to the app
4. The terminal window stays open — **do not close it** while using the app

You should see the browser open to the setup wizard on the first run.

> **Note:** The app only listens on `127.0.0.1` (your own computer). It is not accessible from other computers on the network.

---

## Step 4 — Setup Wizard: Welcome

The first time you launch the app, you will see the **Setup Wizard**. It walks through 7 steps and takes approximately 5–10 minutes.

**Step 1** is the welcome screen. It explains what will be configured and lets you know that every step can be skipped and returned to later from **Settings → Re-run Wizard**.

Click **Get Started** to proceed.

---

## Step 5 — Setup Wizard: Microsoft Graph API (Recommended)

The Graph API is the preferred email access method. It connects via OAuth2 (the same sign-in flow used by Microsoft apps) and requires no password to be stored on your computer. Authentication happens once; subsequent runs refresh the token silently.

This requires a free **Azure App Registration** — no paid subscription, no billing required.

---

### 5a — Create an Azure App Registration

1. Open a new browser tab and go to **[portal.azure.com](https://portal.azure.com)**
2. Sign in with your **Microsoft 365 work account** (the same account whose email you want to scan)
3. In the search bar at the top of the page, type `App registrations` and click the result
4. Click **+ New registration**

   ![New registration button is in the top-left of the App registrations page]

5. Fill in the registration form:
   - **Name:** Enter anything descriptive, e.g. `Remittance Tool`
   - **Supported account types:** Select **"Accounts in this organizational directory only (Single tenant)"**
   - **Redirect URI:** Click the dropdown and select **"Public client/native (mobile & desktop)"**, then enter:
     ```
     http://localhost
     ```
6. Click **Register**

You will land on the **Overview** page of your new registration. **Copy two values from this page** — you will need them shortly:

- **Application (client) ID** — looks like `a1b2c3d4-e5f6-7890-abcd-ef1234567890`
- **Directory (tenant) ID** — same UUID format, found just below the client ID

Keep this browser tab open.

---

### 5b — Grant Mail.Read Permission

Still on your App Registration page:

1. Click **API permissions** in the left-hand menu
2. Click **+ Add a permission**
3. In the panel that appears, click **Microsoft Graph**
4. Click **Delegated permissions**
5. In the search box type `Mail.Read`
6. Check the box next to **Mail.Read**
7. Click **Add permissions**

You should now see `Mail.Read` in the permissions list with status "Not granted for [your org]".

**If you are a Global Administrator or an Exchange Administrator:**
- Click **Grant admin consent for [Your Organisation]**
- Click **Yes** to confirm

**If you are not an admin:**
- You can still proceed — you will be prompted to consent for yourself during the sign-in step below
- Alternatively, ask your IT administrator to grant consent on the App Registrations page

---

### 5c — Enter Credentials in the Wizard

Go back to the setup wizard in your other browser tab (Step 2 of the wizard).

1. Paste the **Client ID** you copied from Azure into the **Client ID** field
2. Paste the **Tenant ID** into the **Tenant ID** field

---

### 5d — Authenticate with Microsoft

Click **Test Connection & Authenticate**.

A device-code authentication flow will start:

1. A message will appear in the wizard showing a URL and a short code, for example:
   ```
   To sign in, visit: https://microsoft.com/devicelogin
   Enter code: ABC123DEF
   ```
2. Open a browser tab, go to **[microsoft.com/devicelogin](https://microsoft.com/devicelogin)**
3. Enter the code shown in the wizard
4. Sign in with your Microsoft 365 work account
5. When prompted, click **Accept** to grant the Mail.Read permission

Return to the wizard. If authentication succeeded, you will see:

> ✅ **Connected as Your Name**

If it fails, see the [Troubleshooting](#troubleshooting) section below.

Click **Save & Continue** to proceed to Step 3.

---

## Step 6 — Setup Wizard: IMAP Fallback

IMAP is a standard email protocol used as a backup. If the Graph API is unavailable (token expired, network change, etc.), the tool falls back to IMAP automatically without you needing to do anything.

The IMAP server for Microsoft 365 is `outlook.office365.com:993` (SSL).

1. Enter your **Microsoft 365 email address** (e.g. `you@yourcompany.com`)
2. Enter your **password**

Then click **Test IMAP Connection**. If the test succeeds, you will see a green success message. Click **Save & Continue**.

---

### 6a — If Basic Auth Is Disabled: Create an App Password

Many Microsoft 365 organisations have disabled basic authentication (username + password) for security reasons. If the IMAP test fails with an "authentication failed" error, you need an **App Password** instead.

**To generate a Microsoft 365 App Password:**

1. Go to **[mysignins.microsoft.com/security-info](https://mysignins.microsoft.com/security-info)**
2. Sign in with your work account
3. Click **+ Add sign-in method**
4. Select **App password** from the dropdown
5. Enter a name like `Remittance Tool` and click **Next**
6. Microsoft will show you a generated password — **copy it now** (it's only shown once)
7. Paste this app password into the wizard's **Password** field instead of your regular password

> **Note:** App Passwords require that per-user MFA is enabled on your account. If the App Password option doesn't appear, your admin may have disabled it. In that case, use Graph API only (Step 5) or Folder Watch (Step 7).

If IMAP is completely blocked at the tenant level, the test will show a "connection refused" error with a specific message. In that case, skip this step — Graph API and Folder Watch are still available.

---

## Step 7 — Setup Wizard: Folder Watch

The folder watch is the always-available fallback. It requires no credentials and no network access.

The wizard shows you the path to the watch folder:
```
/path/to/project/data/watch/
```

**How it works:** The app monitors this folder continuously. Any file you drop into it is processed immediately against your pending deposit queue using the same matching logic.

**Supported file types:**
| Type | How it's used |
|---|---|
| `.eml` | Email exported from any client |
| `.msg` | Outlook message format |
| `.pdf` | Remittance PDF |
| `.docx` | Word document remittance |
| `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp` | Scanned remittance images |

**How to export emails from Outlook into the watch folder:**
1. Open the remittance email in Outlook
2. Go to **File → Save As**
3. Navigate to the `data/watch/` folder inside the project
4. Select file type **Outlook Message Format (*.msg)** or **EML**
5. Click **Save**

The file will be picked up and processed within a few seconds.

Click **Got it — Continue** to proceed to Step 5.

---

## Step 8 — Setup Wizard: Access Priority

This step lets you set which email tier to try first.

**Default order:** Graph API → IMAP → Folder Watch

To change the order:
- Click the **↑ / ↓** arrows to reorder tiers
- Use the **Active/Disabled** toggle to disable any tier you don't want to use

The tool tries each active tier in order and stops at the first one that succeeds. If a tier fails, it logs the failure, tries the next one, and displays the active tier on the dashboard.

Click **Save & Continue**.

---

## Step 9 — Setup Wizard: Create Your First Payor Profile

Payor profiles tell the tool how to identify remittances from each of your payors.

Fill in the fields for your first payor:

| Field | What to enter | Why it matters |
|---|---|---|
| **Payor Name** | Exact name as it appears in your deposit CSV | Used to match CSV rows to this profile (fuzzy matching also applied) |
| **Sender Email** | The "from" address on their remittance emails | Highest-confidence sender matching |
| **Sender Domain** | e.g. `acmecorp.com` | Used when the exact address varies but the domain is consistent |
| **Subject Keywords** | e.g. `remittance, EFT payment` | Comma-separated; emails with these subjects are prioritised |
| **What to Save** | Body + attachments / Attachments only / Body only | Which parts of the email to convert to PDF for your records |
| **Email Tier Override** | Usually "Use global settings" | Override the global tier order for this payor if needed |
| **Custom Ref Labels** | e.g. `Payment Voucher, Remit ID` | Additional reference number labels unique to this payor |
| **Manual Only** | Checkbox | Check this to stop automation for this payor entirely |
| **Notes** | Free text | Any quirks or special handling reminders |

After saving:
- Click **Save & Add Another** to add more payors right away
- Click **Save & Continue** to proceed to the final step

You can add and edit payors at any time from the **Payors** menu once the wizard is complete.

---

## Step 10 — Setup Wizard: Complete

The final screen summarises which email tiers are active. Click **Go to Dashboard** to begin using the tool.

The setup wizard can be re-run at any time from **Settings → Re-run Setup Wizard**. Re-running does not delete any of your data.

---

## Daily Use: Processing Deposits

### Prepare Your CSV

Export your previous day's deposit report from your banking portal or accounting system as a CSV file. The tool auto-detects column names, but your CSV must have at minimum:

| Required | Accepted column names (any of these work) |
|---|---|
| Payor name | `Payor`, `Payer`, `Customer`, `Company`, `Name`, `Vendor`, `Client` |
| Amount | `Amount`, `Deposit`, `Total`, `Payment`, `Credit` |

| Optional but helpful | Accepted column names |
|---|---|
| Deposit date | `Date`, `Deposit Date`, `Received`, `Posted`, `Settlement Date` |
| Reference number | `Reference`, `Ref`, `Check`, `Trace`, `Transaction ID`, `Confirmation` |

**Example CSV:**
```csv
Payor,Amount,Date,Reference
Acme Corporation,15250.00,2024-01-15,ACH1234567
Widget Suppliers Inc,8400.50,2024-01-15,CHK00892
Global Logistics LLC,42000.00,2024-01-15,WIRE-20240115-001
```

---

### Upload and Run a Batch

1. From the **Dashboard**, click **Upload CSV**
2. Drag and drop your CSV file onto the upload area, or click to browse
3. Click **Upload & Preview** — the tool parses the file and shows you the deposits
4. On the batch preview page, click **Start Matching**
5. A progress bar shows the real-time status as each deposit is processed
6. When complete, a summary shows matched, pending, review, and manual counts

---

### Review the Results

After a batch run, check each queue from the dashboard or the top navigation:

**Dashboard** — shows:
- Today's match rate (%)
- Pending queue count with the top 10 items
- Items awaiting confidence review
- Manual queue count
- Active email tier
- Recent batch run history
- Per-document extraction log (text layer vs OCR)

**Pending Queue** — deposits not yet matched. Each row shows an age-in-days badge:
- 🟢 Green: fewer than 3 days
- 🟡 Yellow: 3–7 days
- 🔴 Red: more than 7 days

These are re-scanned automatically on every future batch run. No action needed unless you want to manually resolve them.

**Review Queue** — low-confidence matches (Tiers 3–5) waiting for your confirmation:
- Each card shows the deposit details and the matched email side-by-side
- Click **Confirm** to accept the match (PDF saved to output folder)
- Click **Reject** to send the deposit back to the pending queue

**Manual Queue** — deposits from payors flagged as "Manual Only":
- Review them in your own workflow
- Click **Mark Complete** when done

---

## Understanding the Queues

### Why deposits stay in the pending queue

The tool uses a ±7-day window (configurable in Settings) around each deposit date to search for matching remittances. A deposit stays pending if:

- No matching email was found in the window
- The remittance email hasn't arrived yet (common with ACH payments)
- The payor's sender email/domain doesn't match any profile

**The pending queue is re-scanned on every batch run**, looking both backward and forward in email history. As soon as a matching remittance arrives in your inbox (even days later), it will be caught on the next run.

### How the 5 confidence tiers work

| Tier | Logic | Action |
|---|---|---|
| 1 — Exact | Payor name + amount + reference number all match | Auto-saved ✅ |
| 2 — Strong | Payor name + amount match (±1¢ tolerance) | Auto-saved ✅ |
| 3 — Domain + Amount | Sender domain matches payor profile + amount matches | Held for review 👁 |
| 4 — Fuzzy + Amount | Payor name ≥80% fuzzy match + amount within ±$1 | Held for review 👁 |
| 5 — Reference Only | Reference number found in email regardless of payor | Held for review 👁 |

If multiple emails match a single deposit at the same confidence tier, the deposit is flagged for manual review rather than guessing.

---

## Payor Profiles — Full Reference

Profiles are created in the Setup Wizard or at any time from **Payors → New Payor**.

### Field guide

**Payor Name** *(required)*
Must match the name in your deposit CSV. Matching is case-insensitive. Fuzzy matching is applied, so minor spelling differences (e.g. "Acme Corp" vs "Acme Corporation") are usually caught. If a deposit payor name doesn't match any profile, the tool will still attempt matching but with reduced confidence.

**Sender Email**
The exact "from" address on remittance emails from this payor (e.g. `ap@acmecorp.com`). Leave blank if it varies; use Sender Domain instead.

**Sender Domain**
The domain portion of the sender's email (e.g. `acmecorp.com`). Any email from `@acmecorp.com` will match this profile.

**Subject Keywords**
Comma-separated words or phrases that appear in the subject line of remittance emails from this payor. Used to prioritise candidates when multiple emails match.

**What to Save**
- *Email body + attachments* — saves the email body as a page followed by any attachments
- *Attachments only* — saves only the attached PDF/document (ignores the email body)
- *Email body only* — saves only the rendered email body (useful when payors embed remittance details in the email rather than attaching a file)

**Email Tier Override**
- *Use global settings* (default) — follows the order set in Step 5 of the wizard
- *Graph API only* — scan only via the Graph API for this payor
- *IMAP only* — scan only via IMAP
- *Folder Watch only* — only process files manually dropped into the watch folder; no email scanning

**Custom Reference Labels**
Supplements the built-in 30+ synonym list. If this payor uses unusual labels like "Payment Voucher #" or "Remit ID", add them here. Values following these labels will be extracted and compared against the deposit's reference number.

**Manual Only**
When checked, the deposit appears in the Manual Queue on the dashboard but no email scanning is ever attempted. Use this for payors whose remittances always require human review (e.g. complex multi-invoice payments, special formats).

**Notes**
Free text for internal reference — remittance quirks, contact names, special instructions, etc.

---

## Email Tier Details

### Tier 1 — Microsoft Graph API

- Connects via OAuth2 using the Microsoft Authentication Library (MSAL)
- Token is stored in `data/tokens/graph_token.json` (inside the project folder only)
- Silent refresh happens automatically on every run — no re-authentication needed
- If the refresh token expires (typically after 90 days of inactivity), you will be prompted to re-authenticate via device code
- Requires the Mail.Read permission granted during setup

### Tier 2 — IMAP

- Uses Python's built-in `imaplib` — no extra install for the protocol itself
- Password is encrypted using Fernet symmetric encryption (`cryptography` package)
- The encryption key is stored in `data/secret.key` (inside the project folder only)
- Plaintext password is only ever held in memory during a scan; never written to disk
- IMAP server: `outlook.office365.com`, Port `993`, SSL

### Tier 3 — Folder Watch

- A background daemon thread monitors `data/watch/` continuously using `watchdog`
- Files are processed within seconds of being dropped in
- Files already in the folder when the app starts are processed on startup
- The folder watch runs regardless of which tiers are configured — it is always active
- Per-payor profiles can be set to "Folder Watch only" to use this exclusively

---

## How Matching Works

### Reference Number Extraction

When scanning an email or document, the tool searches the full text (body + all attachments) for any of the following labels followed by an alphanumeric value:

```
Reference Number    Ref #           Ref No          Payment Reference
Transaction ID      Transaction #   Trace Number    ACH Trace
Wire Reference      Confirmation #  Confirmation No Check Number
Check #             Check No        EFT Reference   EFT #
Remittance ID       Payment ID      Invoice Number  Invoice #
Voucher Number      Voucher #       Document #      PO Number
Batch #             IMAD            OMAD
... plus any custom labels defined in each payor profile
```

Search is case-insensitive. Values like `REF#: ACH1234567` and `Reference Number: ACH1234567` are both captured.

### Amount Extraction

Dollar amounts are extracted from the full email text using patterns matching:
- `$1,234.56`
- `1,234.56`
- `1234.56`

The extracted amounts are compared against the deposit amount with tolerance:
- Exact match: ±$0.01 (floating-point tolerance)
- Fuzzy match (Tier 4): ±$1.00

### Date Handling

**Date is never a hard filter.** The ±7-day window is only used to narrow the email scan query sent to the mail server (to avoid scanning thousands of old emails). Within the results returned, all emails are evaluated regardless of how far their date is from the deposit date.

Date proximity is only used as a **tiebreaker** between two matches that are otherwise identical in tier and confidence score.

---

## PDF Output

Matched PDFs are saved to: `data/remittances/`

### Folder structure
```
data/
└── remittances/
    └── 2024-01-15/
        ├── 001_2024-01-15_Acme_Corporation_$15250.00.pdf
        ├── 002_2024-01-15_Global_Logistics_$42000.00.pdf
        └── 003_2024-01-15_Widget_Suppliers_$8400.50.pdf
```

- Files are organised into daily subfolders (`YYYY-MM-DD`)
- Within each day, files are sorted **greatest to smallest** by deposit amount
- The numeric prefix (`001_`, `002_`, etc.) ensures correct sort order in file browsers

### Conversion logic
| Source | Method |
|---|---|
| Email body (HTML) | WeasyPrint renders HTML to PDF |
| Email body (plain text) | Wrapped in HTML, rendered by WeasyPrint |
| PDF attachment | Copied as-is |
| DOCX attachment | Text extracted, saved as PDF |
| Image attachment (.png, .jpg, etc.) | Pillow converts to single-page PDF |
| Email body + attachment | Both converted and merged into one PDF |

---

## Changing Settings Later

All settings are accessible from the **Settings** menu in the top navigation.

| What you want to change | Where to go |
|---|---|
| Lookback window (default 7 days) | Settings → General |
| Email tier credentials | Settings → Re-run Wizard → Step 2 or 3 |
| Email tier priority order | Settings → Re-run Wizard → Step 5 |
| Add a new payor | Payors → New Payor |
| Edit an existing payor | Payors → Edit (pencil icon) |
| Re-authenticate with Microsoft | Settings → Re-run Wizard → Step 2 |
| Reset everything | Settings → Re-run Wizard (does not delete data) |

---

## Troubleshooting

### App doesn't start / browser doesn't open

- Make sure the `venv/` folder exists. If not, run setup again.
- Check the terminal window for error messages.
- Try opening `http://localhost:5000` manually in your browser.
- Make sure no other application is using port 5000. If needed, set a different port:
  ```bash
  PORT=5001 ./run.sh
  ```

---

### "Python was not found" during setup

- **Windows:** Ensure Python is installed and "Add Python to PATH" was checked during installation. Try reopening Command Prompt after installing Python.
- **Mac:** Install Python via [python.org](https://www.python.org/downloads/) or Homebrew: `brew install python3`
- **Linux:** `sudo apt install python3 python3-venv` (Ubuntu/Debian)

---

### Graph API — "Could not initiate device code flow"

**Cause:** The Client ID or Tenant ID is incorrect.

**Fix:** Go back to your App Registration in the Azure portal, copy the IDs again carefully (no extra spaces), and re-enter them in the wizard.

---

### Graph API — "AADSTS50011: The redirect URI specified in the request does not match"

**Cause:** The redirect URI in the Azure registration doesn't match.

**Fix:**
1. Go to your App Registration in the Azure portal
2. Click **Authentication** in the left menu
3. Under **Mobile and desktop applications**, add `http://localhost` as a redirect URI
4. Make sure the platform type is **Public client/native**, not **Web**
5. Click **Save**

---

### Graph API — "Insufficient privileges" after authentication

**Cause:** The Mail.Read permission was added but admin consent was not granted.

**Fix (if you're an admin):** Go to App Registration → API permissions → Grant admin consent.

**Fix (if you're not an admin):** Ask your IT administrator to grant consent. Alternatively, ask them to enable "user consent" for Microsoft Graph Mail.Read delegated permissions. You may also be able to consent for yourself during the device-code sign-in flow if user consent is allowed.

---

### IMAP — "Connection refused"

**Cause:** IMAP access is disabled at the Microsoft 365 tenant level.

**Fix options:**
1. Ask your IT administrator to enable IMAP for your mailbox (Exchange Admin Center → Recipients → Mailboxes → select your mailbox → Email apps → enable IMAP)
2. Use Graph API instead (Step 5 of the wizard)
3. Use Folder Watch as your primary method (no IMAP needed)

---

### IMAP — "Authentication failed"

**Cause:** Your regular Microsoft 365 password doesn't work for IMAP (common when MFA is enabled or when the tenant requires modern authentication).

**Fix:** Use an **App Password** instead. See [Step 6a](#6a--if-basic-auth-is-disabled-create-an-app-password) above.

---

### IMAP — Timeout

**Cause:** Port 993 is blocked by your corporate firewall or VPN.

**Fix:** Contact IT to allow outbound TCP connections to `outlook.office365.com:993`. Alternatively, use Graph API (which uses HTTPS/443, typically allowed) or Folder Watch.

---

### PDF files are blank or not generated

**Cause:** WeasyPrint requires certain system libraries (Pango, Cairo).

**Fix (Linux):**
```bash
sudo apt install libpango-1.0-0 libcairo2 libgdk-pixbuf2.0-0
```
**Fix (Mac):**
```bash
brew install pango cairo gdk-pixbuf
```
**Fix (Windows):** WeasyPrint on Windows bundles its dependencies — if it fails, check the terminal for the specific error and search the [WeasyPrint documentation](https://doc.courtbouillon.org/weasyprint/).

If WeasyPrint fails entirely, the tool will still save matches — it just won't generate PDFs. You can retrieve the original emails from your inbox manually.

---

### OCR not working

**Cause:** Tesseract is not installed or not in the system PATH.

**Fix:** Install Tesseract (see [System Requirements](#system-requirements)) and restart the app. The tool works without OCR — it only falls back to OCR when a PDF has no selectable text layer.

---

### Match rate is unexpectedly low

Common causes and fixes:

| Symptom | Likely cause | Fix |
|---|---|---|
| All deposits pending | Email connection failed | Check the active tier badge on the dashboard; re-test in Settings |
| Some payors never matched | Payor profiles missing or wrong sender domain | Review payor profiles; check the sender address of actual remittance emails |
| Amount matches but name doesn't | Payor name in CSV differs from profile | Update the profile name to match the CSV exactly, or check fuzzy threshold |
| PDF remittances not matched | Attachments not being extracted | Check the extraction log on the dashboard for errors |
| Old deposits never matched | Lookback window too short | Settings → Increase lookback days |

---

### "Module not found" errors when starting the app

**Cause:** A package failed to install during setup, or the virtual environment is not activated.

**Fix:** Run setup again:
```bash
./setup.sh    # Mac/Linux
setup.bat     # Windows
```

If a specific package fails to install, try installing it manually:
```bash
source venv/bin/activate          # Mac/Linux
venv\Scripts\activate.bat         # Windows
pip install <package-name>
```

---

*For additional help, check the terminal output when running the app — Flask logs all errors with full stack traces.*
