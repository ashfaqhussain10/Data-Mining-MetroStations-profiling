-- Cleans the raw taps, maps stations, and writes partitioned Parquet.
-- Keeps every row with a station, including date-only rows. No rows are de-duplicated.
-- Athena allows 100 partitions per query, so 2017-2021 and 2022-2026 load separately.

CREATE OR REPLACE VIEW v_clean AS
WITH taps AS (
  SELECT
    "$path" AS source_file,
    NULLIF(end_location, '') AS end_location,
    NULLIF(start_location, '') AS start_location,
    NULLIF(line_name, '') AS line_name,
    regexp_replace(trim(replace(end_location, ' Metro Station', '')), '\s+', ' ') AS raw_name,
    CAST(txn_date AS date) AS txn_date,
    txn_time,
    txn_type,
    load_timestamp,
    txn_time LIKE '00:00:00%' AS date_only,
    CAST(substr(txn_time, 1, 2) AS integer) AS hour_of_day,
    substr(txn_date, 1, 7) AS year_month
  FROM raw_ridership
),
station_map AS (
  SELECT raw_name, line_name, CAST(location_id AS integer) AS location_id, station
  FROM ref_station_map
),
name_only AS (
  SELECT raw_name, min(location_id) AS location_id, min(station) AS station
  FROM station_map
  GROUP BY raw_name
  HAVING count(DISTINCT location_id) = 1
)
SELECT
  t.source_file,
  t.txn_date,
  t.txn_time,
  t.txn_type,
  t.txn_type = 'Check in' AS is_check_in,
  t.end_location,
  t.start_location,
  t.line_name,
  t.load_timestamp,
  coalesce(m.location_id, f.location_id) AS location_id,
  coalesce(m.station, f.station) AS station,
  t.date_only,
  t.hour_of_day,
  CASE
    WHEN t.date_only THEN NULL
    WHEN t.hour_of_day < 7 THEN '00-07'
    WHEN t.hour_of_day < 10 THEN '07-10'
    WHEN t.hour_of_day < 16 THEN '10-16'
    WHEN t.hour_of_day < 20 THEN '16-20'
    ELSE '20-24'
  END AS band,
  CASE
    WHEN t.year_month BETWEEN '2017-11' AND '2018-02' THEN 'W17/18'
    WHEN t.year_month BETWEEN '2018-09' AND '2019-02' THEN 'W18/19'
    WHEN t.year_month BETWEEN '2019-09' AND '2020-02' THEN 'W19/20'
    WHEN t.year_month BETWEEN '2021-09' AND '2022-02' THEN 'W21/22'
    WHEN t.year_month BETWEEN '2024-09' AND '2025-02' THEN 'W24/25'
  END AS win,
  CASE
    WHEN t.txn_date < DATE '2022-01-01' THEN day_of_week(t.txn_date) IN (5, 6)
    ELSE day_of_week(t.txn_date) IN (6, 7)
  END AS is_weekend,
  substr(t.year_month, 1, 4) AS year,
  substr(t.year_month, 6, 2) AS month
FROM taps t
LEFT JOIN station_map m
  ON t.raw_name = m.raw_name AND coalesce(t.line_name, '') = coalesce(m.line_name, '')
LEFT JOIN name_only f
  ON t.raw_name = f.raw_name
WHERE t.end_location IS NOT NULL
;
CREATE TABLE curated_ridership
WITH (
  format = 'PARQUET',
  write_compression = 'SNAPPY',
  external_location = 's3://__BUCKET__/curated/ridership/',
  partitioned_by = ARRAY['year', 'month']
) AS
SELECT * FROM v_clean WHERE year <= '2021'
;
INSERT INTO curated_ridership
SELECT * FROM v_clean WHERE year > '2021'
