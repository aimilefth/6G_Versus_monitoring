from pyJoules.energy_meter import measure_energy
from pyJoules.handler import EnergyHandler, UnconsistantSamplesError
from pyJoules.energy_trace import EnergyTrace, EnergySample
import time
import datetime

class NoSampleProcessedError(Exception):
    """
    Exception raised when trying to get data from DictHandler without processing any sample before.
    """

class DictHandler(EnergyHandler):
    """
    Handle energy samples and convert them into a dictionary without using Pandas.
    """
    def __init__(self):
        super().__init__()  # Initialize the parent EnergyHandler class

    def get_single_dictionary(self) -> dict:
        """
        Returns the data of a single energy sample as a dictionary.
        Asserts that there is exactly one energy sample.
        """
        if not self.traces:
            raise NoSampleProcessedError("No samples have been processed.")

        # Use the inherited _flaten_trace method
        flattened_trace = self._flaten_trace()
        samples = list(flattened_trace)

        if len(samples) != 1:
            raise ValueError(f"Expected exactly one sample, but got {len(samples)}.")

        sample = samples[0]
        result = {
            'timestamp': sample.timestamp,
            'tag': sample.tag,
            'duration': sample.duration,
        }
        result.update(sample.energy)
        return result

    def reset(self) -> None:
        """
        Resets the handler by clearing all stored traces.
        """
        self.traces = []

class power_scraper:
    def __init__(self) -> None:
        self.dict_handler = DictHandler()

    def get_power(self, interval: float= 0.1):
        @measure_energy(handler=self.dict_handler)
        def waste_time_sleep(interval: float= 0.1):
            time.sleep(interval)
        waste_time_sleep(interval)
        data = self.dict_handler.get_single_dictionary()
        self.dict_handler.reset()
        data['timestamp'] = datetime.datetime.utcnow().isoformat()
        return data