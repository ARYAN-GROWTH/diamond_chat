import pandas as pd
from sqlalchemy import create_engine, text
import os

# === CONFIGURATION ===
FILE_PATH = r"C:\Users\Aryan_Growth_Loop_IO\Downloads\WALMART_DUMP.csv"  # Change if needed
DB_URL = (
    "postgresql+psycopg2://diamond_user:StrongPassword123!"
    "@postgres-db-16-3-r1.cimgrjr0vadx.ap-south-1.rds.amazonaws.com:5432/diamond-db-dev"
)
SCHEMA_NAME = "public"
TABLE_NAME = "dev_diamond2"

# === COLUMN MAPPING ===
COLUMN_MAPPING = {
    "item_no": "item_no",
    "Image": "image_url",
    "Date": "date",
    "Company": "company",
    "Group": "group_name",
    "Customer": "customer_name",
    "Jgroup": "jewelry_group",
    "Retail Range": "retail_range",
    "Range": "range_type",
    "MainCategory": "main_category",
    "subcat1": "subcategory",
    "collections": "collection",
    "division": "division",
    "Diamond CTW Fraction": "diamond_ctw_fraction",
    "custom_sd_ctrshap": "custom_sd_ctrshap",
    "sdc_mis_item_status": "sdc_mis_item_status",
    "New Tag": "new_tag",
    "Diamond CTW Range": "diamond_ctw_range",
    "custom_sd_ctrdesc": "custom_sd_ctrdesc",
    "Secondary Sales QTY": "secondary_sales_qty",
    "Secondary Sales Total Cost": "secondary_sales_total_cost",
    "Secondary Sales Value": "secondary_sales_value",
    "Inventory Qty Final": "inventory_qty_final",
    "Inventory Cost Final": "inventory_cost_final",
    "Open Memo Qty": "open_memo_qty",
    "Open Memo Amount": "open_memo_amount",
    "Open Order Qty Asset": "open_order_qty_asset",
    "Open Order Amount Asset": "open_order_amount_asset",
    "Open Order Qty Memo": "open_order_qty_memo",
    "Open Order Amount Memo": "open_order_amount_memo",
}

# === STEP 1: AUTO-DETECT FILE TYPE ===
file_ext = os.path.splitext(FILE_PATH)[1].lower()

print(f"📂 Loading file: {FILE_PATH}")

try:
    if file_ext == ".csv":
        df = pd.read_csv(FILE_PATH, encoding="utf-8", low_memory=False)
    elif file_ext in [".xls", ".xlsx"]:
        df = pd.read_excel(FILE_PATH, engine="openpyxl")
    else:
        raise ValueError(f"❌ Unsupported file format: {file_ext}")
except Exception as e:
    raise RuntimeError(f"❌ Failed to read file: {e}")

print(f"✅ File loaded successfully. Shape: {df.shape}")

# === STEP 2: CLEAN COLUMN NAMES ===
df.columns = (
    df.columns.str.strip()
    .str.replace("\n", " ")
    .str.replace(r"[^0-9a-zA-Z_ ]", "", regex=True)
)

# === STEP 3: STRICT COLUMN MAPPING ===
mapped_columns = {}
for col in df.columns:
    for key, new_col in COLUMN_MAPPING.items():
        if key.lower() == col.lower().strip():  # exact match only
            mapped_columns[col] = new_col
            break

df = df.rename(columns=mapped_columns)
df = df.loc[:, ~df.columns.duplicated()]  # remove duplicate names

# Keep only the expected mapped columns
df = df[[c for c in COLUMN_MAPPING.values() if c in df.columns]]

print("✅ Columns mapped successfully:")
print(df.columns.tolist())

# === STEP 4: CONNECT TO POSTGRESQL ===
print("🔗 Connecting to PostgreSQL...")
engine = create_engine(DB_URL)

with engine.connect() as conn:
    # Create schema if not exists
    conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME};"))

    # Build CREATE TABLE statement dynamically
    columns_with_types = ", ".join([f"{col} TEXT" for col in df.columns])
    create_table_query = f"""
    CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.{TABLE_NAME} (
        id SERIAL PRIMARY KEY,
        {columns_with_types}
    );
    """
    conn.execute(text(create_table_query))
    conn.commit()

# === STEP 5: INSERT INTO DATABASE ===
print(f"⬆️ Inserting {len(df)} rows into {SCHEMA_NAME}.{TABLE_NAME}...")
df.to_sql(TABLE_NAME, engine, schema=SCHEMA_NAME, if_exists="append", index=False)

print(f"✅ Upload complete! {len(df)} rows inserted into {SCHEMA_NAME}.{TABLE_NAME}.")
