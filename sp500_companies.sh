#!/bin/bash
# sp500_companies.sh
# Downloads S&P 500 constituents CSV and outputs:
#   Company Name | Location | Founded Year
# Sorted by founding year (ascending)

CSV_URL="https://raw.githubusercontent.com/datasets/s-and-p-500-companies/refs/heads/main/data/constituents.csv"

# Fetch CSV and process with awk
# CSV columns: Symbol, Name, Sector, Sub-Industry, Headquarters Location, Date First Added, CIK, Founded
curl -s "$CSV_URL" | awk -F',' '
NR == 1 {
    # Print header
    printf "%-45s %-35s %s\n", "Company Name", "Location", "Founded"
    printf "%s\n", "--------------------------------------------------------------------------------------------------------------------------------------"
    next
}
{
    # Handle quoted fields (some fields may contain commas inside quotes)
    # Fields: Symbol(1), Name(2), Sector(3), Sub-Industry(4), HQ Location(5), Date Added(6), CIK(7), Founded(9)
    name     = $2
    location = $5
    founded  = $9

    # Strip surrounding double-quotes if present
    gsub(/^"/, "", name);     gsub(/"$/, "", name)
    gsub(/^"/, "", location); gsub(/"$/, "", location)
    gsub(/^"/, "", founded);  gsub(/"$/, "", founded)
    gsub(/\r/, "", founded)   # strip Windows carriage returns

    # Skip rows with missing founding year
    if (founded == "" || founded !~ /^[0-9]+$/) next

    printf "%-45s %-35s %s\n", name, location, founded
}
' | sort -t$'\t' -k3 -n 2>/dev/null || \
# Fallback: sort by the Founded column (field at fixed character position)
curl -s "$CSV_URL" | awk -F',' '
NR == 1 { next }
{
    name     = $2; location = $5; founded  = $9
    gsub(/^"/, "", name);     gsub(/"$/, "", name)
    gsub(/^"/, "", location); gsub(/"$/, "", location)
    gsub(/^"/, "", founded);  gsub(/"$/, "", founded)
    gsub(/\r/, "", founded)
    if (founded == "" || founded !~ /^[0-9]+$/) next
    print founded "|" name "|" location
}
' | sort -t'|' -k1 -n | awk -F'|' '
BEGIN {
    printf "%-45s %-35s %s\n", "Company Name", "Location", "Founded"
    printf "%s\n", "--------------------------------------------------------------------------------------------------------------------------------------"
}
{ printf "%-45s %-35s %s\n", $2, $3, $1 }'
