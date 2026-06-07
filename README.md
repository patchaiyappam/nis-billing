# NEW INDIAN STEEL — Billing System

A simple billing app for the shop at Aranthangi Road, Thiruchitrambalam.

---

## How to run on Windows 10 / Windows 11

### First-time setup (do this ONCE)
1. Extract this zip to a folder (e.g. `C:\Users\patch\NEW INDIAN STEEL`)
2. Double-click **`INSTALL_WINDOWS10.bat`**
3. Wait for it to install the required libraries (about 1 minute)

### Daily use — pick the right mode
- **Dad uses:** Double-click **`START_SHOP_MODE.bat`** — simple mode with only Bill + Payment screens, large fonts
- **Patchaiyappan uses:** Double-click **`START_ADMIN_MODE.bat`** — full mode with all features (asks for PIN: `1216`)

---

## If Python is not installed
Download from: https://www.python.org/downloads/

**Important:** During install, tick **"Add Python to PATH"**

---

## Update your shop details
Open `config.py` and fill in:
```
SHOP_ADDRESS = "Aranthangi Road, Thiruchitrambalam - 614628"
SHOP_PHONE   = "+91 6380903276 / +91 9047312666"
SHOP_GSTIN   = ""   # NIS has no GSTIN — all bills are labelled "ESTIMATE"
```

---

## Your data is saved at
`C:\Users\<your name>\Documents\NEW_INDIAN_STEEL\`
- `billing.db` — all your customers, invoices, payments
- `invoices\` — all generated PDF estimates
- `exports\` — Excel exports
- `backups\` — automatic daily backups

---

## What's new in this version
1. **PDF redesigned** — clean "ESTIMATE" header, no row shading, tight right-aligned summary
2. **Manual Old Balance** — edit a customer's previous-due directly on the bill
3. **NIL Balance** button moved to the bottom of the bill summary, where it belongs
4. Removed clutter — only the three .bat files you actually need
