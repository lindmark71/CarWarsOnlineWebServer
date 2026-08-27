from car import Car

# Provide the relative target path to your design file
sample_car = Car("./uploads/designs/20K_2VMG_Mid.txt")

# You can immediately access any variable directly with clean dot notation!
print(f"Loaded Body Type: {sample_car.selected_body}")
print(f"Top Speed (Float verification): {sample_car.top_speed} MPH")
print(f"Front Armor Value (Integer verification): {sample_car.var_outer_armor_qty}")
print(f"Weapon 1 Array: {sample_car.selected_sub_weapon_1_canvas} (Facing: {sample_car.weapon_armor_facing_1})")
