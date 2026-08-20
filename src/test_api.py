import requests

url = url = "https://world.openfoodfacts.net/api/v2/search"
params = {
    "categories_tags_en": "breakfast-cereals",
    "page_size": 5,
    "fields": "code,product_name,brands"
}
headers = {
    "User-Agent": "PantryAuditTest/1.0 (test@example.com)"
}

response = requests.get(url, params=params, headers=headers)
print("Status code:", response.status_code)
print(response.json())