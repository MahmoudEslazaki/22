"""
Project Pantry Audit — Retail Shelf-Health Scoring
Pipeline script: fetches product data, cleans it, and outputs a scored CSV.
"""

import requests
import json
import csv
from pathlib import Path


def fetch_products():
    """
    Fetch breakfast cereal products from the Open Food Facts API.
    Returns a list of product dicts, or an empty list if the request fails.
    """
    url = "https://world.openfoodfacts.net/api/v2/search"
    params = {
        "categories_tags_en": "breakfast-cereals",
        "page_size": 100,
        "fields": "code,product_name,brands,quantity,categories_tags_en,countries_tags,ingredients_text,nutrition_grades,nutriments"
    }
    headers = {
        "User-Agent": "PantryAudit-mahmoud eslam/1.0 (mahmoudeslam1055@gmail.com)"
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        payload = response.json()
        return payload.get("products", [])
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return []


def filter_products_with_sugar(products):
    """
    Keep only products that have a sugars_100g value.
    Products without it can't be scored against our target.
    """
    return [p for p in products if p.get("nutriments", {}).get("sugars_100g") is not None]
def safe_float(value, default=None):
    """
    Try to convert a value to float. Return `default` if it fails.
    """
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
def parse_quantity_grams(raw):
    """
    Extract the leading number from a free-text quantity string like "70 g" or "1.5 L".
    Returns None for anything that can't be confidently parsed (e.g. "12 x 25 g").
    """
    if not raw:
        return None

    raw = raw.strip()
    number_str = ""
    seen_decimal = False

    for char in raw:
        if char.isdigit():
            number_str += char
        elif char == "." and not seen_decimal and number_str:
            number_str += char
            seen_decimal = True
        else:
            break

    if not number_str:
        return None

    # If there's a stray "x" (multipack) anywhere in the raw string, bail out
    if "x" in raw.lower():
        return None

    return safe_float(number_str)
def scrape_daily_value_sugar():
    """
    Scrape the FDA's official Daily Value for added sugars (in grams)
    from sugar.org. Falls back to 50.0 if the scrape fails.
    """
    url = "https://www.sugar.org/blog/making-sense-of-added-sugars-on-the-new-nutrition-facts-label/"
    headers = {
        "User-Agent": "PantryAudit-mahmoud eslam /1.0 (mahmoudeslam1055@gmail.com)"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html = response.text

        anchor = "the Daily Value is "
        idx = html.find(anchor)
        if idx == -1:
            print("Anchor phrase not found, using fallback value.")
            return 50.0

        window = html[idx + len(anchor): idx + len(anchor) + 40]
        print("Extracted window:", repr(window))

        number_str = window.strip().split()[0]
        return safe_float(number_str, default=50.0)
    except requests.exceptions.RequestException as e:
        print(f"Scrape failed: {e}, using fallback value.")
        return 50.0
def clean_and_engineer(products, daily_value_sugar_g):
    """
    Clean products, impute missing values, and add engineered columns.
    Returns a list of cleaned record dicts.
    """
    # First pass: compute cohort means for imputation
    fiber_values = []
    protein_values = []

    for p in products:
        nutriments = p.get("nutriments", {})
        fiber = nutriments.get("fiber_100g")
        protein = nutriments.get("proteins_100g")
        if fiber is not None:
            fiber_values.append(fiber)
        if protein is not None:
            protein_values.append(protein)

    fiber_mean = sum(fiber_values) / len(fiber_values) if fiber_values else 0
    protein_mean = sum(protein_values) / len(protein_values) if protein_values else 0

    print(f"Cohort fiber mean: {fiber_mean:.2f}, protein mean: {protein_mean:.2f}")

    cleaned_records = []

    for p in products:
        nutriments = p.get("nutriments", {})

        sugars_100g = nutriments.get("sugars_100g")
        # Should always exist since we filtered earlier, but stay safe
        if sugars_100g is None:
            continue

        fat_100g = nutriments.get("fat_100g")
        salt_100g = nutriments.get("salt_100g")
        energy_kcal_100g = nutriments.get("energy-kcal_100g")

        fiber_100g = nutriments.get("fiber_100g")
        if fiber_100g is None:
            fiber_100g = fiber_mean

        proteins_100g = nutriments.get("proteins_100g")
        if proteins_100g is None:
            proteins_100g = protein_mean

        quantity_raw = p.get("quantity")
        quantity_grams = parse_quantity_grams(quantity_raw)

        ingredients_text = p.get("ingredients_text")
        has_ingredients = ingredients_text is not None and ingredients_text != ""

        # Feature engineering
        sugar_pct_dv = (sugars_100g / daily_value_sugar_g) * 100

        if sugar_pct_dv < 5:
            sugar_tier = "low"
        elif sugar_pct_dv <= 20:
            sugar_tier = "moderate"
        else:
            sugar_tier = "high"

        high_sugar_flag = 1 if (sugars_100g / 50.0) >= 0.20 else 0

        record = {
            "barcode": str(p.get("code", "")),
            "product_name": p.get("product_name", ""),
            "brands": p.get("brands", ""),
            "sugars_100g": sugars_100g,
            "fat_100g": fat_100g,
            "fiber_100g": fiber_100g,
            "salt_100g": salt_100g,
            "proteins_100g": proteins_100g,
            "energy_kcal_100g": energy_kcal_100g,
            "quantity_grams": quantity_grams,
            "has_ingredients": has_ingredients,
            "nutrition_grades": p.get("nutrition_grades", ""),
            "sugar_pct_dv": sugar_pct_dv,
            "sugar_tier": sugar_tier,
            "high_sugar_flag": high_sugar_flag,
        }
        cleaned_records.append(record)

    print(f"Cleaned {len(cleaned_records)} records.")
    return cleaned_records
def join_with_warehouse_log(records, log_path="data/raw/warehouse_scan_log.csv"):
    """
    Load the warehouse scan log and attach its fields to each cleaned record,
    matching on barcode. Records with no match keep None for those fields.
    """
    log_lookup = {}
    with open(log_path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            log_lookup[row["barcode"]] = row

    for record in records:
        barcode = record["barcode"]
        log_row = log_lookup.get(barcode)
        if log_row:
            record["shelf_location"] = log_row.get("shelf_location")
            record["units_sold_last_month"] = log_row.get("units_sold_last_month")
        else:
            record["shelf_location"] = None
            record["units_sold_last_month"] = None

    matched = sum(1 for r in records if r["shelf_location"] is not None)
    print(f"Matched {matched} out of {len(records)} records with warehouse log.")
    return records
def apply_min_max_scaling(records, field="sugar_pct_dv", new_field="sugar_pct_dv_scaled"):
    """
    Scale a numeric field to the 0-1 range using min-max scaling.
    """
    values = [r[field] for r in records]
    min_val = values[0]
    max_val = values[0]

    for v in values:
        if v < min_val:
            min_val = v
        if v > max_val:
            max_val = v

    value_range = max_val - min_val

    for r in records:
        if value_range == 0:
            r[new_field] = 0.0
        else:
            r[new_field] = (r[field] - min_val) / value_range

    print(f"Scaled {field}: min={min_val:.2f}, max={max_val:.2f}")
    return records
def validation_check(records):
    """
    For each nutrition_grade, compute the percentage of products
    flagged as high_sugar_flag == 1.
    """
    total_by_grade = {}
    flagged_by_grade = {}

    for r in records:
        grade = r.get("nutrition_grades", "unknown")
        total_by_grade[grade] = total_by_grade.get(grade, 0) + 1
        if r["high_sugar_flag"] == 1:
            flagged_by_grade[grade] = flagged_by_grade.get(grade, 0) + 1

    print("\nValidation Check: high_sugar_flag rate by nutrition_grade")
    for grade in sorted(total_by_grade.keys(), key=str):
        total = total_by_grade[grade]
        flagged = flagged_by_grade.get(grade, 0)
        pct = (flagged / total) * 100
        print(f"  Grade {grade}: {flagged}/{total} flagged ({pct:.1f}%)")


def write_to_csv(records, output_path="data/processed/clean_data.csv"):
    """
    Write cleaned records to a CSV file.
    """
    Path("data/processed").mkdir(parents=True, exist_ok=True)
    fieldnames = list(records[0].keys())

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)

    print(f"\nWrote {len(records)} records to {output_path}")
def main():
    """
    Run the full pipeline end-to-end: fetch, filter, clean, join, scale, validate, save.
    """
    # Step 1: Fetch data from API
    products = fetch_products()
    print(f"Fetched {len(products)} products.")

    if not products:
        print("No products fetched. Exiting.")
        return

    # Save raw data
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    with open("data/raw/products_raw.json", "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

    # Extract barcodes and save them
    barcodes = [str(p["code"]) for p in products if p.get("code")]
    barcodes = list(dict.fromkeys(barcodes))
    Path("data/raw/extracted_ids.txt").write_text("\n".join(barcodes), encoding="utf-8")
    print(f"Extracted {len(barcodes)} unique barcodes.")

    # Step 2: Filter cohort
    filtered_products = filter_products_with_sugar(products)
    print(f"Filtered to {len(filtered_products)} products with sugar data.")

    # Step 3: Scrape daily value
    daily_value_sugar_g = scrape_daily_value_sugar()
    print(f"Daily Value for sugar: {daily_value_sugar_g}")

    # Step 4: Clean and engineer features
    cleaned_records = clean_and_engineer(filtered_products, daily_value_sugar_g)

    # Step 5: Join with warehouse log
    joined_records = join_with_warehouse_log(cleaned_records)

    # Step 6: Apply min-max scaling
    scaled_records = apply_min_max_scaling(joined_records)

    # Step 7: Validation check
    validation_check(scaled_records)

    # Step 8: Write to CSV
    write_to_csv(scaled_records)

    # Report ROI metric
    n_total = len(scaled_records)
    n_flagged = sum(1 for r in scaled_records if r["high_sugar_flag"] == 1)
    pct_reduction = (1 - (n_flagged / n_total)) * 100
    print(f"\nROI: {n_flagged}/{n_total} products flagged high-sugar.")
    print(f"Workload reduction: {pct_reduction:.1f}%")


if __name__ == "__main__":
    main()