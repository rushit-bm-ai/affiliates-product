select
  date_format(date_trunc('month', cast(payout_date as timestamp)), '%Y-%m') as month,
  case
    when partner = 'AmoneAPI'    then 'AmONE'
    when partner = 'PBrigit'     then 'Brigit'
    when partner = 'Pkashkick'   then 'Kashkick'
    when partner = 'PSupermoney' then 'SuperMoney'
    when partner = 'PFreecash'   then 'Freecash'
    else partner
  end as partner,
  round(sum(coalesce(payout, 0)), 2) as payout
from iceberg_db.affiliate__affiliate_revenue__entity
where cast(payout_date as date) >= date_add('month', -13, date_trunc('month', current_date))
group by 1, 2
order by 1, 2
