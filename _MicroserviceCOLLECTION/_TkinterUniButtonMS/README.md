TO USE:
# In your main app file
from components import UnifiedButtonGroup # assuming you saved the class there

def my_validation_logic():
    # do pandas stuff, etc
    pass

def my_apply_logic():
    # do database stuff
    pass

# Drop the button group into your GUI
my_buttons = UnifiedButtonGroup(
    parent=my_frame, 
    on_validate=my_validation_logic, 
    on_apply=my_apply_logic
)
my_buttons.pack()