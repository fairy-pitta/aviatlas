#!/usr/bin/env python3
"""
Simple Wikipedia and Image URL Updater for Bird Taxonomy

A simplified, more reliable version that updates species one by one
with proper error handling and logging.
"""

import os
import sys
import time
import logging
import requests
from typing import Optional, Dict, Any
from urllib.parse import quote
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('simple_wiki_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class SimpleWikiUpdater:
    """Simple Wikipedia and image URL updater"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.supabase = self._init_supabase()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AviAtlas/1.0 (Educational) Bird Taxonomy Updater'
        })
        
        # Statistics
        self.stats = {
            'total_processed': 0,
            'wikipedia_found': 0,
            'images_found': 0,
            'updated': 0,
            'errors': 0,
            'skipped': 0
        }
    
    def _init_supabase(self) -> Optional[Client]:
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
    
    def search_wikipedia(self, scientific_name: str, common_name: str = None) -> Dict[str, Any]:
        """Search for Wikipedia page and image"""
        result = {
            'wikipedia_url': None,
            'image_url': None,
            'success': False,
            'error': None
        }
        
        try:
            # Try scientific name first
            wiki_data = self._get_wikipedia_data(scientific_name)
            
            # If not found and we have common name, try that
            if not wiki_data and common_name:
                wiki_data = self._get_wikipedia_data(common_name)
            
            if wiki_data:
                result.update(wiki_data)
                result['success'] = True
                
                if result['wikipedia_url']:
                    self.stats['wikipedia_found'] += 1
                if result['image_url']:
                    self.stats['images_found'] += 1
            
        except Exception as e:
            result['error'] = str(e)
            logger.error(f"Error searching Wikipedia for {scientific_name}: {e}")
            self.stats['errors'] += 1
        
        return result
    
    def _get_wikipedia_data(self, name: str) -> Optional[Dict[str, Any]]:
        """Get Wikipedia data for a specific name"""
        try:
            # First, try the REST API summary endpoint
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(name)}"
            
            response = self.session.get(summary_url, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Skip disambiguation pages
                if data.get('type') == 'disambiguation':
                    return None
                
                result = {
                    'wikipedia_url': data.get('content_urls', {}).get('desktop', {}).get('page'),
                    'image_url': None
                }
                
                # Get image from thumbnail or original
                if 'thumbnail' in data:
                    result['image_url'] = data['thumbnail'].get('source')
                elif 'originalimage' in data:
                    result['image_url'] = data['originalimage'].get('source')
                
                # If we have a Wikipedia URL but no image, try to get one
                if result['wikipedia_url'] and not result['image_url']:
                    result['image_url'] = self._get_page_image(name)
                
                return result
            
            elif response.status_code == 404:
                # Page not found, this is normal
                return None
            
            else:
                logger.warning(f"Wikipedia API returned {response.status_code} for {name}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout searching for {name}")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request error for {name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {name}: {e}")
            return None
    
    def _get_page_image(self, page_title: str) -> Optional[str]:
        """Get main image from Wikipedia page"""
        try:
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': page_title,
                'prop': 'pageimages',
                'pithumbsize': 400,
                'pilimit': 1
            }
            
            response = self.session.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                
                for page_data in pages.values():
                    if 'thumbnail' in page_data:
                        return page_data['thumbnail']['source']
            
        except Exception as e:
            logger.debug(f"Could not get image for {page_title}: {e}")
        
        return None
    
    def get_species_to_update(self, limit: int = None, offset: int = 0) -> list:
        """Get species that need Wikipedia/image updates"""
        if self.dry_run:
            return [
                {
                    'id': 'sample-1',
                    'scientific_name': 'Corvus corax',
                    'common_name': 'Common Raven'
                },
                {
                    'id': 'sample-2',
                    'scientific_name': 'Passer domesticus', 
                    'common_name': 'House Sparrow'
                }
            ]
        
        try:
            query = self.supabase.table('bird_taxonomy').select(
                'id, scientific_name, common_name, wikipedia_url, image_url'
            ).eq('rank', 'species').is_('wikipedia_url', 'null')
            
            if limit:
                query = query.limit(limit)
            
            if offset:
                query = query.range(offset, offset + (limit or 1000) - 1)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error fetching species: {e}")
            return []
    
    def update_species(self, species_id: str, wikipedia_url: str = None, image_url: str = None) -> bool:
        """Update a single species with Wikipedia and/or image URL"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would update {species_id}:")
            if wikipedia_url:
                logger.info(f"  Wikipedia: {wikipedia_url}")
            if image_url:
                logger.info(f"  Image: {image_url}")
            return True
        
        try:
            update_data = {}
            
            if wikipedia_url:
                update_data['wikipedia_url'] = wikipedia_url
            
            if image_url:
                update_data['image_url'] = image_url
            
            if update_data:
                update_data['updated_at'] = 'now()'
                
                response = self.supabase.table('bird_taxonomy').update(
                    update_data
                ).eq('id', species_id).execute()
                
                if response.data:
                    self.stats['updated'] += 1
                    return True
                else:
                    logger.warning(f"No data returned for update of {species_id}")
                    return False
            else:
                logger.debug(f"No updates needed for {species_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating {species_id}: {e}")
            self.stats['errors'] += 1
            return False
    
    def process_species(self, limit: int = None, start_offset: int = 0) -> None:
        """Process species to add Wikipedia and image URLs"""
        logger.info(f"Starting Wikipedia/image update (dry_run={self.dry_run})")
        
        species_list = self.get_species_to_update(limit, start_offset)
        total_species = len(species_list)
        
        if total_species == 0:
            logger.info("No species found that need updates")
            return
        
        logger.info(f"Found {total_species} species to process")
        
        for i, species in enumerate(species_list, 1):
            self.stats['total_processed'] += 1
            
            scientific_name = species.get('scientific_name')
            common_name = species.get('common_name')
            species_id = species.get('id')
            
            logger.info(f"Processing {i}/{total_species}: {scientific_name}")
            
            # Search for Wikipedia data
            wiki_result = self.search_wikipedia(scientific_name, common_name)
            
            if wiki_result['success']:
                # Update the database
                success = self.update_species(
                    species_id,
                    wiki_result['wikipedia_url'],
                    wiki_result['image_url']
                )
                
                if success:
                    logger.info(f"✓ Updated {scientific_name}")
                else:
                    logger.warning(f"✗ Failed to update {scientific_name}")
            else:
                logger.info(f"- No Wikipedia data found for {scientific_name}")
                self.stats['skipped'] += 1
            
            # Rate limiting - be respectful to Wikipedia
            time.sleep(0.5)
            
            # Progress update every 25 species
            if i % 25 == 0:
                self._print_progress(i, total_species)
        
        self._print_final_stats()
    
    def _print_progress(self, current: int, total: int) -> None:
        """Print progress update"""
        percentage = (current / total) * 100
        logger.info(f"Progress: {current}/{total} ({percentage:.1f}%)")
        logger.info(f"Found: Wiki={self.stats['wikipedia_found']}, Images={self.stats['images_found']}, Updated={self.stats['updated']}")
    
    def _print_final_stats(self) -> None:
        """Print final statistics"""
        logger.info("\n" + "="*60)
        logger.info("WIKIPEDIA AND IMAGE UPDATE SUMMARY")
        logger.info("="*60)
        logger.info(f"Total processed: {self.stats['total_processed']}")
        logger.info(f"Wikipedia URLs found: {self.stats['wikipedia_found']}")
        logger.info(f"Image URLs found: {self.stats['images_found']}")
        logger.info(f"Successfully updated: {self.stats['updated']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Skipped (no data found): {self.stats['skipped']}")
        
        if self.stats['total_processed'] > 0:
            success_rate = (self.stats['updated'] / self.stats['total_processed']) * 100
            logger.info(f"Success rate: {success_rate:.1f}%")
        
        logger.info("="*60)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update bird taxonomy with Wikipedia URLs and images')
    parser.add_argument('--dry-run', action='store_true', help='Run without making database changes')
    parser.add_argument('--limit', type=int, help='Limit number of species to process')
    parser.add_argument('--offset', type=int, default=0, help='Starting offset for processing')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    updater = SimpleWikiUpdater(dry_run=args.dry_run)
    updater.process_species(limit=args.limit, start_offset=args.offset)

if __name__ == '__main__':
    main()