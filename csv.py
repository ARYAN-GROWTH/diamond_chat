import pandas as pd
from sqlalchemy import create_engine

# Step 1: Load CSV
df = pd.read_csv(r"C:/Users/Aryan_Growth_Loop_IO/Downloads/WALMART_DUMP.csv")

# Step 2: Connect to AWS RDS PostgreSQL
engine = create_engine(
    "postgresql://diamond_user:StrongPassword123!@postgres-db-16-3-r1.cimgrjr0vadx.ap-south-1.rds.amazonaws.com/diamond-db-dev?schema=public"
)

# Step 3: Upload the DataFrame
df.to_sql("dev_diamond", engine, if_exists="append", index=False)

print(f"✅ Successfully uploaded {len(df)} rows to dev_diamond on AWS RDS.")
