import tkinter as tk
from tkinter import messagebox, StringVar

class TaskListGenerator:
    def __init__(self, root):
        self.root = root
        self.root.title("Task List Generator")
        
        # Initialize StringVars for storing user input
        self.task_var = StringVar()
        self.description_var = StringVar()
        
        # Create a frame to hold the widgets
        self.frame = tk.Frame(root)
        self.frame.pack(padx=20, pady=20)
        
        # Create labels and entry widgets
        tk.Label(self.frame, text="Task Name:").grid(row=0, column=0, sticky=tk.W)
        self.task_entry = tk.Entry(self.frame, textvariable=self.task_var)
        self.task_entry.grid(row=0, column=1)
        
        tk.Label(self.frame, text="Description:").grid(row=1, column=0, sticky=tk.W)
        self.description_entry = tk.Entry(self.frame, textvariable=self.description_var)
        self.description_entry.grid(row=1, column=1)
            
        # Create a submit button
        self.submit_button = tk.Button(self.frame, text="Submit", command=self.show_results)
        self.submit_button.grid(row=2, column=0, columnspan=2)
        
    def show_results(self):
        task = self.task_var.get()
        description = self.description_var.get()
        
        # Create a formatted string to display the user's input
        result_text = f"Task Name: {task}\nDescription: {description}"
        
        # Display the results in a message box
        messagebox.showinfo("Task List", result_text)

if __name__ == "__main__":
    root = tk.Tk()
    app = TaskListGenerator(root)
    root.mainloop()