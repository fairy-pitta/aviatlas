# table structure summary

## SG Bird Map
---

### Table: `observationsg`

| Column Name         | Data Type      | Constraints                | Description                         |
| ------------------- | -------------- | -------------------------- | ----------------------------------- |
| `id`                | `integer`      | PRIMARY KEY, AUTOINCREMENT | Unique observation record ID        |
| `obs_dt`            | `date`         | NOT NULL                   | Observation date                    |
| `lat`               | `real`         | NOT NULL                   | Latitude                            |
| `lng`               | `real`         | NOT NULL                   | Longitude                           |
| `location_name`     | `varchar(255)` | NULL                       | Name of location (optional)         |
| `location_id`       | `varchar(100)` | NULL                       | Location code (e.g., from eBird)    |
| `obs_valid`         | `bool`         | NOT NULL                   | Whether the observation is valid    |
| `obs_reviewed`      | `bool`         | NOT NULL                   | Whether the observation is reviewed |
| `user_display_name` | `varchar(100)` | NULL                       | Display name of observer            |
| `subnational1_name` | `varchar(100)` | NULL                       | First-level administrative region   |
| `subnational2_name` | `varchar(100)` | NULL                       | Second-level administrative region  |

---

### Table: `observationsgspecies`

| Column Name      | Data Type | Constraints                         | Description                    |
| ---------------- | --------- | ----------------------------------- | ------------------------------ |
| `id`             | `integer` | PRIMARY KEY, AUTOINCREMENT          | Observation-species record ID  |
| `how_many`       | `integer` | NULL                                | Number of individuals observed |
| `observation_id` | `bigint`  | NOT NULL, FK to `observationsg(id)` | Reference to observation       |
| `species_id`     | `bigint`  | NOT NULL, FK to `species(id)`       | Reference to bird species      |

---

### Table: `sgbird`

| Column Name    | Data Type      | Constraints                | Description                     |
| -------------- | -------------- | -------------------------- | ------------------------------- |
| `id`           | `integer`      | PRIMARY KEY, AUTOINCREMENT | Bird species record ID          |
| `species_code` | `varchar(50)`  | NOT NULL, UNIQUE           | Species code (e.g., from eBird) |
| `com_name`     | `varchar(200)` | NOT NULL                   | Common name in English          |
| `sci_name`     | `varchar(200)` | NOT NULL                   | Scientific name                 |

---

# AviGuessr 

### Table: `country`

| Column Name | Data Type      | Constraints                | Description               |
| ----------- | -------------- | -------------------------- | ------------------------- |
| `id`        | `integer`      | PRIMARY KEY, AUTOINCREMENT | Unique ID for the country |
| `code`      | `varchar(10)`  | NOT NULL, UNIQUE           | Country code (e.g., ISO)  |
| `name`      | `varchar(100)` | NOT NULL                   | Country name              |

### Table: `species`

| Column Name     | Data Type          | Constraints                | Description                 |
| --------------- | ------------------ | -------------------------- | --------------------------- |
| `id`            | `integer`          | PRIMARY KEY, AUTOINCREMENT | Unique species ID           |
| `species_code`  | `varchar(20)`      | NOT NULL, UNIQUE           | Species code                |
| `com_name`      | `varchar(200)`     | NOT NULL                   | Common name                 |
| `sci_name`      | `varchar(200)`     | NOT NULL                   | Scientific name             |
| `country_count` | `integer unsigned` | NOT NULL, CHECK (>= 0)     | Number of countries seen in |
| `image_url`     | `varchar(200)`     | NULL                       | Image URL (optional)        |

---

### Table: `species_countries`

| Column Name  | Data Type | Constraints                   | Description |
| ------------ | --------- | ----------------------------- | ----------- |
| `id`         | `integer` | PRIMARY KEY, AUTOINCREMENT    | Record ID   |
| `species_id` | `bigint`  | NOT NULL, FK to `species(id)` | Species ID  |
| `country_id` | `bigint`  | NOT NULL, FK to `country(id)` | Country ID  |

---