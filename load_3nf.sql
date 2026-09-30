USE RentBoardDB;
SET FOREIGN_KEY_CHECKS = 0;
LOAD DATA LOCAL INFILE 'load/neighborhood.tsv' INTO TABLE `neighborhood`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`neighborhood_id`, `name`);
LOAD DATA LOCAL INFILE 'load/supervisor_district.tsv' INTO TABLE `supervisor_district`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`district_id`);
LOAD DATA LOCAL INFILE 'load/location_point.tsv' INTO TABLE `location_point`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`point_id`, `longitude`, `latitude`, `neighborhood_id`, `district_id`);
LOAD DATA LOCAL INFILE 'load/assessor_block.tsv' INTO TABLE `assessor_block`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`block_num`);
LOAD DATA LOCAL INFILE 'load/street_block.tsv' INTO TABLE `street_block`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`street_block_id`, `raw_label`, `block_range`, `street_name`);
LOAD DATA LOCAL INFILE 'load/bedroom_type.tsv' INTO TABLE `bedroom_type`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`bedroom_type_id`, `raw_label`, `bedrooms`, `is_unparseable`);
LOAD DATA LOCAL INFILE 'load/bathroom_type.tsv' INTO TABLE `bathroom_type`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`bathroom_type_id`, `raw_label`, `bathrooms`, `is_shared`, `is_unparseable`);
LOAD DATA LOCAL INFILE 'load/duplicate_group.tsv' INTO TABLE `duplicate_group`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`dup_group_id`, `content_hash`, `member_count`);
LOAD DATA LOCAL INFILE 'load/unit_record.tsv' INTO TABLE `unit_record`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`unique_id`, `batch_id`, `submission_year`, `signature_date`, `block_num`, `street_block_id`, `point_id`, `building_unit_count`, `year_property_built`, `occupancy_type_id`, `bedroom_type_id`, `bathroom_type_id`, `sqft_band_id`, `rent_band_id`, `occupancy_or_vacancy_date`, `occupancy_or_vacancy_year`, `date_unknown_reason_id`, `occupancy_year_raw`, `vacancy_date`, `past_occupancy`, `other_utilities_raw`, `dup_group_id`);
LOAD DATA LOCAL INFILE 'load/occupancy_history.tsv' INTO TABLE `occupancy_history`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`unique_id`, `seq_no`, `date_range_type_id`, `start_date`, `end_date`);
LOAD DATA LOCAL INFILE 'load/record_utility_included.tsv' INTO TABLE `record_utility_included`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`unique_id`, `utility_id`, `from_checkbox`, `from_other_text`);
LOAD DATA LOCAL INFILE 'load/record_quality_flag.tsv' INTO TABLE `record_quality_flag`
FIELDS TERMINATED BY '\t' ESCAPED BY '\\'
LINES TERMINATED BY '\n'
(`unique_id`, `flag_id`, `rejected_value`);
SET FOREIGN_KEY_CHECKS = 1;
SELECT 'staging complete' AS status, COUNT(*) AS unit_records FROM unit_record;
