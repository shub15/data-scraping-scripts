#!/bin/bash
# sp500_companies.sh
# Downloads S&P 500 constituents CSV and outputs:
#   Company Name | Location | Founded Year
# Sorted by founding year (ascending)
#
# CSV columns: Symbol, Name, Sector, Sub-Industry, Headquarters Location,
#              Date First Added, CIK, Founded
# NOTE: "Headquarters Location" is a quoted field that may contain a comma
#       (e.g. "Golden Valley, Minnesota"). Python's csv module handles this.

CSV_URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"

python3 - "$CSV_URL" <<'PYEOF'
import csv, sys, urllib.request

url = sys.argv[1]

with urllib.request.urlopen(url) as response:
    lines = response.read().decode("utf-8").splitlines()

reader = csv.reader(lines)
next(reader)  # skip header row

rows = []
for row in reader:
    if len(row) < 8:
        continue
    name     = row[1].strip()  # column 2: Company Name
    location = row[4].strip()  # column 5: Headquarters Location (quoted)
    founded  = row[7].strip()  # column 8: Founded Year

    if not founded.isdigit():
        continue

    rows.append((int(founded), name, location))

rows.sort(key=lambda r: r[0])

print(f"{'Company Name':<45} {'Location':<40} {'Founded'}")
print("-" * 95)
for founded, name, location in rows:
    print(f"{name:<45} {location:<40} {founded}")
PYEOF
