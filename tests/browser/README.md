# Browser regression run: Create New Bill grid

`billing_grid_e2e.js` drives the real billing page (real key events, real search and save endpoints) and checks the
spreadsheet behaviour: Party → Product → Batch → Unit → Qty → Disc, dropdown placement, batch rules, validation,
totals, delete, stale search, duplicate save, network failure, printer failure, held bills, keyboard-only bill.

It **saves real bills and takes stock**, so run it only against a TEST pharmacy.

Seed (local SQLite or a test database):

| Medicine | Batches |
|---|---|
| `PARACETAMOL 500` (GST 12 %, 10 per strip) | `PCM-OLD` expired, stock 5 · `PCM-NEAR` 30 days, stock 12, MRP 32 · `PCM-FAR` 400 days, stock 40, MRP 34 |
| `BULK MEDICINE 0000` … `1199` | batch `B0000` … `B1199`, 10 or more in stock, GST 12 % |

Run: open `/web/billing.html` signed in to the test pharmacy, paste the file into the console, then

```js
await runBillingGridE2E()   // -> { total, passed, failed: [] }
```

The pure rules (cell movement, dropdown placement, batch order, quantity/discount checks) have Node unit tests:
`node --test tests/js/*.test.js`.
