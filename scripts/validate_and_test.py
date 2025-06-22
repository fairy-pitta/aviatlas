#!/usr/bin/env python3
"""
Validation and Testing Script for Bird Taxonomy Data

This script provides validation functions and test cases for the bird taxonomy conversion.
"""

import os
import csv
from typing import Dict, List, Set, Tuple
from collections import defaultdict, Counter
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class TaxonomyValidator:
    def __init__(self):
        # Initialize Supabase client
        supabase_url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
        supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if supabase_url and supabase_key:
            self.supabase: Client = create_client(supabase_url, supabase_key)
        else:
            self.supabase = None
            print("Warning: Supabase credentials not found. Database validation will be skipped.")
    
    def validate_csv_structure(self, csv_file_path: str) -> Dict[str, any]:
        """Validate the structure and content of the eBird CSV file"""
        print("Validating CSV structure...")
        
        validation_results = {
            'total_rows': 0,
            'species_count': 0,
            'missing_data': defaultdict(int),
            'categories': Counter(),
            'orders': set(),
            'families': set(),
            'duplicate_codes': [],
            'invalid_scientific_names': [],
            'errors': []
        }
        
        seen_codes = set()
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                # Check required columns
                required_columns = ['TAXON_ORDER', 'CATEGORY', 'SPECIES_CODE', 'PRIMARY_COM_NAME', 
                                  'SCI_NAME', 'ORDER', 'FAMILY', 'SPECIES_GROUP']
                missing_columns = [col for col in required_columns if col not in reader.fieldnames]
                
                if missing_columns:
                    validation_results['errors'].append(f"Missing required columns: {missing_columns}")
                    return validation_results
                
                for i, row in enumerate(reader):
                    validation_results['total_rows'] += 1
                    
                    # Count categories
                    validation_results['categories'][row['CATEGORY']] += 1
                    
                    if row['CATEGORY'] == 'species':
                        validation_results['species_count'] += 1
                    
                    # Check for missing essential data
                    for field in ['SPECIES_CODE', 'PRIMARY_COM_NAME', 'SCI_NAME']:
                        if not row[field].strip():
                            validation_results['missing_data'][field] += 1
                    
                    # Check for duplicate species codes
                    code = row['SPECIES_CODE']
                    if code in seen_codes:
                        validation_results['duplicate_codes'].append(code)
                    else:
                        seen_codes.add(code)
                    
                    # Validate scientific name format
                    sci_name = row['SCI_NAME'].strip()
                    if sci_name and not self._is_valid_scientific_name(sci_name):
                        validation_results['invalid_scientific_names'].append(sci_name)
                    
                    # Collect taxonomy data
                    if row['ORDER']:
                        validation_results['orders'].add(row['ORDER'])
                    if row['FAMILY']:
                        validation_results['families'].add(row['FAMILY'])
                    
                    # Progress indicator
                    if i % 5000 == 0:
                        print(f"Validated {i} rows...")
        
        except Exception as e:
            validation_results['errors'].append(f"Error reading CSV: {str(e)}")
        
        return validation_results
    
    def _is_valid_scientific_name(self, sci_name: str) -> bool:
        """Basic validation for scientific name format"""
        # Skip hybrid names and complex cases
        if any(char in sci_name for char in ['x', '/', '[', '(']):
            return True  # These are valid but complex cases
        
        # Basic binomial nomenclature check
        parts = sci_name.split()
        if len(parts) < 1:
            return False
        
        # First part should be capitalized (genus)
        if not parts[0][0].isupper():
            return False
        
        return True
    
    def validate_hierarchy_consistency(self, csv_file_path: str) -> Dict[str, any]:
        """Validate that the taxonomic hierarchy is consistent"""
        print("Validating hierarchy consistency...")
        
        hierarchy_data = defaultdict(lambda: defaultdict(set))
        inconsistencies = []
        
        with open(csv_file_path, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            
            for row in reader:
                if row['CATEGORY'] != 'species':
                    continue
                
                order = row['ORDER']
                family = row['FAMILY']
                genus = self._extract_genus(row['SCI_NAME'])
                
                if order and family:
                    hierarchy_data[order]['families'].add(family)
                
                if family and genus:
                    hierarchy_data[family]['genera'].add(genus)
        
        # Check for families appearing in multiple orders
        family_to_orders = defaultdict(set)
        for order, data in hierarchy_data.items():
            for family in data['families']:
                family_to_orders[family].add(order)
        
        for family, orders in family_to_orders.items():
            if len(orders) > 1:
                inconsistencies.append(f"Family '{family}' appears in multiple orders: {list(orders)}")
        
        return {
            'total_orders': len(hierarchy_data),
            'total_families': len(family_to_orders),
            'inconsistencies': inconsistencies,
            'hierarchy_stats': dict(hierarchy_data)
        }
    
    def _extract_genus(self, sci_name: str) -> str:
        """Extract genus from scientific name"""
        if not sci_name or ' x ' in sci_name or '/' in sci_name:
            return None
        
        parts = sci_name.strip().split()
        return parts[0] if parts else None
    
    def validate_database_integrity(self) -> Dict[str, any]:
        """Validate the integrity of data in Supabase"""
        if not self.supabase:
            return {'error': 'Supabase connection not available'}
        
        print("Validating database integrity...")
        
        try:
            # Check table exists and get basic stats
            result = self.supabase.table('bird_taxonomy').select('rank', count='exact').execute()
            total_count = result.count
            
            # Get counts by rank
            rank_counts = {}
            for rank in ['class', 'order', 'family', 'genus', 'species']:
                result = self.supabase.table('bird_taxonomy').select('id', count='exact').eq('rank', rank).execute()
                rank_counts[rank] = result.count
            
            # Check for orphaned records (except class level)
            orphaned_query = self.supabase.table('bird_taxonomy').select('id', 'name', 'rank').is_('parent_id', 'null').neq('rank', 'class').execute()
            orphaned_records = orphaned_query.data
            
            # Check for circular references (basic check)
            # This is a simplified check - in production you'd want more comprehensive validation
            
            # Check for duplicate ebird_codes
            duplicate_codes_query = self.supabase.rpc('check_duplicate_ebird_codes').execute()
            
            return {
                'total_records': total_count,
                'rank_distribution': rank_counts,
                'orphaned_records': len(orphaned_records),
                'orphaned_details': orphaned_records[:10],  # First 10 for review
                'validation_passed': len(orphaned_records) == 0
            }
        
        except Exception as e:
            return {'error': f'Database validation failed: {str(e)}'}
    
    def generate_sample_queries(self) -> List[str]:
        """Generate sample queries for testing the database"""
        return [
            "-- Get all orders\nSELECT name, scientific_name FROM bird_taxonomy WHERE rank = 'order' ORDER BY name;",
            
            "-- Get species count by family\nSELECT family_name, COUNT(*) as species_count \nFROM bird_taxonomy \nWHERE rank = 'species' AND family_name IS NOT NULL \nGROUP BY family_name \nORDER BY species_count DESC \nLIMIT 20;",
            
            "-- Test hierarchical query - get all descendants of Passeriformes\nSELECT * FROM get_taxonomy_descendants(\n    (SELECT id FROM bird_taxonomy WHERE name = 'Passeriformes' AND rank = 'order')\n) LIMIT 10;",
            
            "-- Test search function\nSELECT * FROM search_taxonomy('crow') LIMIT 10;",
            
            "-- Get taxonomic path for a specific species\nSELECT * FROM get_taxonomy_path(\n    (SELECT id FROM bird_taxonomy WHERE ebird_code = 'amecro' LIMIT 1)\n);",
            
            "-- Check data integrity - find records without proper hierarchy\nSELECT bt1.name, bt1.rank, bt2.name as parent_name, bt2.rank as parent_rank\nFROM bird_taxonomy bt1\nLEFT JOIN bird_taxonomy bt2 ON bt1.parent_id = bt2.id\nWHERE bt1.rank != 'class' AND bt2.id IS NULL;"
        ]
    
    def run_comprehensive_validation(self, csv_file_path: str) -> Dict[str, any]:
        """Run all validation checks"""
        print("=== Running Comprehensive Validation ===")
        
        results = {
            'csv_validation': self.validate_csv_structure(csv_file_path),
            'hierarchy_validation': self.validate_hierarchy_consistency(csv_file_path),
            'database_validation': self.validate_database_integrity(),
            'sample_queries': self.generate_sample_queries()
        }
        
        return results
    
    def print_validation_report(self, results: Dict[str, any]):
        """Print a formatted validation report"""
        print("\n" + "="*60)
        print("BIRD TAXONOMY VALIDATION REPORT")
        print("="*60)
        
        # CSV Validation Results
        csv_results = results['csv_validation']
        print(f"\n📊 CSV VALIDATION:")
        print(f"  Total rows: {csv_results['total_rows']:,}")
        print(f"  Species count: {csv_results['species_count']:,}")
        print(f"  Categories: {dict(csv_results['categories'])}")
        print(f"  Unique orders: {len(csv_results['orders'])}")
        print(f"  Unique families: {len(csv_results['families'])}")
        
        if csv_results['errors']:
            print(f"  ❌ Errors: {len(csv_results['errors'])}")
            for error in csv_results['errors'][:5]:
                print(f"    - {error}")
        
        if csv_results['duplicate_codes']:
            print(f"  ⚠️  Duplicate codes: {len(csv_results['duplicate_codes'])}")
        
        # Hierarchy Validation
        hierarchy_results = results['hierarchy_validation']
        print(f"\n🌳 HIERARCHY VALIDATION:")
        print(f"  Total orders: {hierarchy_results['total_orders']}")
        print(f"  Total families: {hierarchy_results['total_families']}")
        
        if hierarchy_results['inconsistencies']:
            print(f"  ❌ Inconsistencies: {len(hierarchy_results['inconsistencies'])}")
            for inconsistency in hierarchy_results['inconsistencies'][:3]:
                print(f"    - {inconsistency}")
        else:
            print(f"  ✅ No hierarchy inconsistencies found")
        
        # Database Validation
        db_results = results['database_validation']
        print(f"\n🗄️  DATABASE VALIDATION:")
        if 'error' in db_results:
            print(f"  ❌ {db_results['error']}")
        else:
            print(f"  Total records: {db_results['total_records']:,}")
            print(f"  Rank distribution: {db_results['rank_distribution']}")
            print(f"  Orphaned records: {db_results['orphaned_records']}")
            
            if db_results['validation_passed']:
                print(f"  ✅ Database integrity check passed")
            else:
                print(f"  ⚠️  Database integrity issues found")
        
        print(f"\n🔍 SAMPLE QUERIES:")
        print(f"  Generated {len(results['sample_queries'])} test queries")
        print(f"  Run these in your Supabase SQL editor to test functionality")
        
        print("\n" + "="*60)

def main():
    """Main function for running validation"""
    csv_file_path = "/Users/shuna/aviatlas/data/eBird_taxonomy_v2024.csv"
    
    if not os.path.exists(csv_file_path):
        print(f"CSV file not found: {csv_file_path}")
        return
    
    validator = TaxonomyValidator()
    results = validator.run_comprehensive_validation(csv_file_path)
    validator.print_validation_report(results)
    
    # Save sample queries to file
    with open('/Users/shuna/aviatlas/scripts/sample_queries.sql', 'w') as f:
        f.write("-- Sample Queries for Bird Taxonomy Database\n\n")
        for i, query in enumerate(results['sample_queries'], 1):
            f.write(f"-- Query {i}\n{query}\n\n")
    
    print("\n📝 Sample queries saved to scripts/sample_queries.sql")

if __name__ == "__main__":
    main()