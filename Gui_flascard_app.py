# flashcards_gui.py
# Simple flashcards app with a basic spaced-repetition scheduler and a Tkinter UI.
# Save in your repo and run: python3 flashcards_gui.py

import json
import os
import uuid
import csv
from datetime import date, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

db_file = "flashcards.json"


# ---------- Helpers for date and storage ----------
def today():
    """Return today's date (date object)."""
    return date.today()


def load_db():
    """Load JSON store, return a dict with 'decks' key."""
    if not os.path.exists(db_file):
        return {"decks": {}}
    try:
        with open(db_file, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        # If file gets corrupted, warn and start fresh
        messagebox.showwarning("Data warning", f"{db_file} seems damaged — starting fresh.")
        return {"decks": {}}


def save_db(data):
    """Write data back to disk (pretty JSON)."""
    with open(db_file, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


# ---------- Model / scheduling ----------
def make_card(front, back):
    """Create a new card dict with default scheduling fields."""
    return {
        "id": str(uuid.uuid4()),
        "front": front,
        "back": back,
        "repetitions": 0,
        "interval": 0,
        "ef": 2.5,               # ease factor (SM-2 style starting value)
        "due": today().isoformat()
    }


def cards_due(deck):
    """Return list of cards that are due today or earlier."""
    out = []
    d_today = today()
    for c in deck.get("cards", []):
        try:
            due_date = date.fromisoformat(c.get("due", d_today.isoformat()))
        except Exception:
            due_date = d_today
        if due_date <= d_today:
            out.append(c)
    return out


def schedule_card(card, quality):
    """
    Update card in-place using a small SM-2-inspired algorithm.
    quality should be int 0..5 (5 = perfect).
    """
    q = max(0, min(5, int(quality)))
    ef = float(card.get("ef", 2.5))
    reps = int(card.get("repetitions", 0))
    interval = int(card.get("interval", 0))

    if q < 3:
        # failed recall -> reset repetitions but keep a short interval
        reps = 0
        interval = 1
    else:
        # successful recall -> set interval according to reps
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = max(1, round(interval * ef))
        reps += 1

    # adjust ease factor (small step; keep it above 1.3)
    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if ef < 1.3:
        ef = 1.3

    card["repetitions"] = reps
    card["interval"] = interval
    card["ef"] = round(ef, 2)
    card["due"] = (today() + timedelta(days=interval)).isoformat()


# ---------- Deck operations ----------
def create_deck(data, name):
    if not name or name.strip() == "":
        return False
    name = name.strip()
    if name in data["decks"]:
        return False
    data["decks"][name] = {"cards": []}
    save_db(data)
    return True


def delete_deck(data, name):
    if name in data["decks"]:
        del data["decks"][name]
        save_db(data)
        return True
    return False


def add_card(data, deck_name, front, back):
    if deck_name not in data["decks"]:
        return False
    data["decks"][deck_name]["cards"].append(make_card(front, back))
    save_db(data)
    return True


def export_deck_to_csv(data, deck_name):
    """Write a CSV file with deck contents; return file name or None."""
    deck = data["decks"].get(deck_name)
    if not deck:
        return None
    fname = f"{deck_name.replace(' ', '_')}.csv"
    with open(fname, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["id", "front", "back", "repetitions", "interval", "ef", "due"])
        for c in deck["cards"]:
            writer.writerow([c.get("id"), c.get("front"), c.get("back"),
                             c.get("repetitions"), c.get("interval"), c.get("ef"), c.get("due")])
    return fname


# ---------- UI: Study window ----------
class StudyWindow(tk.Toplevel):
    def __init__(self, master, data, deck_name):
        super().__init__(master)
        self.title(f"Study — {deck_name}")
        self.resizable(False, False)
        self.data = data
        self.deck_name = deck_name
        self.deck = data["decks"].get(deck_name, {"cards": []})
        self.cards = cards_due(self.deck)
        self.i = 0

        # UI pieces
        self.front_label = tk.Label(self, text="", font=("Arial", 16), wraplength=420, justify="center")
        self.front_label.grid(row=0, column=0, columnspan=6, padx=12, pady=(12, 6))

        self.show_btn = ttk.Button(self, text="Show answer", command=self.show_answer)
        self.show_btn.grid(row=1, column=0, columnspan=6, pady=(0, 8))

        self.back_label = tk.Label(self, text="", font=("Arial", 13), wraplength=420, justify="center", fg="#333333")
        self.back_label.grid(row=2, column=0, columnspan=6, padx=12, pady=(0, 8))

        tk.Label(self, text="Rate (0–5):").grid(row=3, column=0, columnspan=6)
        self.rate_buttons = []
        for n in range(6):
            b = ttk.Button(self, text=str(n), command=lambda q=n: self.rate(q))
            b.grid(row=4, column=n, padx=4, pady=8, sticky="we")
            b.config(state="disabled")
            self.rate_buttons.append(b)

        self.status = tk.Label(self, text="", anchor="w")
        self.status.grid(row=5, column=0, columnspan=6, sticky="we", padx=8, pady=(0,8))

        ttk.Button(self, text="End session", command=self.on_close).grid(row=6, column=0, columnspan=6, pady=(0,12))

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.update_ui()

    def update_ui(self):
        if not self.cards:
            self.front_label.config(text="No cards due. You're ahead!")
            self.back_label.config(text="")
            self.show_btn.config(state="disabled")
            for b in self.rate_buttons:
                b.config(state="disabled")
            self.status.config(text="Nothing to review today.")
            return

        if self.i >= len(self.cards):
            self.front_label.config(text="Session complete — good work.")
            self.back_label.config(text="")
            self.show_btn.config(state="disabled")
            for b in self.rate_buttons:
                b.config(state="disabled")
            self.status.config(text=f"Reviewed {len(self.cards)} card(s).")
            return

        c = self.cards[self.i]
        self.front_label.config(text=c["front"])
        self.back_label.config(text="")
        self.show_btn.config(state="normal")
        for b in self.rate_buttons:
            b.config(state="disabled")
        self.status.config(text=f"Card {self.i + 1} of {len(self.cards)}")

    def show_answer(self):
        c = self.cards[self.i]
        self.back_label.config(text=c["back"])
        for b in self.rate_buttons:
            b.config(state="normal")
        self.show_btn.config(state="disabled")

    def rate(self, q):
        c = self.cards[self.i]
        schedule_card(c, q)
        save_db(self.data)
        self.i += 1
        # re-enable UI for next card
        self.show_btn.config(state="normal")
        self.update_ui()

    def on_close(self):
        self.destroy()


# ---------- Main application ----------
class FlashcardApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Flashcards")
        self.geometry("720x420")
        self.minsize(640, 360)

        self.data = load_db()
        self.build_ui()
        self.refresh_decks()

    def build_ui(self):
        left = ttk.Frame(self)
        left.pack(side="left", fill="y", padx=8, pady=8)

        ttk.Label(left, text="Decks").pack(anchor="w")
        self.deck_list = tk.Listbox(left, height=20, width=28)
        self.deck_list.pack(pady=(6,8))
        self.deck_list.bind("<<ListboxSelect>>", lambda e: self.on_select())

        bframe = ttk.Frame(left)
        bframe.pack(fill="x")
        ttk.Button(bframe, text="New deck", command=self.new_deck).pack(fill="x", pady=2)
        ttk.Button(bframe, text="Delete deck", command=self.delete_deck).pack(fill="x", pady=2)
        ttk.Button(bframe, text="Export CSV", command=self.export_deck).pack(fill="x", pady=2)
        ttk.Button(bframe, text="Study", command=self.open_study).pack(fill="x", pady=2)

        right = ttk.Frame(self)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)

        self.deck_title = ttk.Label(right, text="Select a deck", font=("Arial", 14))
        self.deck_title.pack(anchor="w")

        self.deck_info = ttk.Label(right, text="No deck selected.", justify="left")
        self.deck_info.pack(anchor="w", pady=(4,12))

        card_frame = ttk.LabelFrame(right, text="Add card")
        card_frame.pack(fill="x", padx=4, pady=4)

        ttk.Label(card_frame, text="Front:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        self.front_entry = ttk.Entry(card_frame)
        self.front_entry.grid(row=0, column=1, sticky="ew", padx=6, pady=4)

        ttk.Label(card_frame, text="Back:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        self.back_entry = ttk.Entry(card_frame)
        self.back_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=4)

        card_frame.columnconfigure(1, weight=1)
        ttk.Button(card_frame, text="Add card", command=self.add_card).grid(row=2, column=0, columnspan=2, pady=8)

        bottom = ttk.Frame(right)
        bottom.pack(fill="both", expand=True, pady=(8,0))
        ttk.Label(bottom, text="Quick tips:", font=("Arial", 10, "bold")).pack(anchor="w")
        ttk.Label(bottom, text="• Create a deck, add some cards, then click Study.\n"
                               "• Rate yourself honestly: it affects how fast cards come back.",
                  justify="left").pack(anchor="w", pady=(2,6))

    def refresh_decks(self):
        self.data = load_db()
        self.deck_list.delete(0, tk.END)
        for name in sorted(self.data["decks"].keys()):
            self.deck_list.insert(tk.END, name)
        self.update_deck_info(None)

    def on_select(self):
        sel = self.deck_list.curselection()
        if not sel:
            self.update_deck_info(None)
            return
        name = self.deck_list.get(sel[0])
        self.update_deck_info(name)

    def update_deck_info(self, name):
        if not name or name not in self.data["decks"]:
            self.deck_title.config(text="Select a deck")
            self.deck_info.config(text="No deck selected.")
            return
        deck = self.data["decks"][name]
        total = len(deck.get("cards", []))
        due = len(cards_due(deck))
        self.deck_title.config(text=name)
        self.deck_info.config(text=f"Total cards: {total}\nDue today: {due}")

    def new_deck(self):
        name = simpledialog.askstring("New deck", "Deck name:")
        if not name:
            return
        if create_deck(self.data, name):
            self.refresh_decks()
        else:
            messagebox.showinfo("Info", "Deck exists or invalid name.")

    def delete_deck(self):
        sel = self.deck_list.curselection()
        if not sel:
            messagebox.showinfo("Info", "Pick a deck first.")
            return
        name = self.deck_list.get(sel[0])
        if messagebox.askyesno("Confirm", f"Delete deck '{name}'? This is permanent."):
            delete_deck(self.data, name)
            self.refresh_decks()

    def add_card(self):
        sel = self.deck_list.curselection()
        if not sel:
            messagebox.showinfo("Info", "Select a deck first.")
            return
        name = self.deck_list.get(sel[0])
        front = self.front_entry.get().strip()
        back = self.back_entry.get().strip()
        if not front or not back:
            messagebox.showinfo("Info", "Both front and back are required.")
            return
        add_card(self.data, name, front, back)
        self.front_entry.delete(0, tk.END)
        self.back_entry.delete(0, tk.END)
        self.refresh_decks()

    def export_deck(self):
        sel = self.deck_list.curselection()
        if not sel:
            messagebox.showinfo("Info", "Select a deck to export.")
            return
        name = self.deck_list.get(sel[0])
        fname = export_deck_to_csv(self.data, name)
        if fname:
            messagebox.showinfo("Exported", f"Deck saved as {fname}")
        else:
            messagebox.showerror("Error", "Export failed.")

    def open_study(self):
        sel = self.deck_list.curselection()
        if not sel:
            messagebox.showinfo("Info", "Pick a deck first.")
            return
        name = self.deck_list.get(sel[0])
        StudyWindow(self, self.data, name)

    def run(self):
        self.mainloop()


if __name__ == "__main__":
    app = FlashcardApp()
    app.run()