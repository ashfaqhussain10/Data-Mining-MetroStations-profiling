-- Raw CSVs as Athena tables. Every column is text, and nothing is converted here.
-- Statements are separated by a line holding only a semicolon.

CREATE EXTERNAL TABLE IF NOT EXISTS raw_ridership (
  end_location string,
  end_zone string,
  line_name string,
  start_location string,
  start_zone string,
  txn_date string,
  txn_time string,
  txn_type string,
  load_timestamp string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
STORED AS TEXTFILE
LOCATION 's3://__BUCKET__/raw/ridership/'
TBLPROPERTIES ('skip.header.line.count' = '1')
;
CREATE EXTERNAL TABLE IF NOT EXISTS raw_stations (
  line_name string,
  location_id string,
  location_name_arabic string,
  location_name_english string,
  station_closing_date string,
  station_location_latitude string,
  station_location_longitude string,
  station_opening_date string,
  zone_id string,
  load_timestamp string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
STORED AS TEXTFILE
LOCATION 's3://__BUCKET__/raw/stations/'
TBLPROPERTIES ('skip.header.line.count' = '1')
;
CREATE EXTERNAL TABLE IF NOT EXISTS raw_lines (
  line_description string,
  line_name string,
  load_timestamp string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
STORED AS TEXTFILE
LOCATION 's3://__BUCKET__/raw/lines/'
TBLPROPERTIES ('skip.header.line.count' = '1')
;
CREATE EXTERNAL TABLE IF NOT EXISTS ref_station_map (
  raw_name string,
  line_name string,
  n_rows string,
  first_seen string,
  last_seen string,
  location_id string,
  station string,
  match_type string
)
ROW FORMAT SERDE 'org.apache.hadoop.hive.serde2.OpenCSVSerde'
STORED AS TEXTFILE
LOCATION 's3://__BUCKET__/reference/station_map/'
TBLPROPERTIES ('skip.header.line.count' = '1')
