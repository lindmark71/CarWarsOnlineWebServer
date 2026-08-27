import ast
import os

class Car:
    def __init__(self, design_file_path):
        """
        Initializes a Car object by parsing a design file path.
        Automatically converts every key in the file into a class member variable.
        """
        self.design_file_path = design_file_path
        
        # ── Baseline Positional States (Independent of Design Files) ──────────
        self.current_speed = 0.0
        self.current_x = 0.0
        self.current_y = 0.0
        self.orientation = 0  # Clockwise degrees (0, 90, 180, 270)
        
        # Trigger the automatic file ingestion sequence
        self._absorb_design_file()

    def _absorb_design_file(self):
        """Reads the text file and injects all dictionary values as class attributes."""
        if not os.path.exists(self.design_file_path):
            raise FileNotFoundError(f"Design file not found at: {self.design_file_path}")

        try:
            with open(self.design_file_path, 'r', encoding='utf-8') as file:
                raw_content = file.read().strip()

            # Safely evaluate the string format into a Python object
            parsed_data = ast.literal_eval(raw_content)

            # If wrapped in a list context (e.g., [{...}]), extract the inner dictionary
            if isinstance(parsed_data, list) and len(parsed_data) > 0:
                design_dict = parsed_data[0]
            elif isinstance(parsed_data, dict):
                design_dict = parsed_data
            else:
                raise ValueError("Data format must resolve to a dictionary or a list containing a dictionary.")

            # ── Dynamic Attribute Injection Loop ──────────────────────────────
            for key, value in design_dict.items():
                # Clean up the key: remove 'self.' prefix if it exists
                clean_key = key.replace('self.', '') if key.startswith('self.') else key
                
                # Clean up values: convert numbers hidden inside strings into real numeric types
                processed_value = self._sanitize_value(value)
                
                # Programmatically attach the variable directly to this class instance
                setattr(self, clean_key, processed_value)

        except Exception as e:
            print(f"Error parsing car configuration file: {e}")
            raise

    def _sanitize_value(self, val):
        """Converts numerical strings into clean Python ints or floats where applicable."""
        if not isinstance(val, str):
            return val
            
        # Try converting integer strings (e.g., '12' -> 12)
        if val.isdigit() or (val.startswith('-') and val[1:].isdigit()):
            return int(val)
            
        # Try converting decimal strings (e.g., '92.50' -> 92.5)
        try:
            if '.' in val:
                return float(val)
        except ValueError:
            pass
            
        return val # Fall back to returning raw string if no conversion works

    def display_profile_summary(self):
        """Debug helper that prints out all attributes currently attached to the car."""
        print(f"\n===== CAR PROFILE: {os.path.basename(self.design_file_path)} =====")
        for key, value in sorted(self.__dict__.items()):
            # Skip printing the master path layout tracker string
            if key == "design_file_path":
                continue
            print(f"  self.{key:<35} = {repr(value)}")
