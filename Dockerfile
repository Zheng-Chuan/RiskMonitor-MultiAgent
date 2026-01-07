FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
 
# Copy application code
COPY main.py .
COPY src ./src
COPY .env* ./

# Expose MCP server port (if needed for stdio communication, this is optional)
# MCP typically uses stdio, but we expose a port for potential future use
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run the MCP server
CMD ["python", "main.py"]
