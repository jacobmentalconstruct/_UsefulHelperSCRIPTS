import tkinter as tk
from tkinter import scrolledtext, filedialog
import queue
import logging
import datetime
from typing import Any, Dict, Optional
from microservice_std_lib import service_metadata, service_endpoint

class QueueHandler(logging.Handler):
    """
    Sends log records to a thread-safe queue.
    Used to bridge the gap between Python's logging system and the Tkinter UI.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.log_queue.put(record)

@service_metadata(name='LogView', version='1.0.0', description='A thread-safe log viewer widget for Tkinter.', tags=['ui', 'logs', 'widget'], capabilities=['ui:gui', 'filesystem:write'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class LogViewMS(tk.Frame):
    """
    The Console: A professional log viewer widget.
    Features:
    - Thread-safe (consumes from a Queue).
    - Message Consolidation ("Error occurred (x5)").
    - Level Filtering (Toggle INFO/DEBUG/ERROR).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        parent = self.config.get('parent')
        super().__init__(parent)
        self.log_queue: queue.Queue = self.config.get('log_queue')
        if self.log_queue is None:
            self.log_queue = queue.Queue()
        self.last_msg = None
        self.last_count = 0
        self.last_line_index = None
        self._build_ui()
        self._poll_queue()

    def _build_ui(self):
        toolbar = tk.Frame(self, bg='#2d2d2d', height=30)
        toolbar.pack(fill='x', side='top')
        self.filters = {'INFO': tk.BooleanVar(value=True), 'DEBUG': tk.BooleanVar(value=True), 'WARNING': tk.BooleanVar(value=True), 'ERROR': tk.BooleanVar(value=True)}
        for level, var in self.filters.items():
            cb = tk.Checkbutton(toolbar, text=level, variable=var, bg='#2d2d2d', fg='white', selectcolor='#444', activebackground='#2d2d2d', activeforeground='white')
            cb.pack(side='left', padx=5)
        tk.Button(toolbar, text='Clear', command=self.clear, bg='#444', fg='white', relief='flat').pack(side='right', padx=5)
        tk.Button(toolbar, text='Save', command=self.save, bg='#444', fg='white', relief='flat').pack(side='right')
        self.text = scrolledtext.ScrolledText(self, state='disabled', bg='#1e1e1e', fg='#d4d4d4', font=('Consolas', 10), insertbackground='white')
        self.text.pack(fill='both', expand=True)
        self.text.tag_config('INFO', foreground='#d4d4d4')
        self.text.tag_config('DEBUG', foreground='#569cd6')
        self.text.tag_config('WARNING', foreground='#ce9178')
        self.text.tag_config('ERROR', foreground='#f44747')
        self.text.tag_config('timestamp', foreground='#608b4e')

    def _poll_queue(self):
        """Pulls logs from the queue and updates UI."""
        try:
            while True:
                record = self.log_queue.get_nowait()
                self._display(record)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_queue)

    def _display(self, record):
        level = record.levelname
        if not self.filters.get(level, tk.BooleanVar(value=True)).get():
            return
        msg = record.getMessage()
        ts = datetime.datetime.fromtimestamp(record.created).strftime('%H:%M:%S')
        self.text.config(state='normal')
        if msg == self.last_msg:
            self.last_count += 1
        else:
            self.last_msg = msg
            self.last_count = 1
        self.text.insert('end', f'[{ts}] ', 'timestamp')
        self.text.insert('end', f'{msg}\n', level)
        self.text.see('end')
        self.text.config(state='disabled')

    @service_endpoint(inputs={}, outputs={}, description='Clears the log console.', tags=['ui', 'logs'], side_effects=['ui:update'])
    def clear(self):
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.config(state='disabled')

    @service_endpoint(inputs={}, outputs={}, description='Opens a dialog to save logs to a file.', tags=['ui', 'filesystem'], side_effects=['filesystem:write', 'ui:dialog'])
    def save(self):
        path = filedialog.asksaveasfilename(defaultextension='.log', filetypes=[('Log Files', '*.log')])
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(self.text.get('1.0', 'end'))
            except Exception as e:
                print(f'Save failed: {e}')
if __name__ == '__main__':
    root = tk.Tk()
    root.title('Log View Test')
    root.geometry('600x400')
    q = queue.Queue()
    logger = logging.getLogger('TestApp')
    logger.setLevel(logging.DEBUG)
    logger.addHandler(QueueHandler(q))
    log_view = LogViewMS({'parent': root, 'log_queue': q})
    print('Service ready:', log_view)
    log_view.pack(fill='both', expand=True)

    def generate_noise():
        logger.info('System initializing...')
        logger.debug('Checking sensors...')
        logger.warning('Sensor 4 response slow.')
        logger.error('Connection failed!')
        root.after(2000, generate_noise)
    generate_noise()
    root.mainloop()
