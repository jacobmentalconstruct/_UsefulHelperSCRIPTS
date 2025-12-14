import tkinter as tk

def on_exit():
    root.destroy()

# Create the main window
root = tk.Tk()
root.title("Popup Window")
root.geometry("200x150")  # Set the size of the window

# Create a label with the text "Hello World"
label = tk.Label(root, text="Hello World", font=("Helvetica", 16))
label.pack(pady=20)  # Add some padding around the label

# Create an Exit & Close button
exit_button = tk.Button(root, text="Exit & Close", command=on_exit)
exit_button.pack(pady=10)  # Add some padding around the button

# Run the application
root.mainloop()
