# timesheet_app.py
import os
import sqlite3
import calendar
import traceback
from datetime import datetime, timedelta, date

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.togglebutton import ToggleButton

from fpdf import FPDF

# ---------- THEME ----------
Window.clearcolor = (1, 1, 1, 1)  # white background
COLOR_BLUE = (0, 0.5, 1, 1)   # Clock In
COLOR_RED = (1, 0, 0, 1)      # Clock Out
COLOR_GREEN = (0, 0.7, 0.2, 1) # Export
COLOR_TEXT = (0, 0, 0, 1)

POP_DAY_BG = (0.98, 0.98, 0.98, 1)
POP_EMPTY_BG = (0.94, 0.94, 0.94, 1)
POP_WEEK_HI = (0.84, 0.91, 1, 1)
POP_DAY_SEL = (0.54, 0.76, 1, 1)
POP_HEADER_BG = (0.95, 0.97, 1, 1)

# Colors for PDF rows (0-255)
PDF_ROW_RGB = {
    'O': (185, 215, 255),  # light blue
    'M': (195, 245, 195),  # light green
    'N': (255, 255, 190),  # light yellow
}

# ---------- DATABASE ----------
DB_FILE = "timesheet.db"
# allow SQLite usage across callbacks
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
c = conn.cursor()

# Ensure base table exists (older DBs might not have 'shift')
c.execute('''CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY,
    clock_in TEXT,
    clock_out TEXT,
    duration REAL
)''')
conn.commit()

def determine_shift(start_time: datetime, end_time: datetime) -> str:
    """Decide shift (O/M/N) by where majority of minutes fall."""
    counts = {'O': 0, 'M': 0, 'N': 0}
    cur = start_time
    while cur < end_time:
        h = cur.hour
        if 6 <= h < 14:
            counts['O'] += 1
        elif 14 <= h < 22:
            counts['M'] += 1
        else:
            counts['N'] += 1
        cur += timedelta(minutes=1)
    return max(counts, key=counts.get)

def ensure_shift_column_and_backfill():
    """If 'shift' isn't present in DB, add it and backfill rows that have clock_out."""
    try:
        c.execute("PRAGMA table_info(shifts)")
        cols = [r[1] for r in c.fetchall()]
        if 'shift' not in cols:
            try:
                c.execute("ALTER TABLE shifts ADD COLUMN shift TEXT")
                conn.commit()
            except Exception:
                # If ALTER fails, ignore (rare)
                pass

        # Backfill shift where possible
        c.execute("SELECT id, clock_in, clock_out FROM shifts WHERE (shift IS NULL OR shift='') AND clock_in IS NOT NULL AND clock_out IS NOT NULL")
        rows = c.fetchall()
        for rid, cin, cout in rows:
            try:
                start = datetime.strptime(cin, "%Y-%m-%d %H:%M:%S")
                end = datetime.strptime(cout, "%Y-%m-%d %H:%M:%S")
                sh = determine_shift(start, end)
                c.execute("UPDATE shifts SET shift = ? WHERE id = ?", (sh, rid))
            except Exception:
                continue
        conn.commit()
    except Exception:
        pass

ensure_shift_column_and_backfill()

def safe_pdf_filename(week_num: int, iso_year: int, to_folder: str) -> str:
    base = f"Timesheet_Week{week_num:02d}_{iso_year}.pdf"
    full = os.path.join(to_folder, base)
    if not os.path.exists(full):
        return full
    i = 1
    while True:
        candidate = os.path.join(to_folder, f"Timesheet_Week{week_num:02d}_{iso_year}-{i}.pdf")
        if not os.path.exists(candidate):
            return candidate
        i += 1

# ---------- CALENDAR POPUP ----------
class CalendarPopup(Popup):
    def __init__(self, app_ref, **kwargs):
        self.app_ref = app_ref
        self.year = datetime.now().year
        self.month = datetime.now().month
        self.selected_day_dt = None
        self._day_buttons = []
        self._week_rows = []

        root = BoxLayout(orientation='vertical', spacing=10, padding=12)

        header = BoxLayout(size_hint=(1, 0.09), spacing=8)
        self.prev_btn = Button(text="◀", background_normal="", background_color=COLOR_BLUE)
        self.month_lbl = Label(text="", color=COLOR_TEXT, font_size=20)
        self.next_btn = Button(text="▶", background_normal="", background_color=COLOR_BLUE)
        header.add_widget(self.prev_btn)
        header.add_widget(self.month_lbl)
        header.add_widget(self.next_btn)
        root.add_widget(header)

        dow = GridLayout(cols=7, size_hint=(1, 0.07))
        for name in ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]:
            lbl = Label(text=name, color=COLOR_TEXT)
            dow.add_widget(lbl)
        root.add_widget(dow)

        self.grid = GridLayout(cols=7, spacing=6, size_hint_y=None)
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll = ScrollView(size_hint=(1, 0.68))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)

        self.week_info = Label(text="", size_hint=(1, 0.05), color=COLOR_TEXT)
        root.add_widget(self.week_info)

        footer = BoxLayout(size_hint=(1, 0.09), spacing=8)
        self.cancel_btn = Button(text="Cancel", background_normal="", background_color=(0.9, 0.9, 0.9, 1))
        self.export_btn = Button(text="Export Week PDF", background_normal="", background_color=COLOR_GREEN)
        footer.add_widget(self.cancel_btn)
        footer.add_widget(self.export_btn)
        root.add_widget(footer)

        super().__init__(title="Select Week to Export", content=root, size_hint=(0.92, 0.92), auto_dismiss=True)
        self.prev_btn.bind(on_release=self.prev_month)
        self.next_btn.bind(on_release=self.next_month)
        self.cancel_btn.bind(on_release=lambda *_: self.dismiss())
        self.export_btn.bind(on_release=self._on_export)

        self._draw_calendar()

    def _draw_calendar(self):
        self.grid.clear_widgets()
        self._day_buttons.clear()
        self._week_rows.clear()
        self.selected_day_dt = None
        self.week_info.text = ""
        try:
            self.month_lbl.text = f"{calendar.month_name[self.month]} {self.year}"
            month_weeks = calendar.monthcalendar(self.year, self.month)
            rows = len(month_weeks)
            self.grid.height = rows * 52
            for w_idx, week in enumerate(month_weeks):
                row = []
                for day in week:
                    if day == 0:
                        btn = Button(text="", disabled=True, background_normal="", background_color=POP_EMPTY_BG, size_hint_y=None, height=48)
                        self.grid.add_widget(btn)
                        row.append(None)
                    else:
                        btn = ToggleButton(text=str(day), group="cal_days", background_normal="", background_color=POP_DAY_BG, color=COLOR_TEXT, size_hint_y=None, height=48)
                        btn._week_index = w_idx
                        btn._date = datetime(self.year, self.month, day)
                        btn.bind(on_release=self._on_day_pressed)
                        self.grid.add_widget(btn)
                        row.append(btn)
                        self._day_buttons.append(btn)
                self._week_rows.append(row)
        except Exception:
            Popup(title="Calendar Error", content=Label(text=traceback.format_exc()), size_hint=(0.9, 0.8)).open()

    def _on_day_pressed(self, btn):
        try:
            self.selected_day_dt = btn._date
            week_index = btn._week_index
            for b in self._day_buttons:
                b.background_color = POP_DAY_BG
            for cell in self._week_rows[week_index]:
                if isinstance(cell, ToggleButton):
                    cell.background_color = POP_WEEK_HI
            btn.background_color = POP_DAY_SEL
            self.week_info.text = f"Selected: {self.selected_day_dt.strftime('%B %d, %Y')}  ->  Week {self.selected_day_dt.isocalendar()[1]}"
        except Exception:
            Popup(title="Selection Error", content=Label(text=traceback.format_exc()), size_hint=(0.9, 0.8)).open()

    def prev_month(self, *_):
        self.month -= 1
        if self.month < 1:
            self.month = 12
            self.year -= 1
        self._draw_calendar()

    def next_month(self, *_):
        self.month += 1
        if self.month > 12:
            self.month = 1
            self.year += 1
        self._draw_calendar()

    def _on_export(self, *_):
        if not self.selected_day_dt:
            Popup(title="No selection", content=Label(text="Please select a day first."), size_hint=(0.6, 0.4)).open()
            return
        try:
            self.app_ref.export_week_by_selected_day(self.selected_day_dt)
        except Exception:
            Popup(title="Export Error", content=Label(text=traceback.format_exc()), size_hint=(0.9, 0.8)).open()
        finally:
            self.dismiss()

# ---------- MAIN UI ----------
class TimeTracker(BoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.padding = 18
        self.spacing = 18

        self.clocked_in = False
        self.clock_in_time = None

        self.clock_label = Label(text="Clock In: --:--:--", font_size=40, size_hint=(1, 0.18), color=COLOR_TEXT)
        self.add_widget(self.clock_label)

        self.timer_label = Label(text="Running Time: 00:00:00", font_size=40, size_hint=(1, 0.2), color=(0,0,0,1))
        self.add_widget(self.timer_label)
        with self.timer_label.canvas.before:
            Color(1, 1, 1, 1)
            self._timer_rect = Rectangle(pos=self.timer_label.pos, size=self.timer_label.size)
        self.timer_label.bind(pos=self._resize_timer_rect, size=self._resize_timer_rect)

        btns = BoxLayout(size_hint=(1, 0.28), spacing=14)
        self.btn_clock_in = Button(text="Clock In", font_size=30, background_normal="", background_color=COLOR_BLUE)
        self.btn_clock_out = Button(text="Clock Out", font_size=30, background_normal="", background_color=COLOR_RED)
        self.btn_export = Button(text="Select Week to Export", font_size=26, background_normal="", background_color=COLOR_GREEN)
        btns.add_widget(self.btn_clock_in)
        btns.add_widget(self.btn_clock_out)
        btns.add_widget(self.btn_export)
        self.add_widget(btns)

        self.log_grid = GridLayout(cols=1, size_hint_y=None, spacing=6)
        self.log_grid.bind(minimum_height=self.log_grid.setter('height'))
        self.scroll = ScrollView(size_hint=(1, 0.34))
        self.scroll.add_widget(self.log_grid)
        self.add_widget(self.scroll)

        self.btn_clock_in.bind(on_release=self.clock_in)
        self.btn_clock_out.bind(on_release=self.clock_out)
        self.btn_export.bind(on_release=self.open_calendar)

        Clock.schedule_interval(self._tick, 1)

    def _resize_timer_rect(self, *_):
        self._timer_rect.pos = self.timer_label.pos
        self._timer_rect.size = self.timer_label.size

    def clock_in(self, *_):
        if self.clocked_in:
            return
        self.clock_in_time = datetime.now()
        self.clocked_in = True
        self.clock_label.text = f"Clock In: {self.clock_in_time.strftime('%H:%M:%S')}"
        self._log(f"Clocked in: {self.clock_in_time.strftime('%Y-%m-%d %H:%M:%S')}")

    def clock_out(self, *_):
        if not self.clocked_in:
            return
        out = datetime.now()
        duration = (out - self.clock_in_time).total_seconds() / 3600.0
        shift_letter = determine_shift(self.clock_in_time, out)
        try:
            # ensure 'shift' column exists (migration ran at startup)
            c.execute('INSERT INTO shifts (clock_in, clock_out, duration, shift) VALUES (?, ?, ?, ?)',
                      (self.clock_in_time.strftime("%Y-%m-%d %H:%M:%S"),
                       out.strftime("%Y-%m-%d %H:%M:%S"),
                       round(duration, 2),
                       shift_letter))
            conn.commit()
        except Exception:
            Popup(title="DB Error", content=Label(text=traceback.format_exc()), size_hint=(0.9, 0.8)).open()
            return

        self._log(f"Clocked out: {out.strftime('%Y-%m-%d %H:%M:%S')}  - {duration:.2f} h  [{shift_letter}]")
        self.clocked_in = False
        self.clock_in_time = None
        self.clock_label.text = "Clock In: --:--:--"
        self.timer_label.text = "Running Time: 00:00:00"
        with self.timer_label.canvas.before:
            Color(1, 1, 1, 1)
            self._timer_rect = Rectangle(pos=self.timer_label.pos, size=self.timer_label.size)

    def _tick(self, dt):
        if not self.clocked_in:
            return
        now = datetime.now()
        elapsed = now - self.clock_in_time
        hrs, rem = divmod(int(elapsed.total_seconds()), 3600)
        mins, secs = divmod(rem, 60)
        self.timer_label.text = f"Running Time: {hrs:02d}:{mins:02d}:{secs:02d}"

        try:
            shift_letter = determine_shift(self.clock_in_time, now)
            color_map = {'O': (0.5, 0.7, 1, 1), 'M': (0.5, 1, 0.5, 1), 'N': (1, 1, 0.5, 1)}
            with self.timer_label.canvas.before:
                Color(*color_map[shift_letter])
                self._timer_rect = Rectangle(pos=self.timer_label.pos, size=self.timer_label.size)
        except Exception:
            pass

    def _log(self, text):
        lbl = Label(text=text, size_hint_y=None, height=28, color=COLOR_TEXT)
        self.log_grid.add_widget(lbl)

    def open_calendar(self, *_):
        CalendarPopup(self).open()

    def export_week_by_selected_day(self, selected_day_dt: datetime):
        """Export selected ISO week to PDF; write to user home folder. Handles missing shift gracefully."""
        try:
            iso_year, week_num, _ = selected_day_dt.isocalendar()
            monday = date.fromisocalendar(iso_year, week_num, 1)
            sunday = monday + timedelta(days=6)

            c.execute('SELECT clock_in, clock_out, duration, shift FROM shifts WHERE date(clock_in) BETWEEN ? AND ? ORDER BY clock_in',
                      (monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")))
            rows = c.fetchall()
            by_date = {datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").date(): r for r in rows}

            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=12)
            # Header: use ASCII hyphen instead of em-dash to avoid font encoding problems
            title_text = f"Timesheet - Week {week_num} ({monday} to {sunday})"
            pdf.set_font("Helvetica", "B", 14)
            pdf.cell(0, 10, title_text, border=0, align="C")
            pdf.ln(10)

            headers = ["Date", "Clock In", "Clock Out", "Hours", "Overtime", "Shift"]
            widths = [34, 34, 34, 26, 26, 20]

            pdf.set_font("Helvetica", "B", 11)
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 9, h, border=1, align="C")
            pdf.ln()

            pdf.set_font("Helvetica", "", 11)
            total_hours = 0.0
            total_ot = 0.0
            day = monday
            while day <= sunday:
                r = by_date.get(day)
                if r:
                    clock_in_s = datetime.strptime(r[0], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                    clock_out_s = datetime.strptime(r[1], "%Y-%m-%d %H:%M:%S").strftime("%H:%M")
                    hours = float(r[2])
                    overtime = max(0.0, hours - 8.0)
                    total_hours += hours
                    total_ot += overtime
                    shift_letter = r[3] if (r[3] is not None and r[3] != "") else ""
                    rgb = PDF_ROW_RGB.get(shift_letter, (255,255,255))
                    rcol = [int(max(0, min(255, int(v)))) for v in rgb]
                    pdf.set_fill_color(rcol[0], rcol[1], rcol[2])
                    pdf.cell(widths[0], 9, day.strftime("%Y-%m-%d"), border=1, align="C", fill=True)
                    pdf.cell(widths[1], 9, clock_in_s, border=1, align="C", fill=True)
                    pdf.cell(widths[2], 9, clock_out_s, border=1, align="C", fill=True)
                    pdf.cell(widths[3], 9, f"{hours:.2f}", border=1, align="C", fill=True)
                    pdf.cell(widths[4], 9, f"{overtime:.2f}", border=1, align="C", fill=True)
                    pdf.cell(widths[5], 9, shift_letter, border=1, align="C", fill=True)
                    pdf.ln()
                else:
                    pdf.cell(widths[0], 9, day.strftime("%Y-%m-%d"), border=1, align="C")
                    pdf.cell(widths[1], 9, "", border=1, align="C")
                    pdf.cell(widths[2], 9, "", border=1, align="C")
                    pdf.cell(widths[3], 9, "", border=1, align="C")
                    pdf.cell(widths[4], 9, "", border=1, align="C")
                    pdf.cell(widths[5], 9, "", border=1, align="C")
                    pdf.ln()
                day += timedelta(days=1)

            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(widths[0] + widths[1] + widths[2], 9, "Totals", border=1, align="R", fill=True)
            pdf.cell(widths[3], 9, f"{total_hours:.2f}", border=1, align="C", fill=True)
            pdf.cell(widths[4], 9, f"{total_ot:.2f}", border=1, align="C", fill=True)
            pdf.cell(widths[5], 9, "", border=1, align="C", fill=True)
            pdf.ln()

            # save to home folder
            home = os.path.expanduser("~")
            filename = safe_pdf_filename(week_num, iso_year, home)
            try:
                pdf.output(filename)
            except Exception as e_out:
                Popup(title="File Write Error", content=Label(text=f"Could not write PDF:\n{str(e_out)}"), size_hint=(0.8, 0.6)).open()
                print("PDF write traceback:", traceback.format_exc())
                return

            Popup(title="Export Complete", content=Label(text=f"Saved: {filename}", color=COLOR_TEXT), size_hint=(0.6, 0.4)).open()

        except Exception as e:
            tb = traceback.format_exc()
            print("Export failed:", tb)
            Popup(title="Export Error", content=Label(text=f"Error during export:\n{str(e)}\n\nSee console for traceback"), size_hint=(0.9, 0.8)).open()

# ---------- APP ----------
class TimesheetApp(App):
    def build(self):
        return TimeTracker()

if __name__ == "__main__":
    TimesheetApp().run()
