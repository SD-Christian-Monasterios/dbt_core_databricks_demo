import os
import subprocess

# Get the secret parameter
# Read secret directly from Databricks secret scope
token = dbutils.secrets.get(
    scope="cmonasterios-dbt-secrets",
    key="databricks-token"
)
# Export as env var for dbt
os.environ["DATABRICKS_TOKEN"] = token

# Run dbt
subprocess.run("dbt deps", shell=True, check=True)
subprocess.run("dbt build --target prod", shell=True, check=True)