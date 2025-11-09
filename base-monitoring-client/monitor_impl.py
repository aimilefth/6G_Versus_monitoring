# base-monitoring-client/monitor_impl.py
import logging
import time
from queue import Empty, Full

log = logging.getLogger("monitor_impl")

def get_power(output_queue, scrape_interval_s, stop_event):
    """
    Dummy implementation. Real images must overwrite this file
    and provide their own get_power().
    """
    log.warning("Using dummy monitor_impl.get_power() – no data will be produced.")
    while not stop_event.is_set():
        time.sleep(scrape_interval_s)

def process_data(input_queue, output_queue, stop_event):
    """
    Dummy pass-through. Real images may normalize/aggregate here.
    """
    log.warning("Using dummy monitor_impl.process_data() – nothing to process.")
    while not stop_event.is_set():
        try:
            item = input_queue.get(timeout=1)
        except Empty:
            continue
        try:
            output_queue.put(item, timeout=1)
        except Full:
            log.warning("process_data: output queue full; dropping item")
