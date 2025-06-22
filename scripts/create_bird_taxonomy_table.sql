-- Bird Taxonomy Table Creation Script for Supabase
-- Run this in your Supabase SQL Editor before running the Python conversion script

-- Drop table if exists (uncomment if you want to recreate)
-- DROP TABLE IF EXISTS bird_taxonomy CASCADE;

-- Create the main bird_taxonomy table
CREATE TABLE IF NOT EXISTS bird_taxonomy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    rank TEXT CHECK (rank IN ('class', 'order', 'family', 'genus', 'species')) NOT NULL,
    parent_id UUID REFERENCES bird_taxonomy(id) ON DELETE CASCADE,
    scientific_name TEXT,
    common_name TEXT,
    ebird_code TEXT, -- eBird species code (for species only)
    wikipedia_url TEXT,
    image_url TEXT,
    order_name TEXT, -- Denormalized for easier querying
    family_name TEXT, -- Denormalized for easier querying
    species_group TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_rank ON bird_taxonomy(rank);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_parent_id ON bird_taxonomy(parent_id);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_ebird_code ON bird_taxonomy(ebird_code);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_scientific_name ON bird_taxonomy(scientific_name);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_common_name ON bird_taxonomy(common_name);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_order_name ON bird_taxonomy(order_name);
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_family_name ON bird_taxonomy(family_name);

-- Create a composite index for hierarchical queries
CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_hierarchy ON bird_taxonomy(rank, parent_id);

-- Create a unique index for ebird_code where it's not null (species only)
CREATE UNIQUE INDEX IF NOT EXISTS idx_bird_taxonomy_ebird_code_unique 
    ON bird_taxonomy(ebird_code) 
    WHERE ebird_code IS NOT NULL;

-- Add RLS (Row Level Security) policies if needed
-- ALTER TABLE bird_taxonomy ENABLE ROW LEVEL SECURITY;

-- Create a policy for public read access
-- CREATE POLICY "Public read access" ON bird_taxonomy
--     FOR SELECT USING (true);

-- Create a function to get all descendants of a node
CREATE OR REPLACE FUNCTION get_taxonomy_descendants(node_id UUID)
RETURNS TABLE(
    id UUID,
    name TEXT,
    rank TEXT,
    parent_id UUID,
    scientific_name TEXT,
    common_name TEXT,
    ebird_code TEXT,
    level INTEGER
)
LANGUAGE SQL
AS $$
    WITH RECURSIVE descendants AS (
        -- Base case: the node itself
        SELECT 
            bt.id,
            bt.name,
            bt.rank,
            bt.parent_id,
            bt.scientific_name,
            bt.common_name,
            bt.ebird_code,
            0 as level
        FROM bird_taxonomy bt
        WHERE bt.id = node_id
        
        UNION ALL
        
        -- Recursive case: children of current nodes
        SELECT 
            bt.id,
            bt.name,
            bt.rank,
            bt.parent_id,
            bt.scientific_name,
            bt.common_name,
            bt.ebird_code,
            d.level + 1
        FROM bird_taxonomy bt
        INNER JOIN descendants d ON bt.parent_id = d.id
    )
    SELECT * FROM descendants;
$$;

-- Create a function to get the full taxonomic path of a node
CREATE OR REPLACE FUNCTION get_taxonomy_path(node_id UUID)
RETURNS TABLE(
    id UUID,
    name TEXT,
    rank TEXT,
    scientific_name TEXT,
    level INTEGER
)
LANGUAGE SQL
AS $$
    WITH RECURSIVE path AS (
        -- Base case: the node itself
        SELECT 
            bt.id,
            bt.name,
            bt.rank,
            bt.parent_id,
            bt.scientific_name,
            0 as level
        FROM bird_taxonomy bt
        WHERE bt.id = node_id
        
        UNION ALL
        
        -- Recursive case: parent nodes
        SELECT 
            bt.id,
            bt.name,
            bt.rank,
            bt.parent_id,
            bt.scientific_name,
            p.level + 1
        FROM bird_taxonomy bt
        INNER JOIN path p ON bt.id = p.parent_id
    )
    SELECT 
        id,
        name,
        rank,
        scientific_name,
        level
    FROM path
    ORDER BY level DESC;
$$;

-- Create a function to search taxonomy by name
CREATE OR REPLACE FUNCTION search_taxonomy(search_term TEXT)
RETURNS TABLE(
    id UUID,
    name TEXT,
    rank TEXT,
    scientific_name TEXT,
    common_name TEXT,
    ebird_code TEXT,
    match_score REAL
)
LANGUAGE SQL
AS $$
    SELECT 
        bt.id,
        bt.name,
        bt.rank,
        bt.scientific_name,
        bt.common_name,
        bt.ebird_code,
        GREATEST(
            similarity(bt.name, search_term),
            similarity(bt.scientific_name, search_term),
            similarity(bt.common_name, search_term)
        ) as match_score
    FROM bird_taxonomy bt
    WHERE 
        bt.name ILIKE '%' || search_term || '%'
        OR bt.scientific_name ILIKE '%' || search_term || '%'
        OR bt.common_name ILIKE '%' || search_term || '%'
    ORDER BY match_score DESC, bt.name
    LIMIT 50;
$$;

-- Enable the pg_trgm extension for similarity search (if not already enabled)
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

COMMENT ON TABLE bird_taxonomy IS 'Hierarchical bird taxonomy data from eBird';
COMMENT ON COLUMN bird_taxonomy.rank IS 'Taxonomic rank: class, order, family, genus, or species';
COMMENT ON COLUMN bird_taxonomy.parent_id IS 'Reference to parent node in the taxonomy hierarchy';
COMMENT ON COLUMN bird_taxonomy.ebird_code IS 'Unique eBird species code for species-level entries';
COMMENT ON FUNCTION get_taxonomy_descendants(UUID) IS 'Returns all descendant nodes of a given taxonomy node';
COMMENT ON FUNCTION get_taxonomy_path(UUID) IS 'Returns the full taxonomic path from root to the given node';
COMMENT ON FUNCTION search_taxonomy(TEXT) IS 'Searches taxonomy by name with similarity scoring';