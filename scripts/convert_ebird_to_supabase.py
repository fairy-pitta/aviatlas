#!/usr/bin/env python3
"""
eBird Taxonomy CSV to Supabase Bird Taxonomy Converter

This script converts eBird taxonomy data to a hierarchical structure
suitable for the bird_taxonomy table in Supabase.
"""

import csv
import os
import re
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class TaxonomyNode:
    """Represents a node in the taxonomy hierarchy"""
    name: str
    rank: str
    scientific_name: Optional[str] = None
    common_name: Optional[str] = None
    parent_id: Optional[str] = None
    ebird_code: Optional[str] = None
    order: Optional[str] = None
    family: Optional[str] = None
    species_group: Optional[str] = None

class eBirdToSupabaseConverter:
    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')  # Use service role key for admin operations
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL and Service Role Key must be set in environment variables")
        
        self.supabase: Client = create_client(supabase_url, supabase_key)
        
        # Storage for taxonomy nodes
        self.nodes: Dict[str, TaxonomyNode] = {}
        self.node_ids: Dict[str, str] = {}  # Maps node key to UUID
        
        # Track processed items to avoid duplicates
        self.processed_orders: Set[str] = set()
        self.processed_families: Set[str] = set()
        self.processed_genera: Set[str] = set()
        
    def clean_family_name(self, family_str: str) -> str:
        """Extract clean family name from eBird family string"""
        # Remove parenthetical descriptions like "(Ostriches)"
        match = re.match(r'^([^(]+)', family_str.strip())
        return match.group(1).strip() if match else family_str.strip()
    
    def extract_genus_from_scientific_name(self, sci_name: str) -> Optional[str]:
        """Extract genus from scientific name"""
        if not sci_name or sci_name.strip() == '':
            return None
        
        # Handle hybrid names and complex cases
        if ' x ' in sci_name or '/' in sci_name or '[' in sci_name:
            return None
        
        parts = sci_name.strip().split()
        if len(parts) >= 1:
            return parts[0]
        return None
    
    def create_class_node(self) -> str:
        """Create the root Aves class node"""
        class_key = "class_aves"
        if class_key not in self.nodes:
            self.nodes[class_key] = TaxonomyNode(
                name="Aves",
                rank="class",
                scientific_name="Aves",
                common_name="Birds"
            )
        return class_key
    
    def create_order_node(self, order_name: str, class_key: str) -> str:
        """Create an order node"""
        order_key = f"order_{order_name.lower().replace(' ', '_')}"
        if order_key not in self.nodes and order_name not in self.processed_orders:
            self.nodes[order_key] = TaxonomyNode(
                name=order_name,
                rank="order",
                scientific_name=order_name,
                common_name=order_name,
                parent_id=class_key
            )
            self.processed_orders.add(order_name)
        return order_key
    
    def create_family_node(self, family_str: str, order_key: str) -> str:
        """Create a family node"""
        family_name = self.clean_family_name(family_str)
        family_key = f"family_{family_name.lower().replace(' ', '_').replace('-', '_')}"
        
        if family_key not in self.nodes and family_name not in self.processed_families:
            self.nodes[family_key] = TaxonomyNode(
                name=family_name,
                rank="family",
                scientific_name=family_name,
                common_name=family_str,  # Keep original with description
                parent_id=order_key
            )
            self.processed_families.add(family_name)
        return family_key
    
    def create_genus_node(self, genus_name: str, family_key: str) -> str:
        """Create a genus node"""
        genus_key = f"genus_{genus_name.lower().replace(' ', '_')}"
        if genus_key not in self.nodes and genus_name not in self.processed_genera:
            self.nodes[genus_key] = TaxonomyNode(
                name=genus_name,
                rank="genus",
                scientific_name=genus_name,
                common_name=genus_name,
                parent_id=family_key
            )
            self.processed_genera.add(genus_name)
        return genus_key
    
    def create_species_node(self, row: Dict, genus_key: str) -> str:
        """Create a species node"""
        species_code = row['SPECIES_CODE']
        species_key = f"species_{species_code}"
        
        if species_key not in self.nodes:
            self.nodes[species_key] = TaxonomyNode(
                name=row['PRIMARY_COM_NAME'],
                rank="species",
                scientific_name=row['SCI_NAME'],
                common_name=row['PRIMARY_COM_NAME'],
                parent_id=genus_key,
                ebird_code=species_code,
                order=row['ORDER'],
                family=row['FAMILY'],
                species_group=row['SPECIES_GROUP']
            )
        return species_key
    
    def process_csv_file(self, csv_file_path: str):
        """Process the eBird CSV file and build taxonomy hierarchy"""
        print(f"Processing {csv_file_path}...")
        
        # Create root class node
        class_key = self.create_class_node()
        
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for i, row in enumerate(reader):
                if i % 1000 == 0:
                    print(f"Processed {i} rows...")
                
                # Skip non-species entries for now (focus on species only)
                if row['CATEGORY'] != 'species':
                    continue
                
                # Skip if missing essential data
                if not row['ORDER'] or not row['FAMILY'] or not row['SCI_NAME']:
                    continue
                
                # Create hierarchy: Class -> Order -> Family -> Genus -> Species
                order_key = self.create_order_node(row['ORDER'], class_key)
                family_key = self.create_family_node(row['FAMILY'], order_key)
                
                # Extract genus from scientific name
                genus_name = self.extract_genus_from_scientific_name(row['SCI_NAME'])
                if genus_name:
                    genus_key = self.create_genus_node(genus_name, family_key)
                    species_key = self.create_species_node(row, genus_key)
                else:
                    # If we can't extract genus, attach species directly to family
                    species_key = self.create_species_node(row, family_key)
        
        print(f"Built taxonomy tree with {len(self.nodes)} nodes")
    
    def create_supabase_table(self):
        """Create the bird_taxonomy table in Supabase"""
        print("Creating bird_taxonomy table...")
        
        # SQL to create the table
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS bird_taxonomy (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            rank TEXT CHECK (rank IN ('class', 'order', 'family', 'genus', 'species')) NOT NULL,
            parent_id UUID REFERENCES bird_taxonomy(id) ON DELETE CASCADE,
            scientific_name TEXT,
            common_name TEXT,
            ebird_code TEXT,
            wikipedia_url TEXT,
            image_url TEXT,
            order_name TEXT,
            family_name TEXT,
            species_group TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        
        -- Create indexes for better performance
        CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_rank ON bird_taxonomy(rank);
        CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_parent_id ON bird_taxonomy(parent_id);
        CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_ebird_code ON bird_taxonomy(ebird_code);
        CREATE INDEX IF NOT EXISTS idx_bird_taxonomy_scientific_name ON bird_taxonomy(scientific_name);
        """
        
        try:
            # Execute the SQL using Supabase's rpc function or direct SQL execution
            # Note: This might need to be run manually in Supabase dashboard
            print("Table creation SQL:")
            print(create_table_sql)
            print("\nPlease run this SQL in your Supabase dashboard SQL editor.")
        except Exception as e:
            print(f"Error creating table: {e}")
    
    def insert_nodes_to_supabase(self):
        """Insert all taxonomy nodes to Supabase"""
        print("Inserting nodes to Supabase...")
        
        # First, insert nodes in hierarchical order (parents before children)
        insertion_order = ['class', 'order', 'family', 'genus', 'species']
        
        for rank in insertion_order:
            rank_nodes = [(key, node) for key, node in self.nodes.items() if node.rank == rank]
            print(f"Inserting {len(rank_nodes)} {rank} nodes...")
            
            batch_size = 100
            for i in range(0, len(rank_nodes), batch_size):
                batch = rank_nodes[i:i + batch_size]
                batch_data = []
                
                for key, node in batch:
                    # Resolve parent_id to actual UUID if it exists
                    parent_uuid = None
                    if node.parent_id and node.parent_id in self.node_ids:
                        parent_uuid = self.node_ids[node.parent_id]
                    
                    data = {
                        'name': node.name,
                        'rank': node.rank,
                        'parent_id': parent_uuid,
                        'scientific_name': node.scientific_name,
                        'common_name': node.common_name,
                        'ebird_code': node.ebird_code,
                        'order_name': node.order,
                        'family_name': node.family,
                        'species_group': node.species_group
                    }
                    batch_data.append(data)
                
                try:
                    # Insert batch
                    result = self.supabase.table('bird_taxonomy').insert(batch_data).execute()
                    
                    # Store the returned UUIDs for parent-child relationships
                    for j, (key, node) in enumerate(batch):
                        if result.data and j < len(result.data):
                            self.node_ids[key] = result.data[j]['id']
                    
                    print(f"Inserted batch {i//batch_size + 1} of {rank} nodes")
                    
                except Exception as e:
                    print(f"Error inserting {rank} batch: {e}")
                    # Continue with next batch
                    continue
    
    def run_conversion(self, csv_file_path: str):
        """Run the complete conversion process"""
        print("Starting eBird to Supabase conversion...")
        
        # Step 1: Process CSV and build hierarchy
        self.process_csv_file(csv_file_path)
        
        # Step 2: Create table (manual step)
        self.create_supabase_table()
        
        # Step 3: Insert data
        response = input("\nHave you created the table in Supabase? (y/n): ")
        if response.lower() == 'y':
            self.insert_nodes_to_supabase()
            print("Conversion completed!")
        else:
            print("Please create the table first, then run the insertion manually.")

def main():
    """Main function"""
    csv_file_path = "/Users/shuna/aviatlas/data/eBird_taxonomy_v2024.csv"
    
    if not os.path.exists(csv_file_path):
        print(f"CSV file not found: {csv_file_path}")
        return
    
    converter = eBirdToSupabaseConverter()
    converter.run_conversion(csv_file_path)

if __name__ == "__main__":
    main()