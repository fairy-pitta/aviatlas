#!/usr/bin/env python3
"""
Bird Taxonomy Wikipedia and Image URL Updater

This script updates the bird_taxonomy table with Wikipedia URLs and image URLs
for bird species using Wikipedia API and other sources.
"""

import os
import sys
import time
import logging
import requests
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from urllib.parse import quote
import json
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('wiki_image_update.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class WikiImageData:
    """Data structure for Wikipedia and image information"""
    wikipedia_url: Optional[str] = None
    image_url: Optional[str] = None
    description: Optional[str] = None
    success: bool = False
    error: Optional[str] = None

class WikiImageUpdater:
    """Updates bird taxonomy with Wikipedia URLs and images"""
    
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.supabase = self._init_supabase()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'AviAtlas/1.0 (https://github.com/your-repo) Bird Taxonomy Updater'
        })
        
        # Rate limiting
        self.request_delay = 0.5  # seconds between requests
        self.last_request_time = 0
        
        # Statistics
        self.stats = {
            'total_processed': 0,
            'wikipedia_found': 0,
            'images_found': 0,
            'errors': 0,
            'skipped': 0
        }
    
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
    
    def _rate_limit(self):
        """Implement rate limiting for API requests"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        if time_since_last < self.request_delay:
            time.sleep(self.request_delay - time_since_last)
        self.last_request_time = time.time()
    
    def search_wikipedia(self, scientific_name: str, common_name: str = None) -> WikiImageData:
        """Search for Wikipedia page and extract information"""
        result = WikiImageData()
        
        try:
            # Try scientific name first
            wiki_data = self._search_wikipedia_by_name(scientific_name)
            
            # If not found and we have common name, try that
            if not wiki_data and common_name:
                wiki_data = self._search_wikipedia_by_name(common_name)
            
            if wiki_data:
                result.wikipedia_url = wiki_data.get('url')
                result.image_url = wiki_data.get('image')
                result.description = wiki_data.get('description')
                result.success = True
                
                if result.wikipedia_url:
                    self.stats['wikipedia_found'] += 1
                if result.image_url:
                    self.stats['images_found'] += 1
            
        except Exception as e:
            result.error = str(e)
            logger.error(f"Error searching Wikipedia for {scientific_name}: {e}")
            self.stats['errors'] += 1
        
        return result
    
    def _search_wikipedia_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Search Wikipedia for a specific name"""
        self._rate_limit()
        
        # First, search for the page
        search_url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(name)
        
        try:
            response = self.session.get(search_url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if it's a disambiguation page or not found
                if data.get('type') == 'disambiguation':
                    return None
                
                result = {
                    'url': data.get('content_urls', {}).get('desktop', {}).get('page'),
                    'description': data.get('extract'),
                    'image': None
                }
                
                # Try to get the main image
                if 'thumbnail' in data:
                    result['image'] = data['thumbnail'].get('source')
                elif 'originalimage' in data:
                    result['image'] = data['originalimage'].get('source')
                
                # If no image from summary, try to get from page content
                if not result['image'] and result['url']:
                    result['image'] = self._get_wikipedia_image(name)
                
                return result
                
        except requests.exceptions.RequestException as e:
            logger.warning(f"Request failed for {name}: {e}")
        
        return None
    
    def _get_wikipedia_image(self, page_title: str) -> Optional[str]:
        """Get the main image from a Wikipedia page"""
        self._rate_limit()
        
        try:
            # Use Wikipedia API to get page images
            api_url = "https://en.wikipedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': page_title,
                'prop': 'pageimages',
                'pithumbsize': 500,
                'pilimit': 1
            }
            
            response = self.session.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                
                for page_id, page_data in pages.items():
                    if 'thumbnail' in page_data:
                        return page_data['thumbnail']['source']
                    elif 'pageimage' in page_data:
                        # Get full image URL
                        image_title = page_data['pageimage']
                        return self._get_commons_image_url(image_title)
        
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get image for {page_title}: {e}")
        
        return None
    
    def _get_commons_image_url(self, filename: str) -> Optional[str]:
        """Get direct URL for Wikimedia Commons image"""
        self._rate_limit()
        
        try:
            api_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                'action': 'query',
                'format': 'json',
                'titles': f'File:{filename}',
                'prop': 'imageinfo',
                'iiprop': 'url',
                'iiurlwidth': 500
            }
            
            response = self.session.get(api_url, params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                pages = data.get('query', {}).get('pages', {})
                
                for page_data in pages.values():
                    imageinfo = page_data.get('imageinfo', [])
                    if imageinfo and 'thumburl' in imageinfo[0]:
                        return imageinfo[0]['thumburl']
                    elif imageinfo and 'url' in imageinfo[0]:
                        return imageinfo[0]['url']
        
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get Commons image URL for {filename}: {e}")
        
        return None
    
    def get_species_to_update(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get species that need Wikipedia/image updates"""
        if self.dry_run:
            # Return sample data for dry run
            return [
                {
                    'id': 'sample-1',
                    'scientific_name': 'Corvus corax',
                    'common_name': 'Common Raven',
                    'rank': 'species'
                },
                {
                    'id': 'sample-2', 
                    'scientific_name': 'Passer domesticus',
                    'common_name': 'House Sparrow',
                    'rank': 'species'
                }
            ]
        
        try:
            query = self.supabase.table('bird_taxonomy').select(
                'id, scientific_name, common_name, rank, wikipedia_url, image_url'
            ).eq('rank', 'species').is_('wikipedia_url', 'null')
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            return response.data
            
        except Exception as e:
            logger.error(f"Error fetching species data: {e}")
            return []
    
    def update_species_data(self, species_id: str, wiki_data: WikiImageData) -> bool:
        """Update species with Wikipedia and image data"""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would update species {species_id} with:")
            logger.info(f"  Wikipedia URL: {wiki_data.wikipedia_url}")
            logger.info(f"  Image URL: {wiki_data.image_url}")
            return True
        
        try:
            update_data = {}
            
            if wiki_data.wikipedia_url:
                update_data['wikipedia_url'] = wiki_data.wikipedia_url
            
            if wiki_data.image_url:
                update_data['image_url'] = wiki_data.image_url
            
            if update_data:
                update_data['updated_at'] = 'now()'
                
                response = self.supabase.table('bird_taxonomy').update(
                    update_data
                ).eq('id', species_id).execute()
                
                if response.data:
                    logger.info(f"Updated species {species_id}")
                    return True
                else:
                    logger.warning(f"No data returned for species {species_id} update")
                    return False
            else:
                logger.info(f"No updates needed for species {species_id}")
                return True
                
        except Exception as e:
            logger.error(f"Error updating species {species_id}: {e}")
            self.stats['errors'] += 1
            return False
    
    def process_species(self, limit: int = None) -> None:
        """Process species to add Wikipedia and image URLs"""
        logger.info(f"Starting Wikipedia and image update process (dry_run={self.dry_run})")
        
        species_list = self.get_species_to_update(limit)
        total_species = len(species_list)
        
        logger.info(f"Found {total_species} species to process")
        
        for i, species in enumerate(species_list, 1):
            self.stats['total_processed'] += 1
            
            scientific_name = species.get('scientific_name')
            common_name = species.get('common_name')
            species_id = species.get('id')
            
            logger.info(f"Processing {i}/{total_species}: {scientific_name}")
            
            # Skip if already has both URLs
            if species.get('wikipedia_url') and species.get('image_url'):
                logger.info(f"Skipping {scientific_name} - already has URLs")
                self.stats['skipped'] += 1
                continue
            
            # Search for Wikipedia data
            wiki_data = self.search_wikipedia(scientific_name, common_name)
            
            if wiki_data.success:
                # Update the database
                success = self.update_species_data(species_id, wiki_data)
                if not success:
                    self.stats['errors'] += 1
            else:
                logger.warning(f"No Wikipedia data found for {scientific_name}")
                self.stats['skipped'] += 1
            
            # Progress update every 50 species
            if i % 50 == 0:
                self._print_progress(i, total_species)
        
        self._print_final_stats()
    
    def _print_progress(self, current: int, total: int) -> None:
        """Print progress update"""
        percentage = (current / total) * 100
        logger.info(f"Progress: {current}/{total} ({percentage:.1f}%)")
        logger.info(f"Stats: Wiki={self.stats['wikipedia_found']}, Images={self.stats['images_found']}, Errors={self.stats['errors']}")
    
    def _print_final_stats(self) -> None:
        """Print final statistics"""
        logger.info("\n" + "="*60)
        logger.info("WIKIPEDIA AND IMAGE UPDATE SUMMARY")
        logger.info("="*60)
        logger.info(f"Total processed: {self.stats['total_processed']}")
        logger.info(f"Wikipedia URLs found: {self.stats['wikipedia_found']}")
        logger.info(f"Image URLs found: {self.stats['images_found']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info(f"Skipped: {self.stats['skipped']}")
        logger.info("="*60)

def main():
    """Main function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Update bird taxonomy with Wikipedia URLs and images')
    parser.add_argument('--dry-run', action='store_true', help='Run without making database changes')
    parser.add_argument('--limit', type=int, help='Limit number of species to process')
    parser.add_argument('--verbose', '-v', action='store_true', help='Enable verbose logging')
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    updater = WikiImageUpdater(dry_run=args.dry_run)
    updater.process_species(limit=args.limit)

if __name__ == '__main__':
    main()