FROM python:3.11-alpine

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir pyjoules prometheus-client
    
# Copy the application source code
COPY power_scraper.py .
COPY prometheus_client_exporter.py .

# Set default environment variables
ENV EXPORTER_PORT=9091
ENV SCRAPE_INTERVAL_SECONDS=0.1

# Expose the port the exporter will run on
EXPOSE ${EXPORTER_PORT}

# Command to run the application
CMD ["python", "prometheus_client_exporter.py"]