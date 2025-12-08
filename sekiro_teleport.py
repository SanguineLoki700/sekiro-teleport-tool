import customtkinter as ctk
import pymem
import pymem.process
import keyboard
import threading
import json
import os
import sys
import time

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("dark-blue")

class SekiroTrainerV2:
    def __init__(self):
        self.pm = None
        self.game_module = None
        self.final_addr = None
        self.quick_saved_pos = None
        self.saved_locations = {}
        self.json_file = "locations.json"

        self.root = ctk.CTk()
        self.root.title("Sekiro Teleport Manager")
        self.root.geometry("550x600") 
        self.root.resizable(False, False)

        self.load_locations_from_file()
        self.setup_gui()

        self.connect_thread = threading.Thread(target=self.initial_setup)
        self.connect_thread.daemon = True
        self.connect_thread.start()

        self.root.mainloop()

    def initial_setup(self):
        time.sleep(0.5)
        if self.connect():
            self.find_address_from_scan()
            self.setup_hotkeys()
        else:
            self.update_status("Sekiro not found! Please open the game.", "#FF5555")

    def connect(self):
        try:
            self.pm = pymem.Pymem("sekiro.exe")
            self.game_module = pymem.process.module_from_name(self.pm.process_handle, "sekiro.exe").lpBaseOfDll
            return True
        except:
            return False

    def update_status(self, text, color):
        try:
            self.lbl_status.configure(text=text, text_color=color)
        except:
            pass

    def find_address_from_scan(self):
        candidates = [
            (0x03AFB218, [0x28, 0x80]), 
            (0x03D7A1E0, [0x48, 0x28, 0x80])
        ]
        found = False
        for base_offset, offsets in candidates:
            try:
                addr = self.pm.read_longlong(self.game_module + base_offset)
                valid = True
                for off in offsets[:-1]:
                    if addr == 0:
                        valid = False
                        break
                    addr = self.pm.read_longlong(addr + off)
                
                if valid and addr != 0:
                    final_x = addr + offsets[-1]
                    if self.pm.read_float(final_x) != 0.0:
                        self.final_addr = final_x
                        self.update_status("Connected & Ready!", "#55FF55")
                        found = True
                        return
            except:
                continue
        
        if not found:
            self.update_status("Error: Player address not found. Move character.", "#FF5555")

    def get_player_pos(self):
        if not self.final_addr: return None
        try:
            x = self.pm.read_float(self.final_addr)
            z = self.pm.read_float(self.final_addr + 4)
            y = self.pm.read_float(self.final_addr + 8)
            return [x, y, z]
        except:
            return None

    def teleport_to(self, pos):
        if not self.final_addr or not pos: return
        try:
            self.pm.write_float(self.final_addr, float(pos[0]))
            self.pm.write_float(self.final_addr + 4, float(pos[2]))
            self.pm.write_float(self.final_addr + 8, float(pos[1]))
            print(f"Teleported to {pos}")
        except:
            self.update_status("Error writing memory", "#FF5555")

    def quick_save(self):
        pos = self.get_player_pos()
        if pos:
            self.quick_saved_pos = pos
            self.lbl_info.configure(text=f"QUICK SAVE (F5)\nX: {pos[0]:.1f} | Y: {pos[1]:.1f}", text_color="#F1C40F")

    def quick_load(self):
        if self.quick_saved_pos:
            self.teleport_to(self.quick_saved_pos)
            self.lbl_info.configure(text="QUICK LOAD (F9)", text_color="#3498db")

    def setup_hotkeys(self):
        keyboard.add_hotkey('f5', self.quick_save)
        keyboard.add_hotkey('f9', self.quick_load)

    def load_locations_from_file(self):
        if os.path.exists(self.json_file):
            try:
                with open(self.json_file, 'r') as f:
                    self.saved_locations = json.load(f)
            except:
                self.saved_locations = {}

    def save_locations_to_file(self):
        try:
            with open(self.json_file, 'w') as f:
                json.dump(self.saved_locations, f, indent=4)
        except:
            pass

    def add_custom_location(self):
        name = self.entry_name.get()
        
        if not name:
            count = len(self.saved_locations) + 1
            name = f"Location {count}"
        
        original_name = name
        i = 1
        while name in self.saved_locations:
            name = f"{original_name} ({i})"
            i += 1
        
        pos = self.get_player_pos()
        if pos:
            self.saved_locations[name] = pos
            self.save_locations_to_file()
            self.refresh_scroll_list()
            self.entry_name.delete(0, "end")
            self.update_status(f"Saved: {name}", "#55FF55")
        else:
            self.update_status("Connect to game first!", "#FF5555")

    def delete_location(self, name):
        if name in self.saved_locations:
            del self.saved_locations[name]
            self.save_locations_to_file()
            self.refresh_scroll_list()

    def rename_location(self, old_name):
        dialog = ctk.CTkInputDialog(text="Enter new name:", title="Rename Location")
        new_name = dialog.get_input()
        
        if new_name and new_name != old_name:
            
            pos = self.saved_locations[old_name]
            
            del self.saved_locations[old_name]
            
            self.saved_locations[new_name] = pos
            self.save_locations_to_file()
            self.refresh_scroll_list()

    def refresh_scroll_list(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        for name, pos in self.saved_locations.items():
            item_frame = ctk.CTkFrame(self.scroll_frame)
            item_frame.pack(fill="x", pady=2, padx=5)

            btn_tp = ctk.CTkButton(item_frame, text="GO", width=40, fg_color="#3498db", hover_color="#2980b9",
                                   command=lambda p=pos: self.teleport_to(p))
            btn_tp.pack(side="left", padx=5)

            lbl = ctk.CTkLabel(item_frame, text=name, anchor="w", font=("Arial", 12, "bold"))
            lbl.pack(side="left", padx=5, fill="x", expand=True)

            btn_edit = ctk.CTkButton(item_frame, text="Edit", width=40, fg_color="#f39c12", hover_color="#d35400",
                                    command=lambda n=name: self.rename_location(n))
            btn_edit.pack(side="right", padx=2)

            btn_del = ctk.CTkButton(item_frame, text="X", width=30, fg_color="#c0392b", hover_color="#e74c3c",
                                    command=lambda n=name: self.delete_location(n))
            btn_del.pack(side="right", padx=2)

    def setup_gui(self):
        title = ctk.CTkLabel(self.root, text="SEKIRO TELEPORT MANAGER", font=("Impact", 24))
        title.pack(pady=10)

        self.lbl_status = ctk.CTkLabel(self.root, text="Scanning...", font=("Arial", 12))
        self.lbl_status.pack()

        quick_frame = ctk.CTkFrame(self.root)
        quick_frame.pack(fill="x", padx=20, pady=10)
        
        ctk.CTkLabel(quick_frame, text="Quick Actions (Hotkeys)", font=("Arial", 12, "bold")).pack(pady=5)
        self.lbl_info = ctk.CTkLabel(quick_frame, text="F5: Quick Save | F9: Quick Load", text_color="gray")
        self.lbl_info.pack(pady=5)

        custom_frame = ctk.CTkFrame(self.root)
        custom_frame.pack(fill="both", expand=True, padx=20, pady=10)

        input_frame = ctk.CTkFrame(custom_frame, fg_color="transparent")
        input_frame.pack(fill="x", pady=10, padx=10)

        self.entry_name = ctk.CTkEntry(input_frame, placeholder_text="Location Name (Optional)")
        self.entry_name.pack(side="left", fill="x", expand=True, padx=(0, 10))

        btn_add = ctk.CTkButton(input_frame, text="Save Pos", command=self.add_custom_location, fg_color="#27ae60", hover_color="#2ecc71")
        btn_add.pack(side="right")

        ctk.CTkLabel(custom_frame, text="Saved Locations:", anchor="w").pack(fill="x", padx=15)
        
        self.scroll_frame = ctk.CTkScrollableFrame(custom_frame, height=200)
        self.scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        self.refresh_scroll_list()

        footer = ctk.CTkLabel(self.root, text="Mod by SanguineLoki700", font=("Arial", 10), text_color="gray")
        footer.pack(side="bottom", pady=5)

if __name__ == "__main__":

    SekiroTrainerV2()
