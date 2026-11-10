-- One row per station-window, flagged against the 300-tap minimum.

CREATE TABLE station_window_totals
WITH (format = 'PARQUET', external_location = 's3://__BUCKET__/curated/station_window_totals/') AS
SELECT
  win,
  location_id,
  station,
  count(*) AS timed_taps,
  count_if(is_check_in) AS check_ins,
  count_if(NOT is_check_in) AS check_outs,
  count_if(is_weekend) AS weekend_taps,
  count(*) >= 300 AS passes_minimum
FROM curated_ridership
WHERE win IS NOT NULL AND NOT date_only
GROUP BY win, location_id, station
