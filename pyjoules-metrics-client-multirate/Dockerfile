FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir pyjoules==0.5.1 prometheus-client==0.23.1
    
# Copy the application source code
COPY power_scraper.py .
COPY prometheus_client_exporter.py .

# Set default environment variables
ENV EXPORTER_PORT=9092
ENV SCRAPE_INTERVAL_SECONDS=0.1
ENV MAX_QUEUE_LEN=1000

# Expose the port the exporter will run on
EXPOSE ${EXPORTER_PORT}

# Command to run the application
CMD ["python", "prometheus_client_exporter.py"]