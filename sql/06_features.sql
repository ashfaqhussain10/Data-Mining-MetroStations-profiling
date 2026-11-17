-- The 17 features per station-window, built from band_counts and station_window_totals.
-- features_unscaled keeps the readable values; features holds the z-scored model input.
-- volume_share is computed over every station-window in a window, before the 300-tap
-- minimum removes rows, matching src/build_features.py.

CREATE TABLE features_unscaled
WITH (format = 'PARQUET', external_location = 's3://__BUCKET__/curated/features_unscaled/') AS
WITH totals AS (
  SELECT
    win, location_id, station, timed_taps, check_ins, check_outs, passes_minimum,
    CAST(weekend_taps AS double) / timed_taps AS weekend_share,
    CAST(timed_taps AS double) / sum(timed_taps) OVER (PARTITION BY win) AS volume_share
  FROM station_window_totals
),
bands AS (
  SELECT
    win, location_id,
    CAST(sum(CASE WHEN band = '00-07' THEN check_ins ELSE 0 END) AS double) AS ci_00_07,
    CAST(sum(CASE WHEN band = '07-10' THEN check_ins ELSE 0 END) AS double) AS ci_07_10,
    CAST(sum(CASE WHEN band = '10-16' THEN check_ins ELSE 0 END) AS double) AS ci_10_16,
    CAST(sum(CASE WHEN band = '16-20' THEN check_ins ELSE 0 END) AS double) AS ci_16_20,
    CAST(sum(CASE WHEN band = '20-24' THEN check_ins ELSE 0 END) AS double) AS ci_20_24,
    CAST(sum(CASE WHEN band = '00-07' THEN check_outs ELSE 0 END) AS double) AS co_00_07,
    CAST(sum(CASE WHEN band = '07-10' THEN check_outs ELSE 0 END) AS double) AS co_07_10,
    CAST(sum(CASE WHEN band = '10-16' THEN check_outs ELSE 0 END) AS double) AS co_10_16,
    CAST(sum(CASE WHEN band = '16-20' THEN check_outs ELSE 0 END) AS double) AS co_16_20,
    CAST(sum(CASE WHEN band = '20-24' THEN check_outs ELSE 0 END) AS double) AS co_20_24
  FROM band_counts
  GROUP BY win, location_id
)
SELECT
  t.win, t.location_id, t.station, t.timed_taps, t.check_ins, t.check_outs,
  b.ci_00_07 / t.check_ins AS check_in_share_00_07,
  b.ci_07_10 / t.check_ins AS check_in_share_07_10,
  b.ci_10_16 / t.check_ins AS check_in_share_10_16,
  b.ci_16_20 / t.check_ins AS check_in_share_16_20,
  b.ci_20_24 / t.check_ins AS check_in_share_20_24,
  b.co_00_07 / t.check_outs AS check_out_share_00_07,
  b.co_07_10 / t.check_outs AS check_out_share_07_10,
  b.co_10_16 / t.check_outs AS check_out_share_10_16,
  b.co_16_20 / t.check_outs AS check_out_share_16_20,
  b.co_20_24 / t.check_outs AS check_out_share_20_24,
  (b.ci_00_07 - b.co_00_07) / (b.ci_00_07 + b.co_00_07) AS net_flow_00_07,
  (b.ci_07_10 - b.co_07_10) / (b.ci_07_10 + b.co_07_10) AS net_flow_07_10,
  (b.ci_10_16 - b.co_10_16) / (b.ci_10_16 + b.co_10_16) AS net_flow_10_16,
  (b.ci_16_20 - b.co_16_20) / (b.ci_16_20 + b.co_16_20) AS net_flow_16_20,
  (b.ci_20_24 - b.co_20_24) / (b.ci_20_24 + b.co_20_24) AS net_flow_20_24,
  t.weekend_share,
  t.volume_share
FROM totals t
JOIN bands b ON t.win = b.win AND t.location_id = b.location_id
WHERE t.passes_minimum
;
CREATE TABLE features
WITH (format = 'PARQUET', external_location = 's3://__BUCKET__/curated/features/') AS
SELECT
  win, location_id, station, timed_taps, check_ins, check_outs,
  (check_in_share_00_07 - avg(check_in_share_00_07) OVER ()) / stddev_pop(check_in_share_00_07) OVER () AS check_in_share_00_07,
  (check_in_share_07_10 - avg(check_in_share_07_10) OVER ()) / stddev_pop(check_in_share_07_10) OVER () AS check_in_share_07_10,
  (check_in_share_10_16 - avg(check_in_share_10_16) OVER ()) / stddev_pop(check_in_share_10_16) OVER () AS check_in_share_10_16,
  (check_in_share_16_20 - avg(check_in_share_16_20) OVER ()) / stddev_pop(check_in_share_16_20) OVER () AS check_in_share_16_20,
  (check_in_share_20_24 - avg(check_in_share_20_24) OVER ()) / stddev_pop(check_in_share_20_24) OVER () AS check_in_share_20_24,
  (check_out_share_00_07 - avg(check_out_share_00_07) OVER ()) / stddev_pop(check_out_share_00_07) OVER () AS check_out_share_00_07,
  (check_out_share_07_10 - avg(check_out_share_07_10) OVER ()) / stddev_pop(check_out_share_07_10) OVER () AS check_out_share_07_10,
  (check_out_share_10_16 - avg(check_out_share_10_16) OVER ()) / stddev_pop(check_out_share_10_16) OVER () AS check_out_share_10_16,
  (check_out_share_16_20 - avg(check_out_share_16_20) OVER ()) / stddev_pop(check_out_share_16_20) OVER () AS check_out_share_16_20,
  (check_out_share_20_24 - avg(check_out_share_20_24) OVER ()) / stddev_pop(check_out_share_20_24) OVER () AS check_out_share_20_24,
  (net_flow_00_07 - avg(net_flow_00_07) OVER ()) / stddev_pop(net_flow_00_07) OVER () AS net_flow_00_07,
  (net_flow_07_10 - avg(net_flow_07_10) OVER ()) / stddev_pop(net_flow_07_10) OVER () AS net_flow_07_10,
  (net_flow_10_16 - avg(net_flow_10_16) OVER ()) / stddev_pop(net_flow_10_16) OVER () AS net_flow_10_16,
  (net_flow_16_20 - avg(net_flow_16_20) OVER ()) / stddev_pop(net_flow_16_20) OVER () AS net_flow_16_20,
  (net_flow_20_24 - avg(net_flow_20_24) OVER ()) / stddev_pop(net_flow_20_24) OVER () AS net_flow_20_24,
  (weekend_share - avg(weekend_share) OVER ()) / stddev_pop(weekend_share) OVER () AS weekend_share,
  (volume_share - avg(volume_share) OVER ()) / stddev_pop(volume_share) OVER () AS volume_share
FROM features_unscaled
