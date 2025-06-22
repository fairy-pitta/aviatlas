#!/usr/bin/env python3
"""
Check Wikipedia and Image URL Status in Bird Taxonomy

This script checks the current status of Wikipedia URLs and image URLs
in the bird_taxonomy table.
"""

import os
import sys
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def init_supabase() -> Client:
    """Initialize Supabase client"""
    url = os.getenv('NEXT_PUBLIC_SUPABASE_URL')
    key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
    
    if not url or not key:
        raise ValueError("Supabase credentials not found in environment variables")
    
    return create_client(url, key)

def check_status():
    """Check the status of Wikipedia and image URLs"""
    supabase = init_supabase()
    
    print("🔍 Checking Wikipedia and Image URL Status...\n")
    
    # Get overall statistics
    total_species = supabase.table('bird_taxonomy').select('id', count='exact').eq('rank', 'species').execute()
    total_count = total_species.count
    
    # Count species with Wikipedia URLs
    wiki_species = supabase.table('bird_taxonomy').select('id', count='exact').eq('rank', 'species').not_.is_('wikipedia_url', 'null').execute()
    wiki_count = wiki_species.count
    
    # Count species with image URLs
    image_species = supabase.table('bird_taxonomy').select('id', count='exact').eq('rank', 'species').not_.is_('image_url', 'null').execute()
    image_count = image_species.count
    
    # Count species with both
    both_species = supabase.table('bird_taxonomy').select('id', count='exact').eq('rank', 'species').not_.is_('wikipedia_url', 'null').not_.is_('image_url', 'null').execute()
    both_count = both_species.count
    
    print(f"📊 **Overall Statistics:**")
    print(f"   Total species: {total_count:,}")
    print(f"   With Wikipedia URLs: {wiki_count:,} ({wiki_count/total_count*100:.1f}%)")
    print(f"   With image URLs: {image_count:,} ({image_count/total_count*100:.1f}%)")
    print(f"   With both URLs: {both_count:,} ({both_count/total_count*100:.1f}%)")
    print()
    
    # Show some examples of updated species
    examples = supabase.table('bird_taxonomy').select(
        'scientific_name, common_name, wikipedia_url, image_url'
    ).eq('rank', 'species').not_.is_('wikipedia_url', 'null').limit(5).execute()
    
    if examples.data:
        print("🐦 **Examples of Updated Species:**")
        for species in examples.data:
            print(f"   • {species['scientific_name']} ({species['common_name']})")
            print(f"     Wikipedia: {species['wikipedia_url'][:60]}..." if len(species['wikipedia_url']) > 60 else f"     Wikipedia: {species['wikipedia_url']}")
            if species['image_url']:
                print(f"     Image: {species['image_url'][:60]}..." if len(species['image_url']) > 60 else f"     Image: {species['image_url']}")
            print()
    
    # Show species that still need updates
    remaining = supabase.table('bird_taxonomy').select(
        'scientific_name, common_name'
    ).eq('rank', 'species').is_('wikipedia_url', 'null').limit(5).execute()
    
    if remaining.data:
        print("⏳ **Species Still Needing Updates:**")
        for species in remaining.data:
            print(f"   • {species['scientific_name']} ({species['common_name']})")
        print()
    
    print("✅ Status check complete!")

if __name__ == '__main__':
    try:
        check_status()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)