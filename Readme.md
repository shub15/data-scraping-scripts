# Python Program Readme:
### Scrape all pages, save as CSV (default)
```
python mdcomputers_scraper.py "external harddrive"
```

### Save as both CSV + JSON
```
python mdcomputers_scraper.py "rtx 4090" --format both
```

### Limit to 2 pages, custom output filename
```
python mdcomputers_scraper.py "ssd" --max-pages 2 --output ssd_results
```

### Print only to terminal, no file output
```
python mdcomputers_scraper.py "ram" --no-export
```

### Verbose debug logging
```
python mdcomputers_scraper.py "graphics card" --verbose
```

<br>
<br>

# Shell Script Readme:
### Recommended
```
bash sp500_companies_py.sh
```
or
```
bash sp500_companies.sh
```
<br>
<br>

# 2nd round Readme:
### Connect to the Rfam database on the command line:
```
mysql --user rfamro --host mysql-rfam-public.ebi.ac.uk --port 4497 --database Rfam
```

### Then run the queries:
```
source queries.sql
```
