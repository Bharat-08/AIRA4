# Use the official Python 3.11 slim image
FROM python:3.11-slim

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies that might be required by Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copy the requirements file first to leverage Docker's layer caching
COPY requirements.txt /app/requirements.txt

# Install all Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's backend code
COPY app /app/app
COPY alembic /app/alembic
COPY alembic.ini /app/alembic.ini

# Copy the root-level Python scripts that your services depend on
COPY test_searcher.py /app/test_searcher.py
COPY ranker.py /app/ranker.py
COPY my_database.py /app/my_database.py

# Ensure the new searcher module is included for both import paths:
# - /app/searcher_apollo_web.py (root-level import)
# - /app/app/searcher_apollo_web.py (package-level import used by some contexts)
COPY searcher_apollo_web.py /app/searcher_apollo_web.py
COPY searcher_apollo_web.py /app/app/searcher_apollo_web.py

# Set an environment variable to ensure Python output is sent directly to the terminal
ENV PYTHONUNBUFFERED=1

# The command to run the application using Uvicorn
# The --reload flag enables auto-reloading for development
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
