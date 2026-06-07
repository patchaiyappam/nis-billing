# NIS Billing — End-to-End Test Checklist

Two-part test. Run the **automated** test first to verify the data layer; then walk the **manual GUI** checklist to verify the parts a script can't cover (printer, WhatsApp, screen layout).

---

## Part 1 — Automated test (5 minutes, no risk)

Open Command Prompt in the `NIS_final` folder and run:

```
python TEST_END_TO_END.py
```

The script copies your live database to `~/Documents/NEW_INDIAN_STEEL_TEST/` and runs the same `create_invoice_atomic()` call the GUI makes. Your real DB, real invoices folder, Supabase, and WhatsApp are all untouched.

Expect to see:

- A line for each step (A through E)
- The customer-due delta confirming it increased by exactly the invoice balance
- A PDF that opens in your default viewer
- A final line that says **PASS** — end-to-end workflow is healthy

If you see **FAIL** anywhere, copy the output and paste it back to me.

After the test, you can delete `~/Documents/NEW_INDIAN_STEEL_TEST/` — it's just the sandbox copy.

---

## Part 2 — Manual GUI test (Admin Mode on your laptop)

Run `START_ADMIN_MODE.bat`. Pick a customer you don't mind having a real invoice against (or create a test customer with phone `9999999999` first).

### Customer + items

- [ ] Open **Billing** screen
- [ ] Type 3 letters of a customer name — autocomplete suggests matches
- [ ] Pick a customer — name, phone, address auto-fill
- [ ] **Old Balance** field shows the customer's current due (or 0)
- [ ] Type 3 letters of a product — autocomplete suggests matches
- [ ] Add 2 different products with quantity > 1
- [ ] Item table shows each row with qty × price = amount

### Totals + balance

- [ ] Enter Transport = 100, Discount = 5%
- [ ] Subtotal, discount, transport, grand total all update live
- [ ] Enter a partial Paid amount (e.g. half the grand total)
- [ ] **Net Balance** = Old Balance + (Grand Total − Paid)
- [ ] Click **NIL Balance** button — Paid auto-fills to clear everything; Net Balance becomes 0
- [ ] Type a manual value into Old Balance — Net Balance recalculates correctly

### Generate bill

- [ ] Click **Generate Bill**
- [ ] Success dialog appears within ~2 seconds (no UI freeze)
- [ ] PDF opens automatically in the default viewer
- [ ] PDF header says **ESTIMATE**, logo + shop info correct
- [ ] Summary block on the right side: no grey shading, right-aligned
- [ ] Old Balance row and Net Balance row both present
- [ ] No tax / GSTIN columns

### Printer (shop printer or your laptop printer)

- [ ] Within ~5 seconds of clicking Generate Bill, the printer starts
- [ ] Printed page matches the PDF (alignment, fonts, no clipping)

### WhatsApp

- [ ] WhatsApp Web opens to the customer chat
- [ ] Pre-filled message has: customer name, invoice number, total, paid, balance
- [ ] (If Supabase upload finished) message also contains the PDF link
- [ ] Click Send — message delivered

### After saving

- [ ] Go to **Customers** — that customer's due updated correctly
- [ ] Go to **History** — the new invoice is at the top with correct totals
- [ ] Click the invoice row — opens the PDF again with no errors

### Edge cases (do at least 2)

- [ ] Create an invoice with a **brand new customer** (phone not in DB) — should auto-create the customer
- [ ] Create a **quotation** instead of invoice — PDF should say ESTIMATE but customer due should NOT change
- [ ] Create an invoice for a customer with existing old balance — old balance pulls in automatically
- [ ] Try to generate a bill with no line items — should show a friendly error, not crash

---

## What to do with the results

If everything passes: you're cleared to install on the shop PC and train Dad on Shop Mode.

If anything fails, note the exact step number and what you saw vs. expected. Then come back and tell me — I'll fix it before you install on the shop PC.
