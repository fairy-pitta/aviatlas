#!/usr/bin/env python3
"""
Batch Update Wikipedia and Image URLs for Bird Taxonomy

This script efficiently updates large numbers of species with Wikipedia URLs
and image URLs using batch processing and parallel requests.
"""

import os
import sys
import time
import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from urllib.parse import quote
import json
from supabase import create_client, Client
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('batch_wiki_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class BatchUpdateResult:
    """Result of batch update operation"""
    total_processed: int = 0
    wikipedia_found: int = 0
    images_found: int = 0
    errors: int = 0
    skipped: int = 0
    duration: float = 0.0

class BatchWikiImageUpdater:
    """Batch updater for Wikipedia URLs and images"""
    
    def __init__(self, dry_run: bool = False, max_workers: int = 5):
        self.dry_run = dry_run
        self.max_workers = max_workers
        self.supabase = self._init_supabase()
        self.result = BatchUpdateResult()
        self.lock = threading.Lock()
        
        # Rate limiting
        self.request_delay = 0.2  # seconds between requests per worker
        self.last_request_times = {}
    
    def _init_supabase(self) -> Client:
        """Initialize Supabase client"""
        url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
        key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
        
        if not url or not key:
            if self.dry_run:
                logger.warning("Supabase credentials not found - running in dry run mode")
                return None
            else:
                raise ValueError("Supabase credentials not found in environment variables")
        
        return create_client(url, key)
    
    def _rate_limit(self, worker_id: int):
        """Implement per-worker rate limiting"""
        current_time = time.time()
        last_time = self.last_request_times.get(worker_id, 0)
        time_since_last = current_time - last_time
        
        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)
        
        self.last_request_times[worker_id] = time.time()
    
    def search_wikipedia_sync(self, scientific_name: str, common_name: str = None, worker_id: int = 0) -> Dict[str, Any]:
        """Synchronous Wikipedia search for thread pool"""
        self._rate_limit(worker_id)
        
        result = {
            'wikipedia_url': None,
            'image_url': None,
            'success': False,
            'error': None
        }
        
        try:
            import requests
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'AviAtlas/1.0 Bird Taxonomy Updater'
            })
            
            # Try scientific name first
            wiki_data = self._search_wikipedia_by_name_sync(session, scientific_name)
            
            # If not found and we have common name, try that
            if not wiki_data and common_name:
                wiki_data = self._search_wikipedia_by_name_sync(session, common_name)
            
            if wiki_data:
                result.update(wiki_data)
                result['success'] = True
                
                with self.lock:
                    if result['wikipedia_url']:
                        self.result.wikipedia_found += 1
                    if result['image_url']:
                        self.result.images_found += 1
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error searching Wikipedia for {scientific_name}: {e}")
            with self.lock:
                self.result.errors += 1
        
        return result
    
    def _search_wikipedia_by_name_sync(self, session, name: str) -> Optional[Dict[str, Any]]:
        """Synchronous Wikipedia search for a specific name"""
        search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(name)
        
        try:
            response = session.get(search_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if it's a disambiguation page or not found
                if data.get('type') == 'disambiguation':
                    return None
                
                result = {
                    'wikipedia_url': data.get('content_urls', {}).get('desktop', {}).get('page'),
                    'image_url': None
                }
                
                # Try to get the main image
                if 'thumbnail' in data:
                    result['image_url'] = data['thumbnail'].get('source')
                elif 'originalimage' in data:
                    result['image_url'] = data['originalimage'].get('source')
                
                # If no image from summary, try to get from page content
                if not result['image_url'] and result['wikipedia_url']:
                    result['image_url'] = self._get_wikipedia_image_sync(session, name)
                
                return result
                
        except Exception as e:
            logger.warning(f"Request failed for {name}: {e}")
        
        return None
    
    def _get_wikipedia_image_sync(self, session, page_title: str) -> Optional[str]:
        """Get the main image from a Wikipedia page synchronously"""
        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': page_title,
                'prop': 'pageimages',
                'pithumbsize': 500,
                'pilimit': 1
            }
            
            response = session.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                
                for page_id, page_data in pages.items():
                    if 'thumbnail' in page_data:
                        return page_data['thumbnail']['source']
        
        except Exception as e:
            logger.warning(f"Failed to get image for {page_title}: {e}")
        
        return None
    
    def get_species_batch(self, offset: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
        """Get a batch of species that need Wikipedia/image updates"""
        if self.dry_run:
            # Return sample data for dry run
            return [
                {
                    'id': f'sample-{i}',
                    'scientific_name': f'Species {i}',
                    'common_name': f'Common Name {i}',
                    'rank': 'species'
                }
                for i in range(offset, min(offset + limit, offset + 10))
            ]
        
        try:
            response = self.supabase.table('bird_taxonomy').select(
                'id, scientific_name, common_name, rank, wikipedia_url, image_url'
            ).eq('rank', 'species').is_('wikipedia_url', 'null').range(
                offset, offset + limit - 1
            ).execute()
            
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching species batch: {e}")
            return []
    
    def update_species_batch(self, updates: List[Dict[str, Any]]) -> int:
        """Update multiple species with Wikipedia and image data"""
        if not updates:
            return 0
        
        if self.dry_run:
            logger.info(f"[DRY RUN] Would update {len(updates)} species")
            for update in updates[:3]:  # Show first 3 as examples
                logger.info(f"  {update['id']}: Wiki={bool(update.get('wikipedia_url'))}, Image={bool(update.get('image_url'))}")
            return len(updates)
        
        try:
            # Prepare batch update data
            batch_data = []
            for update in updates:
                update_data = {'id': update['id']}
                
                if update.get('wikipedia_url'):
                    update_data['wikipedia_url'] = update['wikipedia_url']
                
                if update.get('image_url'):
                    update_data['image_url'] = update['image_url']
                
                if len(update_data) > 1:  # More than just ID
                    update_data['updated_at'] = 'now()'
                    batch_data.append(update_data)
            
            if batch_data:
                # Use upsert for batch updates
                response = self.supabase.table('bird_taxonomy').upsert(
                    batch_data, on_conflict='id'
                ).execute()
                
                updated_count = len(response.data) if response.data else 0
                logger.info(f"Updated {updated_count} species in batch")
                return updated_count
            else:
                logger.info("No updates needed for this batch")
                return 0
                
        except Exception as e:
            logger.error(f"Error updating species batch: {e}")
            with self.lock:
                self.result.errors += len(updates)
            return 0
    
    def process_species_batch(self, species_batch: List[Dict[str, Any]], batch_num: int) -> List[Dict[str, Any]]:
        """Process a batch of species with parallel Wikipedia searches"""
        logger.info(f"Processing batch {batch_num} with {len(species_batch)} species")
        
        updates = []
        
        # Use ThreadPoolExecutor for parallel processing
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_species = {
                executor.submit(
                    self.search_wikipedia_sync,
                    species['scientific_name'],
                    species.get('common_name'),
                    i % self.max_workers
                ): species
                for i, species in enumerate(species_batch)
            }
            
            # Collect results
            for future in as_completed(future_to_species):
                species = future_to_species[future]
                
                try:
                    wiki_result = future.result()
                    
                    if wiki_result['success']:
                        update_data = {'id': species['id']}
                        
                        if wiki_result['wikipedia_url']:
                            update_data['wikipedia_url'] = wiki_result['wikipedia_url']
                        
                        if wiki_result['image_url']:
                            update_data['image_url'] = wiki_result['image_url']
                        
                        if len(update_data) > 1:  # More than just ID
                            updates.append(update_data)
                    
                    with self.lock:
                        self.result.total_processed += 1
                    
                except Exception as e:
                    logger.error(f"Error processing {species['scientific_name']}: {e}")
                    with self.lock:
                        self.result.errors += 1
        
        return updates
    
    def run_batch_update(self, total_limit: int = None, batch_size: int = 50) -> BatchUpdateResult:
        """Run the batch update process"""
        start_time = time.time()
        logger.info(f"Starting batch Wikipedia and image update (dry_run={self.dry_run})")
        logger.info(f"Batch size: {batch_size}, Max workers: {self.max_workers}")
        
        offset = 0
        processed_total = 0
        
        while True:
            # Get next batch of species
            species_batch = self.get_species_batch(offset, batch_size)
            
            if not species_batch:
                logger.info("No more species to process")
                break
            
            # Check if we've reached the limit
            if total_limit and processed_total >= total_limit:
                logger.info(f"Reached processing limit of {total_limit}")
                break
            
            # Process this batch
            batch_num = (offset // batch_size) + 1
            updates = self.process_species_batch(species_batch, batch_num)
            
            # Update database with results
            if updates:
                updated_count = self.update_species_batch(updates)
                logger.info(f"Batch {batch_num}: {updated_count} species updated")
            
            processed_total += len(species_batch)
            offset += batch_size
            
            # Progress update
            logger.info(f"Progress: {processed_total} species processed")
            
            # Small delay between batches
            time.sleep(1)
        
        self.result.duration = time.time() - start_time
        self._print_final_stats()
        
        return self.result
    
    def _print_final_stats(self) -> None:
        """Print final statistics"""
        logger.info("\n" + "="*60)
        logger.info("BATCH WIKIPEDIA AND IMAGE UPDATE SUMMARY")
        logger.info("="*60)
        logger.info(f"Total processed: {self.result.total_processed}")
        logger.info(f"Wikipedia URLs found: {self.result.wikipedia_found}")
        logger.info(f"Image URLs found: {self.result.images_found}")
        logger.info(f"Errors: {self.result.errors}")
        logger.info(f"Skipped: {self.result.skipped}")
        logger.info(f"Duration: {self.result.duration:.2f} seconds")
        if self.result.total_processed > 0:
            logger.info(f"Rate: {self.result.total_processed/self.result.duration:.1f} species/second")
        logger.info("="*60)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch update bird taxonomy with Wikipedia URLs and images')
    parser.add_argument('--dry-run', action='store_true', help='Run without making database changes')
    parser.add_argument('--limit', type=int, help='Limit total number of species to process')
    parser.add_argument('--batch-size', type=int, default=50, help='Number of species per batch')
    parser.add_argument('--workers', type=int, default=5, help='Number of parallel workers')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    updater = BatchWikiImageUpdater(dry_run=args.dry_run, max_workers=args.workers)
    result = updater.run_batch_update(total_limit=args.limit, batch_size=args.batch_size)
    
    # Exit with error code if there were significant errors
    if result.errors > result.total_processed * 0.1:  # More than 10% errors
        sys.exit(1)

if __name__ == '__main__':
    main()