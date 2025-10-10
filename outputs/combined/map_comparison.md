# Map File Comparison

## File Types & Sizes

| File Type | Size | Description |
|-----------|------|-------------|
| **Original Maps** | ~34MB each | All data embedded in HTML |
| **Optimized Maps** | ~25KB HTML + ~3.5MB JSON | Data in separate JSON files |
| **WordPress Maps** | ~3.5MB each | All data embedded in single HTML file |

## Key Differences

### 1. **Original Maps** (`all_regions_cities_map.html`, `all_regions_cities_country_map.html`)
- **Size**: ~34MB each
- **Structure**: All data embedded directly in HTML
- **WordPress**: ❌ Too large for WordPress upload limits
- **Use Case**: Local viewing, large file hosting

### 2. **Optimized Maps** (`*_optimized.html` + `*.data.json`)
- **Size**: ~25KB HTML + ~3.5MB JSON
- **Structure**: HTML loads data from external JSON file
- **WordPress**: ❌ WordPress blocks JSON file uploads
- **Use Case**: Web hosting with separate data files

### 3. **WordPress Maps** (`*_wordpress.html`)
- **Size**: ~3.5MB each
- **Structure**: All data embedded in single HTML file
- **WordPress**: ✅ Perfect for WordPress upload
- **Use Case**: WordPress integration, single-file hosting

## Technical Differences

### Data Loading
- **Original**: Data embedded in HTML during generation
- **Optimized**: Data loaded via JavaScript `fetch()` from JSON file
- **WordPress**: Data embedded in HTML during generation

### WordPress Compatibility
- **Original**: ❌ File too large (34MB > WordPress limits)
- **Optimized**: ❌ Requires JSON file (WordPress blocks JSON uploads)
- **WordPress**: ✅ Single HTML file, reasonable size, no external dependencies

### Performance
- **Original**: Fastest (no network requests)
- **Optimized**: Fast HTML load, slower data load
- **WordPress**: Fast (no network requests)

### Maintenance
- **Original**: Regenerate entire HTML for data updates
- **Optimized**: Update JSON file, HTML stays same
- **WordPress**: Regenerate entire HTML for data updates

## Recommendation for WordPress

**Use the WordPress maps** (`*_wordpress.html`) because:

1. ✅ **Single file upload** - No JSON files needed
2. ✅ **Reasonable size** - 3.5MB fits WordPress limits
3. ✅ **No external dependencies** - Everything embedded
4. ✅ **Full functionality** - All features work
5. ✅ **Easy integration** - Just upload and embed

## File Naming Convention

- `*_map.html` = Original large embedded maps
- `*_optimized.html` = HTML + separate JSON files
- `*_wordpress.html` = WordPress-compatible single files
