import io
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from playwright.sync_api import sync_playwright

BASE_URL = "http://www.bantaypresyo.da.gov.ph/tbl_fruits.php"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    )
    page = context.new_page()

    print("Navigating to site...")
    page.goto(BASE_URL, wait_until="domcontentloaded")

    # 1. Select Region
    print("Selecting Region...")
    page.wait_for_selector("select#region")
    page.select_option("select#region", label="NCR (NATIONAL CAPITAL REGION)")

    # 2. Extract Commodity category options
    page.wait_for_selector("select#commodity:not([disabled])")
    commodity_options = page.eval_on_selector_all(
        "select#commodity option",
        "options => options.map(o => ({ value: o.value, text: o.text.trim() })).filter(o => o.value !== '')"
    )

    print("\n--- Available Commodity Categories ---")
    for idx, opt in enumerate(commodity_options, 1):
        print(f"[{idx}] {opt['text']}")

    # Prompt user for Category
    selected_idx = None
    while selected_idx is None:
        choice = input(f"\nSelect commodity category [1-{len(commodity_options)}]: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(commodity_options):
            selected_idx = int(choice) - 1
        else:
            print("Invalid selection. Please enter a valid number.")

    selected_category = commodity_options[selected_idx]
    print(f"\nLoading data for: {selected_category['text']}...")

    # Select chosen category
    page.select_option("select#commodity", value=selected_category["value"])
    page.wait_for_load_state("networkidle")
    page.wait_for_selector("table tr:nth-child(2)", timeout=15000)

    # Extract rendered HTML
    tables = pd.read_html(io.StringIO(page.content()))
    browser.close()

if not tables:
    print("No tables found.")
    exit()

# DATA PARSING & ITEM SELECTION
raw_df = tables[0]

# Flatten MultiIndex columns if present, strip whitespace
if isinstance(raw_df.columns, pd.MultiIndex):
    raw_df.columns = [' '.join(col).strip() for col in raw_df.columns.values]
else:
    raw_df.columns = raw_df.columns.astype(str).str.strip()

# Identify the item/commodity column (usually first column)
item_col = raw_df.columns[0]
raw_df = raw_df.dropna(subset=[item_col]).copy()
raw_df = raw_df[raw_df[item_col].astype(str).str.strip() != ""]

items_list = raw_df[item_col].drop_duplicates().tolist()

print(f"\n--- Items available in {selected_category['text']} ---")
for idx, item in enumerate(items_list, 1):
    print(f"[{idx}] {item}")

# Prompt user for specific item to compare
item_idx = None
while item_idx is None:
    choice = input(f"\nSelect item to compare across markets [1-{len(items_list)}]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(items_list):
        item_idx = int(choice) - 1
    else:
        print("Invalid selection. Please enter a valid number.")

selected_item = items_list[item_idx]

# RESHAPE & CLEAN MARKET PRICES
# Filter row for the chosen item
item_row = raw_df[raw_df[item_col] == selected_item].iloc[0]

# Non-market columns to exclude from market comparison
metadata_keywords = ['commodity', 'item', 'spec', 'unit', 'prevailing', 'average', 'mean']
market_cols = [
    col for col in raw_df.columns 
    if not any(k in col.lower() for k in metadata_keywords)
]

# Build Market vs Price DataFrame
market_records = []
for col in market_cols:
    val = str(item_row[col]).strip()
    # Clean currency / text formatting
    cleaned = re.sub(r'[^\d.]', '', val)
    if cleaned:
        try:
            numeric_price = float(cleaned)
            market_records.append({'Market': col, 'Price': numeric_price})
        except ValueError:
            pass

df_comparison = pd.DataFrame(market_records)

if df_comparison.empty:
    print(f"No numeric price entries found across markets for '{selected_item}'.")
    exit()

# Sort markets by price descending
df_comparison = df_comparison.sort_values(by='Price', ascending=False).reset_index(drop=True)

# VISUALIZATION
sns.set_theme(style="whitegrid")
plt.figure(figsize=(12, max(6, len(df_comparison) * 0.4)))

ax = sns.barplot(
    data=df_comparison,
    x='Price',
    y='Market',
    hue='Market',
    palette="mako",
    legend=False
)

plt.title(f'Market Price Comparison: {selected_item} (NCR)', fontsize=15, pad=20, fontweight='bold')
plt.xlabel('Price in Philippine Peso (PHP)', fontsize=12)
plt.ylabel('Market', fontsize=12)

# Value annotations on each bar
max_price = df_comparison['Price'].max()
for i, v in enumerate(df_comparison['Price']):
    ax.text(v + (max_price * 0.01), i, f'₱{v:,.2f}', va='center', fontsize=9, fontweight='bold')

plt.xlim(0, max_price * 1.15)
sns.despine(left=True, bottom=True)
plt.tight_layout()
plt.show()