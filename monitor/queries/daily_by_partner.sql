select
  date_format(cast(payout_date as timestamp), '%Y-%m-%d') as date,
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
where cast(payout_date as date) >= date_add('day', -60, current_date)
group by 1, 2
order by 1, 2
