#!/usr/bin/env python3
"""
Mass Wikipedia and Image URL Updater for Bird Taxonomy

A script designed for processing large numbers of species efficiently
with batch processing and resume capability.
"""

import os
import sys
import time
import json
import logging
from datetime import datetime
from pathlib import Path
from simple_wiki_update import SimpleWikiUpdater

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mass_wiki_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class MassWikiUpdater:
    """Mass updater with batch processing and resume capability"""
    
    def __init__(self, batch_size: int = 100, dry_run: bool = False):
        self.batch_size = batch_size
        self.dry_run = dry_run
        self.updater = SimpleWikiUpdater(dry_run=dry_run)
        self.progress_file = 'mass_update_progress.json'
        
        # Load or initialize progress
        self.progress = self._load_progress()
    
    def _load_progress(self) -> dict:
        """Load progress from file or create new"""
        if Path(self.progress_file).exists():
            try:
                with open(self.progress_file, 'r') as f:
                    progress = json.load(f)
                    logger.info(f"Resuming from offset {progress.get('last_offset', 0)}")
                    return progress
            except Exception as e:
                logger.warning(f"Could not load progress file: {e}")
        
        return {
            'started_at': datetime.now().isoformat(),
            'last_offset': 0,
            'total_processed': 0,
            'total_updated': 0,
            'total_errors': 0,
            'batches_completed': 0
        }
    
    def _save_progress(self):
        """Save current progress to file"""
        try:
            self.progress['last_updated'] = datetime.now().isoformat()
            with open(self.progress_file, 'w') as f:
                json.dump(self.progress, f, indent=2)
        except Exception as e:
            logger.error(f"Could not save progress: {e}")
    
    def process_all_species(self, max_batches: int = None, start_fresh: bool = False):
        """Process all species in batches"""
        if start_fresh:
            self.progress = {
                'started_at': datetime.now().isoformat(),
                'last_offset': 0,
                'total_processed': 0,
                'total_updated': 0,
                'total_errors': 0,
                'batches_completed': 0
            }
            logger.info("Starting fresh (ignoring previous progress)")
        
        logger.info(f"Starting mass update (dry_run={self.dry_run})")
        logger.info(f"Batch size: {self.batch_size}")
        
        if max_batches:
            logger.info(f"Maximum batches: {max_batches}")
        
        batch_count = 0
        current_offset = self.progress['last_offset']
        
        while True:
            # Check if we've reached the maximum number of batches
            if max_batches and batch_count >= max_batches:
                logger.info(f"Reached maximum batch limit ({max_batches})")
                break
            
            batch_count += 1
            logger.info(f"\n{'='*60}")
            logger.info(f"BATCH {batch_count} (Offset: {current_offset})")
            logger.info(f"{'='*60}")
            
            # Get species for this batch
            species_list = self.updater.get_species_to_update(
                limit=self.batch_size, 
                offset=current_offset
            )
            
            if not species_list:
                logger.info("No more species to process - all done!")
                break
            
            batch_start_time = time.time()
            
            # Process this batch
            batch_stats = self._process_batch(species_list, current_offset)
            
            batch_duration = time.time() - batch_start_time
            
            # Update progress
            self.progress['last_offset'] = current_offset + len(species_list)
            self.progress['total_processed'] += batch_stats['processed']
            self.progress['total_updated'] += batch_stats['updated']
            self.progress['total_errors'] += batch_stats['errors']
            self.progress['batches_completed'] += 1
            
            # Save progress
            self._save_progress()
            
            # Log batch summary
            logger.info(f"\nBatch {batch_count} Summary:")
            logger.info(f"  Processed: {batch_stats['processed']}")
            logger.info(f"  Updated: {batch_stats['updated']}")
            logger.info(f"  Errors: {batch_stats['errors']}")
            logger.info(f"  Duration: {batch_duration:.1f}s")
            logger.info(f"  Rate: {batch_stats['processed']/batch_duration:.1f} species/sec")
            
            # Update offset for next batch
            current_offset = self.progress['last_offset']
            
            # Brief pause between batches
            if len(species_list) == self.batch_size:  # Only if we got a full batch
                logger.info("Pausing 2 seconds between batches...")
                time.sleep(2)
        
        self._print_final_summary()
    
    def _process_batch(self, species_list: list, offset: int) -> dict:
        """Process a single batch of species"""
        stats = {
            'processed': 0,
            'updated': 0,
            'errors': 0,
            'wikipedia_found': 0,
            'images_found': 0
        }
        
        for i, species in enumerate(species_list, 1):
            stats['processed'] += 1
            
            scientific_name = species.get('scientific_name')
            common_name = species.get('common_name')
            species_id = species.get('id')
            
            logger.info(f"  {offset + i}: {scientific_name}")
            
            try:
                # Search for Wikipedia data
                wiki_result = self.updater.search_wikipedia(scientific_name, common_name)
                
                if wiki_result['success']:
                    if wiki_result['wikipedia_url']:
                        stats['wikipedia_found'] += 1
                    if wiki_result['image_url']:
                        stats['images_found'] += 1
                    
                    # Update the database
                    success = self.updater.update_species(
                        species_id,
                        wiki_result['wikipedia_url'],
                        wiki_result['image_url']
                    )
                    
                    if success:
                        stats['updated'] += 1
                        logger.info(f"    ✓ Updated")
                    else:
                        stats['errors'] += 1
                        logger.warning(f"    ✗ Update failed")
                else:
                    logger.info(f"    - No data found")
                    if wiki_result.get('error'):
                        stats['errors'] += 1
                
            except Exception as e:
                logger.error(f"    ✗ Error processing {scientific_name}: {e}")
                stats['errors'] += 1
            
            # Rate limiting
            time.sleep(0.5)
        
        return stats
    
    def _print_final_summary(self):
        """Print final processing summary"""
        logger.info(f"\n{'='*60}")
        logger.info("MASS UPDATE FINAL SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"Started: {self.progress.get('started_at', 'Unknown')}")
        logger.info(f"Completed: {datetime.now().isoformat()}")
        logger.info(f"Batches completed: {self.progress['batches_completed']}")
        logger.info(f"Total species processed: {self.progress['total_processed']}")
        logger.info(f"Total species updated: {self.progress['total_updated']}")
        logger.info(f"Total errors: {self.progress['total_errors']}")
        
        if self.progress['total_processed'] > 0:
            success_rate = (self.progress['total_updated'] / self.progress['total_processed']) * 100
            logger.info(f"Overall success rate: {success_rate:.1f}%")
        
        logger.info(f"{'='*60}")
        
        # Clean up progress file if completed successfully
        if self.progress['total_errors'] == 0:
            try:
                os.remove(self.progress_file)
                logger.info("Progress file cleaned up (no errors)")
            except:
                pass
    
    def get_status(self):
        """Get current processing status"""
        if not Path(self.progress_file).exists():
            return "No processing in progress"
        
        logger.info(f"\nCurrent Status:")
        logger.info(f"  Started: {self.progress.get('started_at', 'Unknown')}")
        logger.info(f"  Last offset: {self.progress['last_offset']}")
        logger.info(f"  Batches completed: {self.progress['batches_completed']}")
        logger.info(f"  Total processed: {self.progress['total_processed']}")
        logger.info(f"  Total updated: {self.progress['total_updated']}")
        logger.info(f"  Total errors: {self.progress['total_errors']}")
        
        return self.progress

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Mass update bird taxonomy with Wikipedia URLs and images')
    parser.add_argument('--dry-run', action='store_true', help='Run without making database changes')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of species per batch')
    parser.add_argument('--max-batches', type=int, help='Maximum number of batches to process')
    parser.add_argument('--start-fresh', action='store_true', help='Start fresh (ignore previous progress)')
    parser.add_argument('--status', action='store_true', help='Show current processing status')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    updater = MassWikiUpdater(batch_size=args.batch_size, dry_run=args.dry_run)
    
    if args.status:
        updater.get_status()
    else:
        updater.process_all_species(
            max_batches=args.max_batches,
            start_fresh=args.start_fresh
        )

if __name__ == '__main__':
    main()