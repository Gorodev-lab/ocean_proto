import csv
import random
import os
import uuid
from datetime import datetime, timedelta

# Constraints
MIN_LAT, MAX_LAT = 22.0, 32.0
MIN_LON, MAX_LON = -118.0, -105.0

# Count constraints
GFW_RECORDS = 500
OBIS_RECORDS = 200

def random_lat():
    return random.uniform(MIN_LAT, MAX_LAT)

def random_lon():
    return random.uniform(MIN_LON, MAX_LON)

def random_date(start_days_ago=365):
    now = datetime.utcnow()
    delta = timedelta(days=random.randint(0, start_days_ago), 
                      hours=random.randint(0, 23),
                      minutes=random.randint(0, 59))
    return (now - delta).isoformat() + "Z"

def generate_gfw_data(filepath: str):
    vessel_types = ['cargo', 'tanker', 'passenger']
    headers = ['mmsi', 'timestamp', 'lat', 'lon', 'vessel_type']
    
    with open(filepath, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for _ in range(GFW_RECORDS):
            writer.writerow([
                str(random.randint(100000000, 999999999)),
                random_date(),
                random_lat(),
                random_lon(),
                random.choice(vessel_types)
            ])
    print(f"Generated {GFW_RECORDS} vessel records in {filepath}")

def generate_obis_data(filepath: str):
    headers = ['eventDate', 'species', 'decimalLatitude', 'decimalLongitude']
    
    with open(filepath, mode='w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for _ in range(OBIS_RECORDS):
            writer.writerow([
                random_date(),
                'Rhincodon typus',
                random_lat(),
                random_lon()
            ])
    print(f"Generated {OBIS_RECORDS} megafauna records in {filepath}")

if __name__ == "__main__":
    os.makedirs("data", exist_ok=True)
    gfw_path = os.path.join("data", "gfw_data.csv")
    obis_path = os.path.join("data", "obis_data.csv")
    
    generate_gfw_data(gfw_path)
    generate_obis_data(obis_path)
    print("Mock data generation complete.")
