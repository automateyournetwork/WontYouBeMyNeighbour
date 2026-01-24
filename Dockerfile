FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including build tools for netifaces
RUN apt-get update && apt-get install -y \
    net-tools \
    iputils-ping \
    iproute2 \
    curl \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set Python path
ENV PYTHONPATH=/app

# Expose ports
EXPOSE 8888

# Default command (will be overridden by docker run)
CMD ["python3", "wontyoubemyneighbor.py", "--help"]
