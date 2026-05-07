# Query → Table Mapping

| Query file | Source table | Dimensions | Used in |
|---|---|---|---|
| `daily_by_partner.sql` | `iceberg_db.affiliate__affiliate_revenue__entity` | payout_date (daily), partner | Monitor → Payouts: Day-on-Day chart + heatmap |
| `weekly_by_partner.sql` | `iceberg_db.affiliate__affiliate_revenue__entity` | payout_date (weekly), partner | Monitor → Payouts: Week-on-Week chart |
| `monthly_by_partner.sql` | `iceberg_db.affiliate__affiliate_revenue__entity` | payout_date (monthly), partner | Monitor → Payouts: Month-on-Month chart + table |
| `reports_by_payout_cycle.sql` | `iceberg_db.affiliate__affiliate_revenue__entity` | payout_date (monthly), partner, cycle (C1/C2) | Recon → Reports vs Invoice |
| `enroll_payout_monthly.sql` | `iceberg_db.affiliate__revenue_uid_enriched_v0` | enroll_month, payout_month, partner, imp_source, payout_cohort_bucket | Monitor → Enrolls |

## Table notes

### `iceberg_db.affiliate__affiliate_revenue__entity`
Payout-level ledger — one row per payout event. Used for all revenue/payout monitoring and reconciliation.
Key columns: `payout_date`, `partner`, `payout`, `cycle`

### `iceberg_db.affiliate__revenue_uid_enriched_v0`
User-level enriched table — one row per uid × payout event. Adds enroll metadata to each payout record.
Key columns: `bright_uid`, `first_enrolled_on`, `payout_date`, `partner`, `imp_source`, `payout_cohort_bucket`, `enrol_status`, `payout`
