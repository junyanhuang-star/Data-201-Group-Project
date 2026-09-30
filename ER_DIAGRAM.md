# 3NF ER/EER diagram

The complete implementation is in `SF_Rent_Board_schema_3nf.sql`. The diagram
below shows the main entities and relationship directions. Lookup tables are
shown separately from the main fact table, and the multi-valued data is modeled
with child/junction tables.

```mermaid
erDiagram
    EXTRACT_BATCH ||--o{ UNIT_RECORD : contains
    FILING_CYCLE ||--o{ UNIT_RECORD : classifies
    OCCUPANCY_TYPE ||--o{ UNIT_RECORD : describes
    BEDROOM_TYPE ||--o{ UNIT_RECORD : describes
    BATHROOM_TYPE ||--o{ UNIT_RECORD : describes
    SQFT_BAND ||--o{ UNIT_RECORD : uses
    RENT_BAND ||--o{ UNIT_RECORD : uses
    LOCATION_POINT ||--o{ UNIT_RECORD : locates
    ASSESSOR_BLOCK ||--o{ UNIT_RECORD : labels
    STREET_BLOCK ||--o{ UNIT_RECORD : labels
    DUPLICATE_GROUP ||--o{ UNIT_RECORD : groups
    DATE_UNKNOWN_REASON ||--o{ UNIT_RECORD : explains
    UNIT_RECORD ||--o{ RECORD_UTILITY_INCLUDED : has
    UTILITY ||--o{ RECORD_UTILITY_INCLUDED : included
    UNIT_RECORD ||--o{ OCCUPANCY_HISTORY : records
    DATE_RANGE_TYPE ||--o{ OCCUPANCY_HISTORY : classifies
    UNIT_RECORD ||--o{ RECORD_QUALITY_FLAG : receives
    QUALITY_FLAG ||--o{ RECORD_QUALITY_FLAG : defines
    NEIGHBORHOOD ||--o{ LOCATION_POINT : identifies
    SUPERVISOR_DISTRICT ||--o{ LOCATION_POINT : identifies

    UNIT_RECORD {
        bigint unique_id PK
        smallint submission_year FK
        tinyint occupancy_type_id FK
        smallint bedroom_type_id FK
        smallint bathroom_type_id FK
        tinyint rent_band_id FK
        tinyint sqft_band_id FK
    }
    LOCATION_POINT {
        int point_id PK
        decimal longitude
        decimal latitude
        tinyint neighborhood_id FK
        tinyint district_id FK
    }
    RECORD_UTILITY_INCLUDED {
        bigint unique_id PK,FK
        tinyint utility_id PK,FK
        boolean from_checkbox
        boolean from_other_text
    }
    OCCUPANCY_HISTORY {
        bigint history_id PK
        bigint unique_id FK
        tinyint seq_no
        date start_date
        date end_date
    }
```

The current local CSV has blank neighborhood and district labels, so those
foreign keys remain nullable when this particular file is loaded.
