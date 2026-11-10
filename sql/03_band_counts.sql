-- Check-ins and check-outs per station-window and time band, timed rows only.

CREATE TABLE band_counts
WITH (format = 'PARQUET', external_location = 's3://__BUCKET__/curated/band_counts/') AS
SELECT
  win,
  location_id,
  station,
  band,
  count_if(is_check_in) AS check_ins,
  count_if(NOT is_check_in) AS check_outs
FROM curated_ridership
WHERE win IS NOT NULL AND NOT date_only
GROUP BY win, location_id, station, band
