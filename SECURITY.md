# Security Policy

## Reporting

Please report suspected vulnerabilities privately to the repository owner rather than
opening a public issue. Include the affected file, a reproduction, and any relevant
logs with tokens and personal data removed.

## Secrets and Personal Data

The following files are intentionally excluded from git:

- `config/candidate_profile.json`
- `config/master_profile.yaml`
- `config/comprehensive_portfolio.json`
- `config/private/`
- `data/opportunities.db` and its backups
- `data/dashboard_token.txt`
- generated CVs, screenshots, dashboards, and logs

If any of these were ever committed or shared, treat their contents as exposed:

1. Rotate the Telegram bot token with @BotFather.
2. Replace the dashboard token (`DASHBOARD_AUTH_TOKEN` or `data/dashboard_token.txt`).
3. Change any leaked personal identifiers where the receiving organization allows it.
4. Purge the file from git history before publishing the repository again.

## Runtime Data Isolation

`paths.py` resolves every runtime location from `ZCO_DATA_DIR` and `ZCO_CONFIG_DIR`
(defaults: `data/` and `config/`). Tests point both at a throwaway directory before
any module is imported, so a test run cannot migrate the production database or
overwrite a private profile.

Portfolio snapshots, memory-vault mirrors, the dashboard token, and supervisor state
are written through `file_utils.atomic_write_*`: a sibling temp file is fsynced, set to
mode `0600`, and atomically renamed over the destination. Unreadable portfolio JSON is
preserved as `comprehensive_portfolio.json.corrupt-<UTC timestamp>` before the file is
reinitialized.

## Authentication Model

- **Web dashboard:** every route except `/healthz` and `/favicon.ico` requires a valid
  session cookie or `X-Dashboard-Token` header. The token is generated on first start
  and stored in `data/dashboard_token.txt` with mode `0600`, unless
  `DASHBOARD_AUTH_TOKEN` is set. Mutating requests are same-origin checked.
- **Telegram bot:** every command and callback is denied unless the chat ID appears in
  `TELEGRAM_ADMIN_CHAT_IDS`. The bot exits at startup when the allow-list is empty.
  Scraped text is HTML-escaped and bot tokens are redacted from logs.

## Application Submission Safety

- Batch audits prepare drafts (`READY_FOR_REVIEW`) and do not click Submit by default.
- Unattended submission requires `ZCO_AUTO_SUBMIT=1` or the `--auto-submit` flag.
- `APPLIED_AUTOMATICALLY` requires a captured confirmation reference.
- A clicked-but-unconfirmed submission is `SUBMITTED_UNCONFIRMED`, never a success.
- CV compile failures block submission and record `APPLICATION_FAILED`.
- When funding terms were not verified, coverage displays as unknown rather than as a
  fabricated "100% covered" claim.

Legacy synthetic receipts (including local testbed fixtures) can be reviewed and downgraded with:

```bash
python scripts/quarantine_unverified_submissions.py          # dry run
python scripts/quarantine_unverified_submissions.py --apply  # mutate database
```

## Data Provenance

Each opportunity stores `source_type`, `source_confidence`, `deadline_confidence`, and
`provenance_json`. Local testbed fixtures and legacy rows with unknown deadlines are
scored low on purpose. The dashboard and Telegram cards show these scores so a human
can verify the source before applying. Schema upgrades are versioned in
`schema_migrations` and are additive.
