import os
import sys
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client, Client


API_KEY = os.getenv("EBIRD_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# taxonomy.csv
csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "eBird_taxonomy_v2024.csv")
taxonomy_df = pd.read_csv(csv_path)

# 再開ファイル
progress_path = os.path.join(os.path.dirname(__file__), "..", "last_successful_date.txt")
def get_start_date(default="2010-01-09"):
    if os.path.exists(progress_path):
        with open(progress_path, "r") as f:
            return datetime.strptime(f.read().strip(), "%Y-%m-%d")
    return datetime.strptime(default, "%Y-%m-%d")

def save_progress(date):
    with open(progress_path, "w") as f:
        f.write(date.strftime("%Y-%m-%d"))

# ---------------- メイン処理 ---------------- #
def run_sync():
    REGION = "SG"
    START_DATE = get_start_date()
    END_DATE = datetime.now()
    RATE_SLEEP = 0.5
    BATCH_SIZE = 100
    INSERT_PAUSE = 0.1

    current = START_DATE
    total_inserted = 0

    print(f"🚀 Starting eBird sync from {current.date()} to {END_DATE.date()}")

    while current <= END_DATE:
        date_str = current.strftime("%Y-%m-%d")
        print(f"\n📅 Fetching data for {date_str}...")
        url = f"https://api.ebird.org/v2/data/obs/{REGION}/historic/{current.year}/{current.month}/{current.day}"

        try:
            r = requests.get(url, headers={"X-eBirdApiToken": API_KEY})
            r.raise_for_status()
            rows = r.json()
        except Exception as e:
            print(f"🔴 Error fetching {date_str}: {e}")
            raise  # ここで例外を上げて再実行へ

        day_inserted = 0
        batch_count = 0
        bird_batch = []

        for obs in rows:
            sp_code = obs.get("speciesCode")
            obs_dt_raw = obs.get("obsDt")
            lat = obs.get("lat")
            lng = obs.get("lng")

            if not (sp_code and obs_dt_raw and lat and lng):
                continue

            # Check if species_code exists
            species_lookup = supabase.table("SGBird").select("species_code").eq("species_code", sp_code).execute()
            if not species_lookup.data:
                match = taxonomy_df[taxonomy_df["SPECIES_CODE"] == sp_code]
                if not match.empty:
                    print(f"➕ Adding species: {sp_code}")
                    supabase.table("SGBird").insert({
                        "species_code": sp_code,
                        "com_name": match.iloc[0]["PRIMARY_COM_NAME"],
                        "sci_name": match.iloc[0]["SCI_NAME"]
                    }).execute()
                else:
                    print(f"⚠️ Skipped unknown species: {sp_code}")
                    continue

            try:
                obs_dt = datetime.fromisoformat(obs_dt_raw).date().isoformat()
            except:
                continue

            existing = supabase.table("ObservationSG").select("id").match({
                "obs_dt": obs_dt,
                "lat": lat,
                "lng": lng
            }).execute()

            if existing.data:
                obs_id = existing.data[0]["id"]
            else:
                res = supabase.table("ObservationSG").insert({
                    "obs_dt": obs_dt,
                    "lat": lat,
                    "lng": lng,
                    "location_name": obs.get("locationName"),
                    "location_id": obs.get("locID") or obs.get("locationID"),
                    "obs_valid": obs.get("obsValid", True),
                    "obs_reviewed": obs.get("obsReviewed", False),
                    "user_display_name": obs.get("userDisplayName"),
                    "subnational1_name": obs.get("subnational1Name"),
                    "subnational2_name": obs.get("subnational2Name"),
                }).execute()
                obs_id = res.data[0]["id"]

            bird_batch.append({
                "observation_id": obs_id,
                "species_code": sp_code,
                "how_many": obs.get("howMany")
            })

            if len(bird_batch) >= BATCH_SIZE:
                supabase.table("ObservationSGBird").insert(bird_batch).execute()
                print(f"  ✅ Batch inserted ({len(bird_batch)})")
                day_inserted += len(bird_batch)
                total_inserted += len(bird_batch)
                batch_count += 1
                bird_batch.clear()
                time.sleep(INSERT_PAUSE)

        if bird_batch:
            supabase.table("ObservationSGBird").insert(bird_batch).execute()
            print(f"  ✅ Final batch inserted ({len(bird_batch)})")
            day_inserted += len(bird_batch)
            total_inserted += len(bird_batch)
            batch_count += 1
            bird_batch.clear()

        print(f"✅ Done {date_str}: {day_inserted} records in {batch_count} batch(es). Total so far: {total_inserted}")
        save_progress(current)
        current += timedelta(days=1)
        time.sleep(RATE_SLEEP)

    print(f"\n🎉 All done! Total inserted: {total_inserted}")


# ---------------- 再実行ラッパー ---------------- #
if __name__ == "__main__":
    try:
        run_sync()
    except Exception as e:
        print(f"🛑 Script crashed with error: {e}")
        print("🔁 Restarting in 5 minutes...")
        time.sleep(300)  # 5 minutes
        os.execv(sys.executable, [sys.executable] + sys.argv)
