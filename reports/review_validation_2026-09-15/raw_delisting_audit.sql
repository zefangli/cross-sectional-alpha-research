-- Read-only reproduction of the follow-up review's raw-data evidence.
-- Run with DuckDB from the repository root. Full raw scans can take minutes.
-- The temporary tables live only in the DuckDB session.
SELECT DlyDelFlg, COUNT(*) AS rows
FROM read_csv('crsp/yb8xejbnpiflaprb.csv', header=true, all_varchar=true)
GROUP BY 1;

CREATE TEMP TABLE review_delists AS
SELECT TRY_CAST(PERMNO AS BIGINT) AS permno,
       TRY_CAST(DlyCalDt AS DATE) AS date,
       TRY_CAST(DlyRet AS DOUBLE) AS ret,
       TRY_CAST(SecInfoStartDt AS DATE) AS start_date,
       TRY_CAST(SecInfoEndDt AS DATE) AS end_date,
       USIncFlg, SecurityType, SecuritySubType, ShareType, TradingStatusFlg
FROM read_csv('crsp/yb8xejbnpiflaprb.csv', header=true, all_varchar=true)
WHERE DlyDelFlg = 'Y';

SELECT COUNT(*) AS raw_event_rows,
       COUNT(*) FILTER (date BETWEEN start_date AND end_date) AS interval_valid,
       COUNT(*) FILTER (USIncFlg='Y' AND SecurityType='EQTY'
                        AND SecuritySubType='COM' AND ShareType='NS') AS common_share_identity,
       COUNT(*) FILTER (ret IS NOT NULL) AS with_return
FROM review_delists;

CREATE TEMP TABLE review_eligible_ids AS
SELECT DISTINCT permno
FROM read_parquet('data/processed/factor_panel/**/*.parquet')
WHERE aligned AND date < DATE '2024-01-01';

SELECT COUNT(*) AS distinct_event_records,
       COUNT(*) FILTER (ret IS NOT NULL) AS with_return
FROM (
    SELECT DISTINCT permno, date, ret
    FROM review_delists JOIN review_eligible_ids USING (permno)
    WHERE date BETWEEN DATE '2005-01-01' AND DATE '2023-12-31'
);

-- A concrete event missing from the cleaned panel but relevant to the book.
SELECT DISTINCT * FROM review_delists
WHERE permno=80621 AND date=DATE '2014-02-03';

SELECT permno, date, ret, delisting_flag
FROM read_parquet('data/processed/crsp_daily_panel/**/*.parquet')
WHERE permno=80621 AND date BETWEEN DATE '2014-01-29' AND DATE '2014-02-04'
ORDER BY date;
