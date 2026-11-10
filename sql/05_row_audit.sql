-- Rows removed at each cleaning step, per source file.

CREATE TABLE row_audit
WITH (format = 'PARQUET', external_location = 's3://__BUCKET__/curated/row_audit/') AS
WITH raw_counts AS (
  SELECT
    "$path" AS source_file,
    count(*) AS raw_rows,
    count_if(NULLIF(end_location, '') IS NULL) AS no_station
  FROM raw_ridership
  GROUP BY 1
),
curated_counts AS (
  SELECT
    source_file,
    count_if(date_only) AS date_only,
    count_if(NOT date_only AND win IS NULL) AS timed_outside_windows,
    count_if(NOT date_only AND win IS NOT NULL) AS timed_in_windows,
    count_if(location_id IS NULL) AS unmapped_station
  FROM curated_ridership
  GROUP BY 1
)
SELECT r.source_file, r.raw_rows, r.no_station, c.date_only, c.timed_outside_windows, c.timed_in_windows, c.unmapped_station
FROM raw_counts r
LEFT JOIN curated_counts c ON r.source_file = c.source_file
