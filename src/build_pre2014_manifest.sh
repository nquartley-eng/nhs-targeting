#!/bin/bash
# Builds data/raw/pre2014_manifest.csv: one row per month with NHS Digital file links.
P="https://digital.nhs.uk/data-and-information/publications/statistical/practice-level-prescribing-data"
M=(january february march april may june july august september october november december)
echo "ym,page,zip,pdpi,addr"
for y in 2010 2011 2012 2013; do for i in $(seq 0 11); do ym=$y$(printf %02d $((i+1))); [ $ym -lt 201008 ] && continue
 slug="presentation-level-${M[$i]}-$y"; [ $ym = 201304 ] && slug="gp-practice-prescribing-presentation-level-data-april-2013"
 L=$(curl -s "$P/$slug" | grep -oE 'https://files.digital.nhs.uk/[^"]+' | sort -u)
 z=$(echo "$L" | grep -iE '\.zip$' | head -1); p=$(echo "$L" | grep -i 'PDPI' | head -1); a=$(echo "$L" | grep -i 'ADDR' | head -1)
 echo "$ym,$slug,$z,$p,$a"; done; done
