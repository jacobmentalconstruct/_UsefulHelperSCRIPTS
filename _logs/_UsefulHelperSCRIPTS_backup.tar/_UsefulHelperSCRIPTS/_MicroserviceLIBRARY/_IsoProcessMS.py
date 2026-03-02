import multiprocessing as mp
import logging
import logging.handlers
import time
import queue
from typing import Any, Dict, Optional
from microservice_std_lib import service_metadata, service_endpoint

def _isolated_worker(result_queue: mp.Queue, log_queue: mp.Queue, payload: Any, config: Dict[str, Any]):
    """
    Entry point for the child process.
    Configures a logging handler to send records back to the parent.
    Note: Must remain top-level for multiprocessing pickling compatibility.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in root.handlers[:]:
        root.removeHandler(h)
    qh = logging.handlers.QueueHandler(log_queue)
    root.addHandler(qh)
    log = logging.getLogger('IsoWorker')
    try:
        log.info(f'Worker PID {mp.current_process().pid} started.')
        log.info('Loading heavy libraries (Torch/Transformers)...')
        time.sleep(0.2)
        model_name = config.get('model_name', 'default-model')
        log.info(f"Initializing model '{model_name}'...")
        for i in range(1, 4):
            time.sleep(0.3)
            log.info(f'Processing chunk {i}/3...')
        processed_data = f'Processed({payload}) via {model_name}'
        log.info('Work complete. Returning result.')
        result_queue.put({'success': True, 'data': processed_data})
    except Exception as e:
        log.exception('Critical failure in worker process.')
        result_queue.put({'success': False, 'error': str(e)})

@service_metadata(name='IsoProcess', version='1.0.0', description='Spawns isolated processes with real-time logging feedback.', tags=['process', 'isolation', 'safety'], capabilities=['process:spawn'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class IsoProcessMS:
    """
    The Safety Valve: Spawns isolated processes with real-time logging feedback.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.timeout = self.config.get('timeout_seconds', 60)
        self.log = logging.getLogger('IsoParent')
        if not self.log.handlers:
            logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(name)s] %(message)s', datefmt='%H:%M:%S')

    @service_endpoint(inputs={'payload': 'Any', 'config': 'Dict'}, outputs={'result': 'Any'}, description='Executes a payload in an isolated child process.', tags=['process', 'execution'], side_effects=['process:spawn'])
    def execute(self, payload: Any, config: Optional[Dict[str, Any]]=None) -> Any:
        config = config or {}
        ctx = mp.get_context('spawn')
        result_queue = ctx.Queue()
        log_queue = ctx.Queue()
        listener = logging.handlers.QueueListener(log_queue, *logging.getLogger().handlers)
        listener.start()
        process = ctx.Process(target=_isolated_worker, args=(result_queue, log_queue, payload, config))
        self.log.info('🚀 Spawning isolated process...')
        process.start()
        try:
            result_packet = result_queue.get(timeout=self.timeout)
            process.join()
            if result_packet['success']:
                return result_packet['data']
            else:
                raise RuntimeError(f"Worker Error: {result_packet['error']}")
        except queue.Empty:
            self.log.error('⏳ Worker timed out! Terminating...')
            process.terminate()
            process.join()
            raise TimeoutError(f'Task exceeded {self.timeout}s limit.')
        finally:
            listener.stop()
if __name__ == '__main__':
    print('--- Testing IsoProcessMS with Live Logging ---')
    iso = IsoProcessMS({'timeout_seconds': 5})
    print('Service ready:', iso)
    try:
        result = iso.execute('Sensitive Data', {'model_name': 'DeepSeek-V3'})
        print(f'\n[Parent] Final Result: {result}')
    except Exception as e:
        print(f'\n[Parent] Failed: {e}')
