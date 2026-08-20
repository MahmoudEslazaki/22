# Project Pantry Audit — Retail Shelf-Health Scoring

## 1. Objectives

This project builds an automated shelf-health scoring pass over a breakfast
cereal product category, flagging SKUs that would need reformulation review
before inclusion in a retailer's "healthy aisle" program. The goal is to let
a reformulation team focus their manual review time on the subset of
products that actually cross a meaningful sugar threshold, instead of
reviewing the full catalog.

## 2. Resource Audit

| Resource | Detail |
|---|---|
| API access | No key required, but a descriptive `User-Agent` header is mandatory |
| Rate limit | ~10 requests/minute on the search endpoint; we pull once with `page_size=100` |
| Data sources | Open Food Facts search endpoint (1 call), `data/raw/warehouse_scan_log.csv` (generated), 1 web scrape call to sugar.org |
| Estimated time | 4–6 hours |

**Note on the API endpoint:** during development, `world.openfoodfacts.org`
returned repeated `503` errors on the search endpoint (a known, documented
issue with the legacy search backend). We switched requests to the staging
mirror `world.openfoodfacts.net`, which returned data successfully.

## 3. Target Definition
high_sugar_flag = 1 if (sugars_100g / 50.0) >= 0.20
high_sugar_flag = 0 otherwise

This follows the FDA's "5/20 rule": a nutrient is considered "high" at
≥20% of its Daily Value. 50.0 grams is the FDA's official Daily Value for
added sugars, scraped live from sugar.org rather than hardcoded.

## 4. Features Used

1. `sugars_100g`
2. `fat_100g`
3. `fiber_100g`
4. `salt_100g`
5. `proteins_100g`
6. `energy_kcal_100g`
7. `nutrition_grades`
8. `quantity_grams` (parsed from free-text `quantity` field)
9. `brands`

## 5. ROI Metric

Out of 99 cleaned products, **50 products (50.5%)** were flagged as
`high_sugar_flag == 1`. This means a reformulation review team focusing
only on flagged products would cut their manual review workload by
**49.5%**, compared to reviewing the full catalog.

## 6. Validation Check Interpretation

We compared our `high_sugar_flag` against Open Food Facts' own
`nutrition_grades` (a letter grade computed independently of our rule):

| Grade | Flagged Rate |
|---|---|
| A | 18.8% |
| B | 87.5% |
| C | 88.0% |
| D | 28.6% |
| E | 100.0% |

The overall trend is directionally sensible — Grade E products (worst
nutritional quality) are 100% flagged as high-sugar, while Grade A products
(best quality) are flagged only 18.8% of the time. Grades B and C show a
higher flag rate than D, which suggests `nutrition_grades` weighs several
nutrients together (fat, salt, fiber, energy) rather than sugar alone — so
some agreement, but not a 1:1 mapping, is expected between the two flags by
design.

## 7. Source Reliability Note

The Daily Value figure (50g) was scraped from sugar.org, an industry
advocacy site. In this case the page is reporting a federal regulatory
figure (the FDA's official Daily Value) rather than asserting an opinion,
so the number itself is reliable — but in general, figures scraped from
advocacy or industry sites should be cross-checked against a primary
government source when possible.

## 8. How to Run
python src/pipeline.py

This fetches live data, cleans it, joins it with the warehouse log, and
writes the final output to `data/processed/clean_data.csv`.