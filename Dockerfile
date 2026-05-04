FROM python:3.10-slim

# Install system dependencies needed for spatial libraries (gdal, etc)
RUN apt-get update && apt-get install -y \
    build-essential \
    libgdal-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set env vars for GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# Copy dependencies first for caching layers
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and data folders
COPY src ./src
COPY data ./data

# Expose port
EXPOSE 8080

# Start Uvicorn
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8080"]
