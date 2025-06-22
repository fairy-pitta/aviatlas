#!/usr/bin/env python3
"""
Enhanced eBird Taxonomy CSV to Supabase Converter

Improved version with better error handling, logging, and data validation.
"""

import csv
import os
import re
import logging
import time
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from supabase import create_client, Client
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/Users/shuna/aviatlas/scripts/conversion.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    metadata: Dict = field(default_factory=dict)

@dataclass
class ConversionStats:
    """Track conversion statistics"""
    total_csv_rows: int = 0
    processed_species: int = 0
    created_nodes: int = 0
    skipped_rows: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    def duration(self) -> Optional[float]:
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return None

class EnhancedeBirdConverter:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.stats = ConversionStats()
        
        # Initialize Supabase client
        if not self.dry_run:
            supabase_url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
            
            if not supabase_url or not supabase_key:
                raise ValueError(
                    "Missing Supabase credentials. Please set:\n"
                    "- NEXT_PUBLIC_SUPABASE_URL\n"
                    "- SUPABASE_SERVICE_ROLE_KEY\n"
                    "in your .env file"
                )
            
            self.supabase: Client = create_client(supabase_url, supabase_key)
            logger.info("Connected to Supabase")
        else:
            self.supabase = None
            logger.info("Running in DRY RUN mode - no database operations")
        
        # Storage for taxonomy nodes
        self.nodes: Dict[str, TaxonomyNode] = {}
        self.node_ids: Dict[str, str] = {}  # Maps node key to UUID
        
        # Track processed items to avoid duplicates
        self.processed_orders: Set[str] = set()
        self.processed_families: Set[str] = set()
        self.processed_genera: Set[str] = set()
        
        # Data quality tracking
        self.data_quality = {
            'invalid_scientific_names': [],
            'missing_essential_data': [],
            'duplicate_ebird_codes': [],
            'hierarchy_inconsistencies': []
        }
    
    def validate_csv_row(self, row: Dict, row_num: int) -> Tuple[bool, List[str]]:
        """Validate a single CSV row"""
        errors = []
        
        # Check required fields
        required_fields = ['SPECIES_CODE', 'PRIMARY_COM_NAME', 'SCI_NAME', 'ORDER', 'FAMILY']
        for field in required_fields:
            if not row.get(field, '').strip():
                errors.append(f"Row {row_num}: Missing {field}")
        
        # Validate scientific name format
        sci_name = row.get('SCI_NAME', '').strip()
        if sci_name and not self._is_valid_scientific_name(sci_name):
            errors.append(f"Row {row_num}: Invalid scientific name format: {sci_name}")
            self.data_quality['invalid_scientific_names'].append((row_num, sci_name))
        
        # Check for reasonable name lengths
        if len(row.get('PRIMARY_COM_NAME', '')) > 200:
            errors.append(f"Row {row_num}: Common name too long")
        
        return len(errors) == 0, errors
    
    def _is_valid_scientific_name(self, sci_name: str) -> bool:
        """Enhanced scientific name validation"""
        # Skip hybrid names and complex cases
        if any(char in sci_name for char in ['x', '/', '[']):
            return True  # These are valid but complex cases
        
        # Basic binomial nomenclature check
        parts = sci_name.split()
        if len(parts) < 1:
            return False
        
        # First part should be capitalized (genus)
        if not parts[0][0].isupper():
            return False
        
        # Check for reasonable character set
        if not re.match(r'^[A-Za-z\s\-\.]+$', sci_name):
            return False
        
        return True
    
    def clean_family_name(self, family_str: str) -> str:
        """Extract clean family name from eBird family string"""
        if not family_str:
            return ''
        
        # Remove parenthetical descriptions like "(Ostriches)"
        match = re.match(r'^([^(]+)', family_str.strip())
        cleaned = match.group(1).strip() if match else family_str.strip()
        
        # Additional cleaning
        cleaned = re.sub(r'\s+', ' ', cleaned)  # Normalize whitespace
        return cleaned
    
    def extract_genus_from_scientific_name(self, sci_name: str) -> Optional[str]:
        """Extract genus from scientific name with better error handling"""
        if not sci_name or sci_name.strip() == '':
            return None
        
        # Handle hybrid names and complex cases
        if ' x ' in sci_name or '/' in sci_name or '[' in sci_name:
            return None
        
        try:
            parts = sci_name.strip().split()
            if len(parts) >= 1 and parts[0].isalpha():
                return parts[0]
        except Exception as e:
            logger.warning(f"Error extracting genus from '{sci_name}': {e}")
        
        return None
    
    def create_class_node(self) -> str:
        """Create the root Aves class node"""
        class_key = "class_aves"
        if class_key not in self.nodes:
            self.nodes[class_key] = TaxonomyNode(
                name="Aves",
                rank="class",
                scientific_name="Aves",
                common_name="Birds",
                metadata={"description": "Class of all birds"}
            )
            logger.info("Created Aves class node")
        return class_key
    
    def create_order_node(self, order_name: str, class_key: str) -> str:
        """Create an order node with validation"""
        if not order_name or order_name.strip() == '':
            raise ValueError("Order name cannot be empty")
        
        order_name = order_name.strip()
        order_key = f"order_{order_name.lower().replace(' ', '_').replace('-', '_')}"
        
        if order_key not in self.nodes and order_name not in self.processed_orders:
            self.nodes[order_key] = TaxonomyNode(
                name=order_name,
                rank="order",
                scientific_name=order_name,
                common_name=order_name,
                parent_id=class_key,
                metadata={"created_from": "ebird_csv"}
            )
            self.processed_orders.add(order_name)
            logger.debug(f"Created order node: {order_name}")
        
        return order_key
    
    def create_family_node(self, family_str: str, order_key: str) -> str:
        """Create a family node with enhanced validation"""
        if not family_str or family_str.strip() == '':
            raise ValueError("Family name cannot be empty")
        
        family_name = self.clean_family_name(family_str)
        if not family_name:
            raise ValueError(f"Could not extract valid family name from: {family_str}")
        
        family_key = f"family_{family_name.lower().replace(' ', '_').replace('-', '_')}"
        
        if family_key not in self.nodes and family_name not in self.processed_families:
            self.nodes[family_key] = TaxonomyNode(
                name=family_name,
                rank="family",
                scientific_name=family_name,
                common_name=family_str,  # Keep original with description
                parent_id=order_key,
                metadata={"original_name": family_str}
            )
            self.processed_families.add(family_name)
            logger.debug(f"Created family node: {family_name}")
        
        return family_key
    
    def create_genus_node(self, genus_name: str, family_key: str) -> str:
        """Create a genus node with validation"""
        if not genus_name or genus_name.strip() == '':
            raise ValueError("Genus name cannot be empty")
        
        genus_name = genus_name.strip()
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
            logger.debug(f"Created genus node: {genus_name}")
        
        return genus_key
    
    def create_species_node(self, row: Dict, genus_key: str) -> str:
        """Create a species node with comprehensive data"""
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
                species_group=row['SPECIES_GROUP'],
                metadata={
                    'taxon_order': row.get('TAXON_ORDER'),
                    'category': row.get('CATEGORY'),
                    'report_as': row.get('REPORT_AS')
                }
            )
            logger.debug(f"Created species node: {row['PRIMARY_COM_NAME']} ({species_code})")
        
        return species_key
    
    def process_csv_file(self, csv_file_path: str):
        """Process the eBird CSV file with enhanced error handling"""
        logger.info(f"Processing {csv_file_path}...")
        self.stats.start_time = datetime.now()
        
        # Create root class node
        class_key = self.create_class_node()
        
        try:
            with open(csv_file_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                # Get total rows for progress bar
                total_rows = sum(1 for _ in open(csv_file_path, 'r', encoding='utf-8')) - 1
                file.seek(0)
                reader = csv.DictReader(file)
                
                with tqdm(total=total_rows, desc="Processing rows") as pbar:
                    for i, row in enumerate(reader):
                        self.stats.total_csv_rows += 1
                        pbar.update(1)
                        
                        try:
                            # Validate row
                            is_valid, validation_errors = self.validate_csv_row(row, i + 1)
                            if not is_valid:
                                self.stats.errors.extend(validation_errors)
                                self.stats.skipped_rows += 1
                                continue
                            
                            # Skip non-species entries for now
                            if row['CATEGORY'] != 'species':
                                self.stats.skipped_rows += 1
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
                                self.stats.warnings.append(f"Row {i+1}: Could not extract genus from '{row['SCI_NAME']}'")
                            
                            self.stats.processed_species += 1
                            
                        except Exception as e:
                            error_msg = f"Row {i+1}: {str(e)}"
                            self.stats.errors.append(error_msg)
                            logger.error(error_msg)
                            continue
        
        except Exception as e:
            error_msg = f"Error reading CSV file: {str(e)}"
            self.stats.errors.append(error_msg)
            logger.error(error_msg)
            raise
        
        self.stats.created_nodes = len(self.nodes)
        logger.info(f"Built taxonomy tree with {self.stats.created_nodes} nodes")
        logger.info(f"Processed {self.stats.processed_species} species")
        
        if self.stats.warnings:
            logger.warning(f"Generated {len(self.stats.warnings)} warnings")
        
        if self.stats.errors:
            logger.error(f"Encountered {len(self.stats.errors)} errors")
    
    def insert_nodes_to_supabase(self, batch_size: int = 50):
        """Insert all taxonomy nodes to Supabase with improved error handling"""
        if self.dry_run:
            logger.info("DRY RUN: Would insert nodes to Supabase")
            return
        
        logger.info("Inserting nodes to Supabase...")
        
        # Insert nodes in hierarchical order
        insertion_order = ['class', 'order', 'family', 'genus', 'species']
        
        for rank in insertion_order:
            rank_nodes = [(key, node) for key, node in self.nodes.items() if node.rank == rank]
            logger.info(f"Inserting {len(rank_nodes)} {rank} nodes...")
            
            if not rank_nodes:
                continue
            
            # Process in batches
            for i in tqdm(range(0, len(rank_nodes), batch_size), desc=f"Inserting {rank} nodes"):
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
                    # Insert batch with retry logic
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            result = self.supabase.table('bird_taxonomy').insert(batch_data).execute()
                            
                            # Store the returned UUIDs for parent-child relationships
                            for j, (key, node) in enumerate(batch):
                                if result.data and j < len(result.data):
                                    self.node_ids[key] = result.data[j]['id']
                            
                            break  # Success, exit retry loop
                            
                        except Exception as e:
                            if attempt == max_retries - 1:
                                raise  # Last attempt failed
                            logger.warning(f"Attempt {attempt + 1} failed for {rank} batch: {e}")
                            time.sleep(2 ** attempt)  # Exponential backoff
                    
                except Exception as e:
                    error_msg = f"Error inserting {rank} batch {i//batch_size + 1}: {e}"
                    self.stats.errors.append(error_msg)
                    logger.error(error_msg)
                    continue
    
    def generate_summary_report(self) -> str:
        """Generate a comprehensive summary report"""
        self.stats.end_time = datetime.now()
        
        report = []
        report.append("=" * 60)
        report.append("EBIRD TO SUPABASE CONVERSION SUMMARY")
        report.append("=" * 60)
        report.append(f"Start time: {self.stats.start_time}")
        report.append(f"End time: {self.stats.end_time}")
        report.append(f"Duration: {self.stats.duration():.2f} seconds")
        report.append("")
        report.append("PROCESSING STATISTICS:")
        report.append(f"  Total CSV rows: {self.stats.total_csv_rows:,}")
        report.append(f"  Processed species: {self.stats.processed_species:,}")
        report.append(f"  Created nodes: {self.stats.created_nodes:,}")
        report.append(f"  Skipped rows: {self.stats.skipped_rows:,}")
        report.append("")
        report.append("NODE BREAKDOWN:")
        
        for rank in ['class', 'order', 'family', 'genus', 'species']:
            count = len([n for n in self.nodes.values() if n.rank == rank])
            report.append(f"  {rank.capitalize()}: {count:,}")
        
        report.append("")
        report.append(f"ERRORS: {len(self.stats.errors)}")
        if self.stats.errors:
            for error in self.stats.errors[:10]:  # Show first 10 errors
                report.append(f"  - {error}")
            if len(self.stats.errors) > 10:
                report.append(f"  ... and {len(self.stats.errors) - 10} more")
        
        report.append("")
        report.append(f"WARNINGS: {len(self.stats.warnings)}")
        if self.stats.warnings:
            for warning in self.stats.warnings[:5]:  # Show first 5 warnings
                report.append(f"  - {warning}")
            if len(self.stats.warnings) > 5:
                report.append(f"  ... and {len(self.stats.warnings) - 5} more")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def run_conversion(self, csv_file_path: str, batch_size: int = 50):
        """Run the complete conversion process"""
        logger.info("Starting enhanced eBird to Supabase conversion...")
        
        try:
            # Step 1: Process CSV and build hierarchy
            self.process_csv_file(csv_file_path)
            
            # Step 2: Insert data (if not dry run)
            if not self.dry_run:
                # Check if table exists
                try:
                    test_query = self.supabase.table('bird_taxonomy').select('id').limit(1).execute()
                    logger.info("Table exists, proceeding with data insertion")
                except Exception as e:
                    logger.error(f"Table 'bird_taxonomy' not found or accessible: {e}")
                    logger.error("Please create the table using create_bird_taxonomy_table.sql")
                    return
                
                self.insert_nodes_to_supabase(batch_size)
            
            # Step 3: Generate and display report
            report = self.generate_summary_report()
            print(report)
            
            # Save report to file
            report_file = f"/Users/shuna/aviatlas/scripts/conversion_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(report_file, 'w') as f:
                f.write(report)
            
            logger.info(f"Conversion completed! Report saved to {report_file}")
            
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise

def main():
    """Main function with command line argument support"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Convert eBird taxonomy to Supabase')
    parser.add_argument('--csv-path', default='/Users/shuna/aviatlas/data/eBird_taxonomy_v2024.csv',
                       help='Path to eBird CSV file')
    parser.add_argument('--batch-size', type=int, default=50,
                       help='Batch size for database insertions')
    parser.add_argument('--dry-run', action='store_true',
                       help='Run without making database changes')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.csv_path):
        logger.error(f"CSV file not found: {args.csv_path}")
        return
    
    converter = EnhancedeBirdConverter(dry_run=args.dry_run)
    converter.run_conversion(args.csv_path, args.batch_size)

if __name__ == "__main__":
    main()