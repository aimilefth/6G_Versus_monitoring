FROM aimilefth/base-monitoring-client:latest

# add pyjoules
RUN pip install --no-cache-dir pyjoules==0.5.1

# this will overwrite the stub monitor_impl.py from the base image
COPY monitor_impl.py /app/monitor_impl.py