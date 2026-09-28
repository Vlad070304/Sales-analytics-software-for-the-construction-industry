"""Local desktop interface for BuildSales Insight — no HTTP server required."""
from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from app.analytics import demand_forecast, manager_scores, shortage_risk
from app.database import add_material, add_sale, connection, delete_material, fetch_materials, initialize, preview_sales_csv, save_import_records, update_material


class BuildSalesApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("BuildSales Insight — аналітика продажів")
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.configure(bg="#f7f8f3")
        self._style()
        self._build()
        self.refresh()

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10), background="white", fieldbackground="white")
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#eaf0e7")
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), background="#c7e56c", foreground="#17372c", padding=10)
        style.map("Accent.TButton", background=[("active", "#b2d553")])

    def _build(self) -> None:
        header = tk.Frame(self, bg="#17372c", padx=30, pady=22)
        header.pack(fill="x")
        tk.Label(header, text="АНАЛІТИЧНА СИСТЕМА", fg="#c7e56c", bg="#17372c", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(header, text="BuildSales Insight", fg="white", bg="#17372c", font=("Georgia", 25, "bold")).pack(anchor="w")
        tk.Label(header, text="Продажі будівельних матеріалів · локальний режим", fg="#d3dfd9", bg="#17372c", font=("Segoe UI", 10)).pack(anchor="w")
        actions = tk.Frame(header, bg="#17372c")
        actions.pack(anchor="e", side="right", pady=-50)
        ttk.Button(actions, text="Матеріали", command=self.open_materials).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Імпортувати CSV", command=self.import_csv).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="+ Додати продаж", style="Accent.TButton", command=self.open_sale_form).pack(side="left")
        body = tk.Frame(self, bg="#f7f8f3", padx=24, pady=20)
        body.pack(fill="both", expand=True)
        self.kpi_frame = tk.Frame(body, bg="#f7f8f3")
        self.kpi_frame.pack(fill="x", pady=(0, 14))
        notebook = ttk.Notebook(body)
        notebook.pack(fill="both", expand=True)
        overview = tk.Frame(notebook, bg="#f7f8f3", padx=12, pady=12)
        forecast = tk.Frame(notebook, bg="#f7f8f3", padx=12, pady=12)
        notebook.add(overview, text="  Огляд і ризики  ")
        notebook.add(forecast, text="  Прогноз попиту  ")
        self._overview(overview)
        self._forecast(forecast)

    def _overview(self, parent: tk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" Місячна виручка, ₴ ", padding=14)
        frame.pack(fill="x", pady=(0, 14))
        self.chart = tk.Canvas(frame, height=175, bg="white", highlightthickness=0)
        self.chart.pack(fill="x")
        lower = tk.Frame(parent, bg="#f7f8f3")
        lower.pack(fill="both", expand=True)
        risk_frame = ttk.LabelFrame(lower, text=" Індекс пріоритету закупівлі CPRI ", padding=10)
        risk_frame.pack(side="left", fill="both", expand=True, padx=(0, 7))
        manager_frame = ttk.LabelFrame(lower, text=" Ефективність менеджерів ", padding=10)
        manager_frame.pack(side="left", fill="both", expand=True, padx=(7, 0))
        self.risk_table = ttk.Treeview(risk_frame, columns=("risk", "level", "stock"), show="headings")
        self.manager_table = ttk.Treeview(manager_frame, columns=("score", "deals", "revenue"), show="headings")
        for table, headings in ((self.risk_table, [("risk", "CPRI"), ("level", "Рівень"), ("stock", "Запас")]), (self.manager_table, [("score", "Індекс"), ("deals", "Угод"), ("revenue", "Виручка, ₴")])):
            for key, title in headings: table.heading(key, text=title); table.column(key, anchor="center", width=95)
            table.pack(fill="both", expand=True)

    def _forecast(self, parent: tk.Frame) -> None:
        tk.Label(parent, text="Прогноз розраховано методом трендово-сезонної декомпозиції на 3 місяці.", bg="#f7f8f3", fg="#53645b", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 10))
        columns = ("category", "stock", "risk", "month1", "month2", "month3")
        self.forecast_table = ttk.Treeview(parent, columns=columns, show="tree headings")
        self.forecast_table.heading("#0", text="Матеріал")
        self.forecast_table.column("#0", width=205)
        for key, title in [("category", "Категорія"), ("stock", "Запас"), ("risk", "CPRI"), ("month1", "Місяць +1"), ("month2", "Місяць +2"), ("month3", "Місяць +3")]:
            self.forecast_table.heading(key, text=title); self.forecast_table.column(key, anchor="center", width=125)
        self.forecast_table.pack(fill="both", expand=True)

    def metrics(self) -> tuple[dict, list[dict]]:
        with connection() as conn:
            sales = [dict(row) for row in conn.execute("SELECT * FROM sales ORDER BY sold_at")]
        monthly: dict[str, float] = {}
        for row in sales:
            period = row["sold_at"][:7]
            monthly[period] = monthly.get(period, 0) + row["quantity"] * row["unit_price"]
        materials = []
        for material in fetch_materials():
            with connection() as conn:
                points = conn.execute("SELECT substr(sold_at, 1, 7) period, SUM(quantity) qty FROM sales WHERE material_id=? GROUP BY period ORDER BY period", (material["id"],)).fetchall()
            series = [(row["period"], row["qty"]) for row in points]
            forecast = demand_forecast(series)
            materials.append({**material, "forecast": forecast, "risk": shortage_risk([v for _, v in series][-12:], material["stock"], material["lead_time_days"], forecast[0]["quantity"] if forecast else None)})
        return {"sales": sales, "monthly": monthly, "materials": materials, "managers": manager_scores(sales)}, materials

    def refresh(self) -> None:
        data, materials = self.metrics()
        for child in self.kpi_frame.winfo_children(): child.destroy()
        revenue = sum(s["quantity"] * s["unit_price"] for s in data["sales"])
        values = [(f"{revenue:,.0f} ₴", "Загальна виручка"), (str(len(data["sales"])), "Кількість угод"), (str(len(materials)), "Матеріали"), (str(sum(m["risk"]["level"] == "високий" for m in materials)), "Високий ризик")]
        for value, label in values:
            card = tk.Frame(self.kpi_frame, bg="white", padx=16, pady=13, highlightbackground="#e6e9df", highlightthickness=1)
            card.pack(side="left", fill="x", expand=True, padx=5)
            tk.Label(card, text=value, bg="white", fg="#17372c", font=("Georgia", 18, "bold")).pack(anchor="w")
            tk.Label(card, text=label, bg="white", fg="#708078", font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        self.draw_chart(data["monthly"])
        for table in (self.risk_table, self.manager_table, self.forecast_table):
            table.delete(*table.get_children())
        for m in materials:
            self.risk_table.insert("", "end", text=m["name"], values=(m["risk"]["score"], m["risk"]["level"], f"{m['stock']} {m['unit']}"))
            forecast = [f"{point['period']}: {point['quantity']}" for point in m["forecast"]]
            self.forecast_table.insert("", "end", text=m["name"], values=(m["category"], f"{m['stock']} {m['unit']}", m["risk"]["score"], *forecast))
        for m in data["managers"]:
            self.manager_table.insert("", "end", text=m["manager"], values=(m["score"], m["deals"], f"{m['revenue']:,.0f}"))

    def draw_chart(self, monthly: dict[str, float]) -> None:
        self.chart.delete("all")
        self.update_idletasks(); width = max(self.chart.winfo_width(), 600); height = 160
        points = list(monthly.items())[-12:]; maximum = max((value for _, value in points), default=1)
        gap = width / max(len(points), 1)
        for i, (period, value) in enumerate(points):
            x = i * gap + 12; bar = (height - 25) * value / maximum
            self.chart.create_rectangle(x, height - 22 - bar, x + gap - 14, height - 22, fill="#176b4c", width=0)
            self.chart.create_text(x + gap / 2 - 7, height - 10, text=period[5:], fill="#708078", font=("Segoe UI", 8))

    def open_sale_form(self) -> None:
        window = tk.Toplevel(self); window.title("Новий продаж"); window.transient(self); window.grab_set(); window.resizable(False, False)
        form = tk.Frame(window, padx=24, pady=20); form.pack()
        fields = [("Дата", "sold_at", date.today().isoformat()), ("Менеджер", "manager", ""), ("Клієнт", "customer", ""), ("Кількість", "quantity", ""), ("Ціна за одиницю, ₴", "unit_price", "")]
        entries = {}
        for title, key, default in fields:
            tk.Label(form, text=title, anchor="w").pack(fill="x", pady=(7, 0)); entry = ttk.Entry(form, width=42); entry.insert(0, default); entry.pack(fill="x"); entries[key] = entry
        tk.Label(form, text="Матеріал", anchor="w").pack(fill="x", pady=(7, 0))
        materials = fetch_materials(); names = [m["name"] for m in materials]; selected = tk.StringVar(value=names[0]); ttk.Combobox(form, values=names, textvariable=selected, state="readonly", width=39).pack(fill="x")
        def save() -> None:
            try:
                material = next(item for item in materials if item["name"] == selected.get())
                add_sale({"sold_at": entries["sold_at"].get(), "material_id": material["id"], "manager": entries["manager"].get(), "customer": entries["customer"].get(), "quantity": float(entries["quantity"].get()), "unit_price": float(entries["unit_price"].get())})
                window.destroy(); self.refresh()
            except (ValueError, StopIteration) as error: messagebox.showerror("Помилка введення", str(error), parent=window)
        ttk.Button(form, text="Зберегти продаж", style="Accent.TButton", command=save).pack(fill="x", pady=(16, 0))

    def open_materials(self) -> None:
        window = tk.Toplevel(self)
        window.title("Довідник матеріалів")
        window.geometry("800x430")
        window.transient(self)
        container = tk.Frame(window, padx=18, pady=18)
        container.pack(fill="both", expand=True)
        tk.Label(container, text="Матеріали та параметри постачання", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(container, text="Матеріали з історією продажів не можна видалити, щоб не втратити аналітичні дані.", fg="#53645b").pack(anchor="w", pady=(3, 12))
        columns = ("category", "unit", "stock", "lead_time")
        table = ttk.Treeview(container, columns=columns, show="tree headings", selectmode="browse")
        table.heading("#0", text="Назва"); table.column("#0", width=250)
        for key, title, width in [("category", "Категорія", 180), ("unit", "Од.", 80), ("stock", "Запас", 100), ("lead_time", "Постачання, дн.", 130)]:
            table.heading(key, text=title); table.column(key, width=width, anchor="center")
        table.pack(fill="both", expand=True)

        def reload_table() -> None:
            table.delete(*table.get_children())
            for material in fetch_materials():
                table.insert("", "end", iid=str(material["id"]), text=material["name"], values=(material["category"], material["unit"], material["stock"], material["lead_time_days"]))
            self.refresh()

        def selected_material() -> dict | None:
            selected = table.selection()
            if not selected:
                messagebox.showwarning("Оберіть матеріал", "Спочатку оберіть матеріал у таблиці.", parent=window)
                return None
            return next((item for item in fetch_materials() if item["id"] == int(selected[0])), None)

        def open_editor(material: dict | None = None) -> None:
            editor = tk.Toplevel(window)
            editor.title("Новий матеріал" if material is None else "Редагувати матеріал")
            editor.transient(window); editor.grab_set(); editor.resizable(False, False)
            form = tk.Frame(editor, padx=22, pady=18); form.pack()
            fields = [("Назва", "name"), ("Категорія", "category"), ("Одиниця виміру", "unit"), ("Поточний запас", "stock"), ("Строк постачання, днів", "lead_time_days")]
            entries: dict[str, ttk.Entry] = {}
            for title, key in fields:
                tk.Label(form, text=title, anchor="w").pack(fill="x", pady=(6, 0))
                entry = ttk.Entry(form, width=42)
                if material is not None:
                    entry.insert(0, str(material[key]))
                entry.pack(fill="x"); entries[key] = entry
            def save() -> None:
                payload = {key: entry.get() for key, entry in entries.items()}
                try:
                    if material is None:
                        add_material(payload)
                    else:
                        update_material(material["id"], payload)
                    editor.destroy(); reload_table()
                except ValueError as error:
                    messagebox.showerror("Помилка збереження", str(error), parent=editor)
            ttk.Button(form, text="Зберегти", style="Accent.TButton", command=save).pack(fill="x", pady=(14, 0))

        controls = tk.Frame(container)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Button(controls, text="+ Новий", command=lambda: open_editor()).pack(side="left")
        ttk.Button(controls, text="Редагувати", command=lambda: (lambda item: open_editor(item) if item else None)(selected_material())).pack(side="left", padx=8)
        def remove() -> None:
            material = selected_material()
            if material is None or not messagebox.askyesno("Підтвердження", f"Видалити «{material['name']}»?", parent=window):
                return
            try:
                delete_material(material["id"]); reload_table()
            except ValueError as error:
                messagebox.showerror("Неможливо видалити", str(error), parent=window)
        ttk.Button(controls, text="Видалити", command=remove).pack(side="left")
        reload_table()

    def import_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Оберіть CSV-файл продажів", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            report = preview_sales_csv(path)
            self.open_import_preview(report)
        except (OSError, ValueError) as error:
            messagebox.showerror("Помилка імпорту", str(error), parent=self)

    def open_import_preview(self, report: dict) -> None:
        if not report["records"]:
            details = "\n".join(report["errors"][:5])
            messagebox.showwarning("Немає даних для імпорту", f"Коректних записів не знайдено.\n{details}", parent=self)
            return
        window = tk.Toplevel(self)
        window.title("Попередній перегляд імпорту")
        window.geometry("930x500")
        window.transient(self); window.grab_set()
        frame = tk.Frame(window, padx=18, pady=18); frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Перевірте дані перед збереженням", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        details = f"Коректних рядків: {report['valid']}."
        if report["skipped"]:
            details += f" Пропущено: {report['skipped']}. " + " ".join(report["errors"][:2])
        tk.Label(frame, text=details, fg="#53645b", wraplength=860, justify="left").pack(anchor="w", pady=(4, 12))
        columns = ("date", "material", "manager", "customer", "quantity", "price")
        table = ttk.Treeview(frame, columns=columns, show="headings")
        for key, title, width in [("date", "Дата", 95), ("material", "Матеріал", 180), ("manager", "Менеджер", 145), ("customer", "Клієнт", 180), ("quantity", "Кількість", 95), ("price", "Ціна, ₴", 100)]:
            table.heading(key, text=title); table.column(key, width=width, anchor="center")
        table.pack(fill="both", expand=True)
        for row in report["records"][:100]:
            table.insert("", "end", values=(row["sold_at"], row["material"], row["manager"], row["customer"], row["quantity"], row["unit_price"]))
        footer = tk.Frame(frame); footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, text="Показано перші 100 рядків." if report["valid"] > 100 else "Усі рядки показано.", fg="#53645b").pack(side="left")
        def confirm() -> None:
            inserted = save_import_records(report["records"])
            window.destroy(); self.refresh()
            messagebox.showinfo("Імпорт завершено", f"Імпортовано записів: {inserted}.", parent=self)
        ttk.Button(footer, text="Скасувати", command=window.destroy).pack(side="right")
        ttk.Button(footer, text="Підтвердити імпорт", style="Accent.TButton", command=confirm).pack(side="right", padx=(0, 8))


def main() -> None:
    initialize()
    BuildSalesApp().mainloop()


if __name__ == "__main__":
    main()
