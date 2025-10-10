#!/usr/bin/env python3
"""
Generate WordPress-compatible single-file maps.

These maps embed all data directly in the HTML file, making them perfect
for WordPress upload without needing to upload separate JSON files.
"""

import json
import csv
from pathlib import Path
from city_analysis.map_utils import save_wordpress_map, save_wordpress_country_map

def main():
    # Path to combined data
    combined_dir = Path("outputs/combined")
    csv_file = combined_dir / "all_regions_cities.csv"
    
    print("🏔️ Generating WordPress-Compatible Maps")
    print("=" * 50)
    
    print("Loading city data...")
    # Read CSV and convert to records
    records = []
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean up the record
            clean_row = {}
            for k, v in row.items():
                if v == '':
                    continue
                clean_row[k] = v
            
            # Parse peaks JSON if present
            if 'peaks_higher1200_within30km' in clean_row:
                try:
                    peaks_str = clean_row['peaks_higher1200_within30km']
                    if peaks_str and peaks_str != '[]':
                        clean_row['peaks_higher1200_within30km'] = json.loads(peaks_str)
                    else:
                        clean_row['peaks_higher1200_within30km'] = []
                except:
                    clean_row['peaks_higher1200_within30km'] = []
            
            records.append(clean_row)
    
    print(f"Loaded {len(records)} cities")
    
    # Generate WordPress-compatible standard map
    print("\n🗺️ Generating WordPress standard map...")
    html_path = save_wordpress_map(
        records,
        combined_dir / "all_regions_cities_wordpress.html",
        tiles="OpenTopoMap",
        map_title="Mountain Cities - All Regions"
    )
    print(f"  ✅ Created: {html_path.name} ({html_path.stat().st_size:,} bytes)")
    
    # Generate WordPress-compatible country map
    print("\n🌍 Generating WordPress country map...")
    html_path = save_wordpress_country_map(
        records,
        combined_dir / "all_regions_cities_country_wordpress.html",
        tiles="OpenTopoMap",
        map_title="Mountain Cities by Country"
    )
    print(f"  ✅ Created: {html_path.name} ({html_path.stat().st_size:,} bytes)")
    
    print("\n🎉 WordPress Maps Generated Successfully!")
    print("\n📋 WordPress Integration:")
    print("  1. Upload the HTML files to WordPress Media Library")
    print("  2. No JSON files needed - everything is embedded!")
    print("  3. Use iframe to embed in WordPress pages")
    print("  4. Perfect for WordPress - no file restrictions!")
    
    print(f"\n📁 Files ready for WordPress:")
    print(f"  • {combined_dir / 'all_regions_cities_wordpress.html'}")
    print(f"  • {combined_dir / 'all_regions_cities_country_wordpress.html'}")
    
    print("\n🔧 WordPress iframe code:")
    print('<iframe src="https://yoursite.com/wp-content/uploads/all_regions_cities_wordpress.html" width="100%" height="600" frameborder="0"></iframe>')

if __name__ == "__main__":
    main()
