CREATE TABLE IF NOT EXISTS dataset_info (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    data_version TEXT NOT NULL CHECK (length(trim(data_version)) > 0),
    is_mock INTEGER NOT NULL CHECK (is_mock = 1),
    notice TEXT NOT NULL CHECK (length(trim(notice)) > 0),
    distance_origin TEXT NOT NULL CHECK (length(trim(distance_origin)) > 0),
    updated_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    name TEXT NOT NULL UNIQUE CHECK (length(trim(name)) > 0),
    type TEXT NOT NULL CHECK (type IN ('restaurant', 'window')),
    location TEXT NOT NULL CHECK (length(trim(location)) > 0),
    avg_price REAL NOT NULL CHECK (avg_price >= 0 AND avg_price < 1000000000
        AND abs(avg_price * 100 - round(avg_price * 100)) < 0.00001),
    business_hours TEXT CHECK (business_hours IS NULL OR
        CASE WHEN json_valid(business_hours) THEN json_type(business_hours) = 'array' ELSE 0 END),
    meal_periods TEXT NOT NULL CHECK (
        CASE WHEN json_valid(meal_periods) THEN json_type(meal_periods) = 'array' ELSE 0 END),
    is_open TEXT NOT NULL CHECK (is_open IN ('TRUE', 'FALSE', 'UNKNOWN')),
    status_source TEXT NOT NULL CHECK (status_source IN ('simulated_explicit', 'simulated_schedule', 'unknown')),
    status_at TEXT,
    distance_m INTEGER NOT NULL CHECK (distance_m >= 0),
    rating REAL NOT NULL CHECK (rating BETWEEN 0 AND 5),
    description TEXT,
    updated_at TEXT NOT NULL,
    CHECK (status_source != 'unknown' OR is_open = 'UNKNOWN'),
    CHECK (status_source != 'simulated_schedule' OR business_hours IS NOT NULL),
    CHECK (is_open = 'UNKNOWN' OR status_at IS NOT NULL)
) STRICT;

CREATE TABLE IF NOT EXISTS dishes (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    price REAL NOT NULL CHECK (price >= 0 AND price < 1000000000
        AND abs(price * 100 - round(price * 100)) < 0.00001),
    cuisine TEXT NOT NULL CHECK (length(trim(cuisine)) > 0),
    taste_tags TEXT NOT NULL CHECK (
        CASE WHEN json_valid(taste_tags) THEN json_type(taste_tags) = 'array' ELSE 0 END),
    dietary_tags TEXT NOT NULL CHECK (
        CASE WHEN json_valid(dietary_tags) THEN json_type(dietary_tags) = 'array' ELSE 0 END),
    ingredients TEXT CHECK (ingredients IS NULL OR
        CASE WHEN json_valid(ingredients) THEN json_type(ingredients) = 'array' ELSE 0 END),
    avoid_tags TEXT CHECK (avoid_tags IS NULL OR
        CASE WHEN json_valid(avoid_tags) THEN json_type(avoid_tags) = 'array' ELSE 0 END),
    allergens TEXT CHECK (allergens IS NULL OR
        CASE WHEN json_valid(allergens) THEN json_type(allergens) = 'array' ELSE 0 END),
    possible_allergens TEXT CHECK (possible_allergens IS NULL OR
        CASE WHEN json_valid(possible_allergens) THEN json_type(possible_allergens) = 'array' ELSE 0 END),
    description TEXT,
    updated_at TEXT NOT NULL,
    UNIQUE (restaurant_id, name)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_dishes_restaurant ON dishes(restaurant_id);
CREATE INDEX IF NOT EXISTS idx_dishes_price ON dishes(price);
CREATE INDEX IF NOT EXISTS idx_restaurants_distance ON restaurants(distance_m);
CREATE INDEX IF NOT EXISTS idx_restaurants_rating ON restaurants(rating);
