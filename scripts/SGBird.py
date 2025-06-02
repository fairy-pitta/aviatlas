import os
import requests
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client

# Load .env.local
dotenv_path = os.path.join(os.path.dirname(__file__), "..", ".env.local")
load_dotenv(dotenv_path)

API_KEY = os.getenv("EBIRD_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)



def fetch_species_codes_from_ebird():
    """eBird APIからシンガポールの鳥のリストを取得する"""
    url = "https://api.ebird.org/v2/product/spplist/SG"
    headers = {"X-eBirdApiToken": API_KEY}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()  # speciesCode list

def load_taxonomy_csv():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "eBird_taxonomy_v2024.csv")
    return pd.read_csv(csv_path)

def save_sg_birds(species_codes, taxonomy_df):
    added = 0
    for code in species_codes:
        match = taxonomy_df[taxonomy_df['SPECIES_CODE'] == code]
        if not match.empty:
            com_name = match.iloc[0]['PRIMARY_COM_NAME']
            sci_name = match.iloc[0]['SCI_NAME']

            # Check if bird already exists in Supabase
            existing = supabase.table("SGBird").select("id").eq("species_code", code).execute()
            if existing.data:
                continue  # already exists

            # Insert new record
            res = supabase.table("SGBird").insert({
                "species_code": code,
                "com_name": com_name,
                "sci_name": sci_name
            }).execute()
            if res.data:
                added += 1
        else:
            print(f"❌ Species code not found in taxonomy CSV: {code}")

    print(f"✅ Completed. {added} new birds added.")

def main():
    try:
        print("🚀 Fetching species codes from eBird API...")
        species_codes = fetch_species_codes_from_ebird()
        print(f"🌟 {len(species_codes)} species codes retrieved.")

        print("📚 Loading taxonomy CSV...")
        taxonomy_df = load_taxonomy_csv()

        print("💾 Saving SGBird records to Supabase...")
        save_sg_birds(species_codes, taxonomy_df)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()