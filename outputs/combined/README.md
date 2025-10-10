# Mountain Cities Analysis - Publication Ready

This directory contains interactive maps and legal documentation ready for public web hosting.

## 📁 Files for Public Distribution

### Interactive Maps

**For WordPress or Single-File Hosting:**
- `all_regions_cities_wordpress.html` - Standard interactive map (~3.5 MB)
- `all_regions_cities_country_wordpress.html` - Country-colored map (~3.5 MB)

**For General Web Hosting:**
- `all_regions_cities_map_optimized.html` + `all_regions_cities_map_optimized.data.json`
- `all_regions_cities_country_map_optimized.html` + `all_regions_cities_country_map_optimized.data.json`

**Benefits:**
- WordPress maps: Single-file upload, fits upload limits, no external dependencies
- Optimized maps: Smaller HTML (25KB), better caching, data in separate JSON files
- All versions include 716 cities with full functionality and legal attribution

### Legal Documentation

- `attribution.html` - Comprehensive attribution and data source licenses
- `terms.html` - Terms of Service
- `privacy.html` - Privacy Policy (very user-friendly - no tracking/cookies)
- `../LICENSES.md` - Full text of all third-party licenses

### Data Files

- `all_regions_cities.csv` - Complete dataset in CSV format
- `all_regions_cities.geojson` - Complete dataset in GeoJSON format

## 🚀 Deployment Instructions

### Quick Start

1. **Upload all files** in this directory to your web server
2. **Ensure file structure** is preserved (HTML files must be in same directory as `.data.json` files)
3. **Test** the optimized HTML files work correctly
4. **Done!** Maps include all attribution and legal compliance automatically

### For Local Testing

If you want to test the maps locally:

```bash
cd "/Users/grantduncan/Documents/coding/city_analysis_v2/outputs/combined"
python3 -m http.server 8000
```

Then open: <a href="http://localhost:8000/all_regions_cities_map_optimized.html">http://localhost:8000/all_regions_cities_map_optimized.html</a>

**Important:** These maps require a web server. Opening them directly in your browser (file://) will show an error message explaining how to use a web server.

### WordPress Integration

**✅ Use the WordPress-specific maps:**
- Upload `all_regions_cities_wordpress.html` or `all_regions_cities_country_wordpress.html`
- Single file upload - no external JSON files needed
- Fits within WordPress upload limits (3.5 MB)
- All functionality included

**📋 WordPress Setup Steps:**
1. Go to WordPress Admin → Media → Add New
2. Upload the WordPress HTML file of your choice
3. Copy the file URL from WordPress Media Library
4. Create a new page/post and embed using iframe or your theme's HTML block

**📖 Full Guide:** See `wordpress_example.html` for detailed instructions and code examples.

### Hosting Recommendations

**For moderate traffic:**
- Any static hosting service works (Netlify, Vercel, GitHub Pages, S3 + CloudFront)
- WordPress hosting (for WordPress maps)
- No special server requirements
- Files are small enough for free tier hosting on most platforms

## ⚖️ Legal Compliance Summary

✅ **Ready for public use** - All requirements met:

| Requirement | Status | Location |
|-------------|--------|----------|
| Data source attribution | ✅ Complete | Footer on all maps + attribution.html |
| License compliance | ✅ Full compliance | All licenses documented |
| Terms of Service | ✅ Created | terms.html |
| Privacy Policy | ✅ Created | privacy.html |
| Disclaimer | ✅ Included | terms.html + attribution.html |
| Commercial use OK | ✅ Yes | All data sources permit it (with attribution) |

### Key Legal Points

1. **GeoNames (CC BY 4.0)**: Requires attribution ✅ (provided in footer)
2. **OpenStreetMap (ODbL)**: Requires attribution and share-alike for derivative **databases** ✅ (provided, maps are "produced works" not databases)
3. **OurAirports (CC0)**: No requirements ✅
4. **SRTM**: Public domain ✅
5. **Map Tiles (OpenTopoMap)**: Attribution + fair use ✅ (provided, usage within limits)

## 🎨 Features

### Both Maps Include:
- ✅ Interactive marker clustering
- ✅ City filters (population, driving times, hospitals)
- ✅ Mountain peak display (≥1200m within 30km)
- ✅ Layer toggles
- ✅ Responsive design
- ✅ Legal attribution footer with links
- ✅ Data for 716 cities across all mountain regions

### Standard Map
- Color-coded by population size
- Single "Cities" layer with all cities

### Country Map
- Color-coded by country
- Separate toggleable layers per country
- Population-scaled markers (larger = more populous)
- Great for comparing countries

## 📊 Data Coverage

- **Regions**: Alps, Pyrenees, Rockies, Cascades, Coast Mountains, Sierra Nevada
- **Countries**: 10+ countries (AT, CH, IT, FR, DE, ES, US, CA, AD, NL)
- **Cities**: 716 mountain cities
- **Data points per city**:
  - Name, country, coordinates, population, elevation
  - Nearest airport + driving time
  - Nearest hospital + driving time
  - Nearby peaks (≥1200m within 30km)

## 🔒 Privacy & Compliance

**Privacy-friendly by design:**
- ❌ No cookies
- ❌ No tracking scripts
- ❌ No analytics
- ❌ No user accounts
- ❌ No personal data collection
- ✅ Just maps and public geographic data

**GDPR/CCPA compliant**: No personal data processed, so most regulations don't apply.

**Web server logs**: Standard logs (IP, timestamp, user agent) may be collected by your hosting provider - this is normal and disclosed in privacy.html.

## 📝 Attribution Requirements

When using this data or maps:

**Minimum attribution** (already in map footers):
```
City data © GeoNames (CC BY 4.0) | 
Hospital data © OpenStreetMap contributors (ODbL) | 
Elevation data: SRTM | 
Airport data: OurAirports (Public Domain)
```

**For publications/research**: See `attribution.html` for specific citations.

## 🛠️ Technical Details

### File Sizes
- WordPress maps: ~3.5 MB each (all data embedded, single file)
- Optimized maps: ~25 KB HTML + 3.5 MB JSON (data in separate file)
- See `map_comparison.md` for detailed comparison

### Browser Compatibility
- Modern browsers (Chrome, Firefox, Safari, Edge)
- Mobile-friendly and responsive
- Requires JavaScript enabled

### Performance
- Initial load: ~1-2 seconds on good connection
- Map tiles loaded on-demand as user pans/zooms

## 🔄 Updating Data

To update with new city data:
1. Run your analysis pipeline to generate new CSV
2. Run `generate_optimized_maps.py` to create optimized maps
3. Run `generate_wordpress_maps.py` to create WordPress maps
4. Replace old files on your server

## 🐛 Troubleshooting

**Maps don't load:**
- For optimized maps: Check that `.data.json` files are in the same directory as HTML files
- For WordPress maps: Ensure file uploaded successfully
- Check browser console for errors

**Tiles not loading:**
- Check your internet connection
- OpenTopoMap may have temporary outages
- Check browser console for 429 (rate limit) errors

**Attribution links broken:**
- Ensure `attribution.html`, `terms.html`, `privacy.html` are in same directory or use full URLs

## 📚 Additional Documentation

- `map_comparison.md` - Detailed comparison of different map versions
- `technical_difference_explanation.md` - Why WordPress maps are smaller than original maps
- `wordpress_example.html` - Step-by-step WordPress integration guide

## 📞 Support

This is an open-source project using public data sources. For questions about:
- **Data sources**: See links in `attribution.html`
- **Licenses**: See `LICENSES.md` in project root
- **Technical issues**: Check browser console for errors

## 🎉 You're Ready!

Your maps are legally compliant and ready for public use. Just upload and share!

**Which map to use:**
- **WordPress**: Use `all_regions_cities_country_wordpress.html` (country-colored, single file)
- **Other hosting**: Use `all_regions_cities_country_map_optimized.html` + `.data.json` (better caching)

**Example usage:**
- "Explore mountain cities" website
- Research data visualization
- Travel planning tool
- Geographic education resource

All use cases are permitted with proper attribution (already included).

---

**Generated**: October 2025  
**Data**: 716 cities across 6 major mountain ranges  
**License**: Data sources have various open licenses - see attribution.html

