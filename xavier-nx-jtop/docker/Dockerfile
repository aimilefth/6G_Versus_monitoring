FROM aimilefth/base-monitoring-client:latest

# jtop client library.
# The host must also have jetson-stats installed and jtop.service running.
RUN pip install --no-cache-dir jetson-stats

# this will overwrite the stub monitor_impl.py from the base image
COPY monitor_impl.py /app/monitor_impl.py