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
    New contract:
    - remote_write_pusher expects *normalized* records.
    - this dummy implementation just forwards whatever it sees, so nothing will be sent.
    """
    log.warning(
        "Dummy process_data() – remote_write_pusher expects normalized records, "
        "but this dummy does not produce any."
    )
    while not stop_event.is_set():
        try:
            _ = input_queue.get(timeout=1)
        except Empty:
            continue
        # drop on the floor; this is just a base stub
        try:
            output_queue.put([], timeout=1)
        except Full:
            pass
