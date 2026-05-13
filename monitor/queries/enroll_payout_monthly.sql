select
  date_format(date_trunc('month', cast(first_enrolled_on as timestamp)), '%Y-%m') as enroll_month,
  date_format(date_trunc('month', cast(payout_date as timestamp)), '%Y-%m')       as payout_month,
  case
    when partner = 'AmoneAPI'    then 'AmONE'
    when partner = 'PBrigit'     then 'Brigit'
    when partner = 'Pkashkick'   then 'Kashkick'
    when partner = 'PSupermoney' then 'SuperMoney'
    when partner = 'PFreecash'   then 'Freecash'
    else partner
  end                                          as partner,
  coalesce(imp_source, '(none)')               as imp_source,
  payout_cohort_bucket,
  count(distinct bright_uid)                   as enrolled_users,
  count(distinct api_lead_id)                  as total_leads,
  round(sum(coalesce(payout, 0)), 2)           as total_payout,
  round(avg(coalesce(payout, 0)), 2)           as avg_payout
from iceberg_db.affiliate__revenue_uid_enriched_v0
where first_enrolled_on is not null
  and enrol_status = 'Enrol'
group by 1, 2, 3, 4, 5
order by 1 desc, 2, 3
