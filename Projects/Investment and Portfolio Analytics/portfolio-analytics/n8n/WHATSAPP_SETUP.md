# n8n workflow and WhatsApp setup

`workflow.json` runs at 08:00 Tue-Sat (Africa/Nairobi): ingest prices into SQLite, and on
Saturdays also refresh the analysis and send a weekly summary to WhatsApp.
The Saturday run covers Mon-Fri after every market (NSE, US, crypto) has closed.

```
Schedule -> Config -> Ingest Prices -> Is Saturday? -(yes)-> Run Analysis -> Weekly Summary
                                                          -> Build WhatsApp Message -> Send WhatsApp
```

## 1. Before importing

- **Execute Command node:** the workflow runs your Python code through it. It only works on a
  self-hosted n8n, on the machine that holds this project. Some versions disable the node by
  default; if it is missing, re-enable it in n8n's node-exclusion setting (NODES_EXCLUDE).
- **Python:** `pip install -r requirements.txt` on that machine. On Windows set `python` to `python`.
- **Data:** run `python -m analytics.ingest` once by hand first, and put NSE CSVs in `data/nse/`.
  NSE data is CSV-based, so refresh those files regularly. If they go stale, the summary says
  "STALE" in its last field instead of reporting old data as current.

## 2. WhatsApp Cloud API (Meta)

WhatsApp only lets a business message someone first with a pre-approved **template**, which
is why the workflow sends a template instead of free text.

1. In Meta for Developers, create an app and add the **WhatsApp** product. Note the
   **Phone number ID** (not the phone number itself).
2. Add your own number as a recipient. A test number can only message numbers you have verified.
3. In WhatsApp Manager > Message templates, create this template and wait for approval:
   - Name: `weekly_portfolio_summary`   Language: English   Category: Utility (Meta makes the final call)
   - Body:
     ```
     Weekly portfolio summary for {{1}}. Equal-weight portfolio: {{2}} this week. Benchmark: {{3}}. Best performer: {{4}}. Worst performer: {{5}}. Current drawdown: {{6}}. Data last updated: {{7}}. Historical figures only, not a forecast or investment advice.
     ```
   - Sample values for review: `2026-10-05 to 2026-10-09`, `+1.2%`, `SPY +0.8%`, `SCOM +3.1%`, `KCB -2.0%`, `4.5% below peak`, `2026-10-09`
4. Create a **System User** access token with WhatsApp messaging permission. The temporary
   token on the dashboard expires after about 24 hours, so it is only good for a first test.
5. Meta may charge per template message. Check current pricing before scheduling this.

## 3. In n8n

1. Import `workflow.json`.
2. Create a credential of type **Header Auth**: name `Authorization`, value `Bearer <your token>`.
   Select it on the **Send WhatsApp** node.
3. Open the **Config** node and set: `projectDir`, `python`, `phoneNumberId`, `recipient`
   (country code, digits only, e.g. `2547...`), and `riskFreeRate`. Check that `graphVersion`
   is still a supported Graph API version.
4. Test in this order: execute **Ingest Prices**, then **Weekly Summary** (check the JSON),
   then **Send WhatsApp** once. The weekly branch only runs on Saturdays, so test it with
   "Execute step" on each node.
5. Activate the workflow. In workflow settings, set an Error Workflow so failures notify you.

## Notes

- Not tested against a live n8n instance or the live WhatsApp API: I validated the JSON structure,
  the Python commands and the Code node logic offline. Expect to re-select the credential and
  possibly adjust a node field if your n8n version differs.
- The summary is historical and the template says so. Keep that wording when you edit it.
