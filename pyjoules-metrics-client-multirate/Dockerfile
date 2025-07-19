FROM python:3.11-alpine

WORKDIR /app

# Set default environment variables
ENV EXPORTER_PORT=9092
ENV SCRAPE_INTERVAL_SECONDS=0.1

# Install dependencies
RUN pip install --no-cache-dir pyjoules prometheus-client
    
# Copy the application source code
COPY power_scraper.py .
COPY prometheus_client_exporter.py .

# Expose the port the exporter will run on
EXPOSE ${EXPORTER_PORT}

# Command to run the application
CMD ["python", "prometheus_client_exporter.py"]