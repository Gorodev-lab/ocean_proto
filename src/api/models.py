from pydantic import BaseModel, Field
from typing import List, Dict, Any

class FeatureGeometry(BaseModel):
    type: str
    coordinates: List[List[List[float]]]

class FeatureProperties(BaseModel):
    h3_index: str
    vessel_count: int
    megafauna_count: int
    risk_score: int

class Feature(BaseModel):
    type: str = "Feature"
    geometry: FeatureGeometry
    properties: FeatureProperties

class FeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[Feature]

class VesselRecord(BaseModel):
    mmsi: str
    timestamp: str
    lat: float
    lon: float
    vessel_type: str
