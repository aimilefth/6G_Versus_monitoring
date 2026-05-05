FROM aimilefth/base-monitoring-client:latest

# base-monitoring-client already includes requests, protobuf, snappy, etc.
# Add extra model dependencies here when your real model needs them.
# Example:
# RUN pip install --no-cache-dir numpy==2.2.6 scikit-learn==1.6.1

COPY monitor_impl.py /app/monitor_impl.py
COPY model.py /app/model.py