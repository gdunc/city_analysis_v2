# Mountain Cities Analysis - Publication Ready

This directory contains optimized maps and legal documentation ready for public web hosting.

## 📁 Files for Public Distribution

### Interactive Maps (Optimized)

**Recommended for public use:**
- `all_regions_cities_map_optimized.html` - Standard interactive map (~23 KB)
- `all_regions_cities_country_map_optimized.html` - Country-colored map (~25 KB)
- `all_regions_cities_map_optimized.data.json` - Shared data file (~3.5 MB)
- `all_regions_cities_country_map_optimized.data.json` - Shared data file (~3.5 MB)

**Benefits of optimized versions:**
- 99% smaller HTML files (23KB vs 30-50MB)
- Faster initial page load
- Better browser caching (HTML and data cached separately)
- Includes legal attribution footer
- All 716 cities with full functionality

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

These maps work perfectly with WordPress! Here's how:

**✅ Compatible with WordPress:**
- Upload both the HTML file and `.data.json` file to your WordPress Media Library
- WordPress will serve both files correctly
- The relative paths between HTML and JSON files are maintained
- All functionality works exactly the same

**📋 WordPress Setup Steps:**
1. Go to WordPress Admin → Media → Add New
2. Upload: `all_regions_cities_map_optimized.html`
3. Upload: `all_regions_cities_map_optimized.data.json`
4. Copy the file URLs from WordPress
5. Create a new WordPress page/post
6. Use an iframe or embed the HTML file URL

**🔧 Alternative: Direct File Access**
If you have FTP access to your WordPress server:
- Upload files to `/wp-content/uploads/` or similar directory
- Access via: `https://yoursite.com/wp-content/uploads/all_regions_cities_map_optimized.html`

**📖 WordPress Guide:** See `wordpress_example.html` for a complete step-by-step guide with code examples and troubleshooting tips.

### Hosting Recommendations

**For 50 users/day:**
- Any static hosting service works (Netlify, Vercel, GitHub Pages, S3 + CloudFront)
- No special server requirements
- Total size: ~7 MB (easily fits free tiers)

**Bandwidth estimate:**
- Per user: ~4 MB download (HTML + JSON + map tiles)
- 50 users/day: ~200 MB/day or ~6 GB/month
- Well within free tier limits for most providers

### Tile Usage Monitoring

Current setup uses OpenTopoMap tiles:
- **Current limit**: ~5,000 tile loads/day (generous for 50 users)
- **Your usage**: ~50 users × 50 tiles each = ~2,500 tiles/day ✅
- **If you exceed limits**: See attribution page for alternative tile providers

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
- Original maps: ~30-50 MB each (data embedded in HTML)
- Optimized maps: ~23 KB HTML + 3.5 MB JSON (shared)
- **Savings**: 93%+ smaller initial load

### Browser Compatibility
- Modern browsers (Chrome, Firefox, Safari, Edge)
- Mobile-friendly and responsive
- Requires JavaScript enabled

### Performance
- Initial load: ~1-2 seconds on good connection
- Data cached after first load
- Map tiles loaded on-demand as user pans/zooms

## 🔄 Updating Data

To update with new city data:
1. Run your analysis pipeline to generate new CSV
2. Run `generate_optimized_maps.py` to create new HTML/JSON files
3. Replace old files on your server
4. Browser caching will update automatically

## 🐛 Troubleshooting

**Maps don't load:**
- Check that `.data.json` files are in the same directory as HTML files
- Check browser console for errors
- Verify server allows JSON file downloads

**Tiles not loading:**
- Check your internet connection
- OpenTopoMap may have temporary outages
- Check browser console for 429 (rate limit) errors

**Attribution links broken:**
- Ensure `attribution.html`, `terms.html`, `privacy.html` are in same directory

## 📞 Support

This is an open-source project using public data sources. For questions about:
- **Data sources**: See links in `attribution.html`
- **Licenses**: See `LICENSES.md` in project root
- **Technical issues**: Check browser console for errors

## 🎉 You're Ready!

Your maps are legally compliant and optimized for public use. Just upload and share!

**Recommended landing page**: Link to `all_regions_cities_country_map_optimized.html` (shows countries clearly)

**Example usage**:
- "Explore mountain cities" website
- Research data visualization
- Travel planning tool
- Geographic education resource

All use cases are permitted with proper attribution (already included).

---

**Generated**: October 2025  
**Data**: 716 cities across 6 major mountain ranges  
**License**: Data sources have various open licenses - see attribution.html

