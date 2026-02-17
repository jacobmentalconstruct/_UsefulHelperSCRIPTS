import tkinter as tk
import time as time
from time import strftime


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Clock & Stopwatch")
        self.geometry("300x200")

        # Create a frame for the clock display
        self.clock_frame = tk.Frame(self)
        self.clock_frame.pack(pady=10)

        # Create labels for displaying time and date
        self.time_label = tk.Label(self.clock_frame, font=('Arial', 40), bg='black', fg='white')
        self.date_label = tk.Label(self.clock_frame, font=('Arial', 20), bg='black', fg='white')

        self.time_label.pack(side=tk.LEFT)
        self.date_label.pack(side=tk.LEFT)

        # Create a frame for the stopwatch display
        self.stopwatch_frame = tk.Frame(self)
        self.stopwatch_frame.pack(pady=10)

        # Create labels for displaying elapsed time and stopwatch controls
        self.elapsed_label = tk.Label(self.stopwatch_frame, font=('Arial', 40), bg='black', fg='white')
        self.start_button = tk.Button(self.stopwatch_frame, text="Start", command=self.start_stopwatch)
        self.stop_button = tk.Button(self.stopwatch_frame, text="Stop", command=self.stop_stopwatch)
        self.reset_button = tk.Button(self.stopwatch_frame, text="Reset", command=self.reset_stopwatch)

        self.elapsed_label.pack(side=tk.LEFT)
        self.start_button.pack(side=tk.LEFT)
        self.stop_button.pack(side=tk.LEFT)
        self.reset_button.pack(side=tk.LEFT)

        # Initialize variables
        self.running = False
        self.start_time = 0
        self.total_seconds = 0

        # Update time and date labels every second
        self.update_clock()

    def update_clock(self):
        current_time = strftime('%H:%M:%S %p')
        current_date = strftime('%A, %B %d, %Y')
        self.time_label.config(text=current_time)
        self.date_label.config(text=current_date)
        self.after(1000, self.update_clock)

    def update_stopwatch(self):
        if self.running:
            elapsed_seconds = int((time.time() - self.start_time) + self.total_seconds)
            hours = elapsed_seconds // 3600
            minutes = (elapsed_seconds % 3600) // 60
            seconds = elapsed_seconds % 60
            time_format = f"{hours:02}:{minutes:02}:{seconds:02}"
            self.elapsed_label.config(text=time_format)
            self.after(1000, self.update_stopwatch)

    def start_stopwatch(self):
        if not self.running:
            self.start_time = time.time() - self.total_seconds
            self.running = True

    def stop_stopwatch(self):
        if self.running:
            elapsed_seconds = int((time.time() - self.start_time) + self.total_seconds)
            hours = elapsed_seconds // 3600
            minutes = (elapsed_seconds % 3600) // 60
            seconds = elapsed_seconds % 60
            time_format = f"{hours:02}:{minutes:02}:{seconds:02}"
            self.elapsed_label.config(text=time_format)
            self.running = False

    def reset_stopwatch(self):
        self.elapsed_label.config(text="00:00:00")
        self.total_seconds = 0

if __name__ == "__main__":
    app = App()
    app.mainloop()