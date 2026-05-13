select
  date_format(cast(payout_date as timestamp), '%Y-%m') as invoice_month,
  case
    when partner in ('EngineAPI', 'EngineStatic', 'EngineCC', 'EngineSDK') then 'MoneyLion'
    when partner = 'AmoneAPI' then 'AmONE'
    when partner = 'PBrigit' then 'Brigit'
    when partner = 'Pkashkick' then 'Kashkick'
    when partner = 'PSupermoney' then 'SuperMoney'
    when partner = 'PFreecash' then 'Freecash'
    else partner
  end as partner,
  case
    when partner in ('EngineAPI', 'EngineStatic', 'EngineCC', 'EngineSDK')
         and day(cast(payout_date as timestamp)) <= 15 then 'C1'
    when partner in ('EngineAPI', 'EngineStatic', 'EngineCC', 'EngineSDK')
         and day(cast(payout_date as timestamp)) > 15 then 'C2'
    else 'C1'
  end as cycle,
  sum(payout) as reports_revenue
from iceberg_db.affiliate__affiliate_revenue__entity
group by 1, 2, 3
