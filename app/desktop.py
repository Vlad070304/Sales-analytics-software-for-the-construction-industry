"""Local desktop interface for BuildSales Insight — no HTTP server required."""

from __future__ import annotations

import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk

from app.analytics import (
    CPRI_WEIGHTS,
    calibrate_cpri_weights,
    demand_forecast,
    forecast_accuracy,
    manager_scores,
    procurement_recommendation,
    seasonal_anomaly,
    shortage_risk,
)
from app.database import (
    add_material,
    add_sale,
    backup_database,
    connection,
    delete_material,
    fetch_events,
    fetch_materials,
    get_cpri_weights,
    initialize,
    log_event,
    preview_sales_csv,
    save_import_records,
    save_cpri_weights,
    update_material,
)
from app.export import export_sales_csv


class BuildSalesApp(tk.Tk):
    """Desktop interface for browsing, importing, and analysing construction sales."""

    def __init__(self) -> None:
        """Initialise window state and construct the application interface."""
        super().__init__()
        self.title("BuildSales Insight — аналітика продажів")
        self.geometry("1200x900")
        self.minsize(950, 760)
        self.configure(bg="#f7f8f3")
        self.filter_start = tk.StringVar()
        self.filter_end = tk.StringVar()
        self.filter_category = tk.StringVar(value="Усі категорії")
        self.filter_material = tk.StringVar(value="Усі матеріали")
        self.filter_manager = tk.StringVar(value="Усі менеджери")
        self.filter_customer = tk.StringVar(value="Усі клієнти")
        self.risk_details: dict[str, dict] = {}
        self.cpri_weights = get_cpri_weights()
        self.material_filter_combo: ttk.Combobox
        self.category_filter_combo: ttk.Combobox
        self.manager_filter_combo: ttk.Combobox
        self.customer_filter_combo: ttk.Combobox
        self.main_canvas: tk.Canvas
        self.main_content_window: int
        self.chart: tk.Canvas
        self.risk_table: ttk.Treeview
        self.manager_table: ttk.Treeview
        self.forecast_table: ttk.Treeview
        self._style()
        self._build()
        self.refresh()

    def _style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Treeview",
            rowheight=28,
            font=("Segoe UI", 10),
            background="white",
            fieldbackground="white",
        )
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), background="#eaf0e7")
        style.configure(
            "Accent.TButton",
            font=("Segoe UI", 10, "bold"),
            background="#c7e56c",
            foreground="#17372c",
            padding=10,
        )
        style.map("Accent.TButton", background=[("active", "#b2d553")])

    def _build(self) -> None:
        header = tk.Frame(self, bg="#17372c", padx=30, pady=22)
        header.pack(fill="x")
        titles = tk.Frame(header, bg="#17372c")
        titles.pack(side="left")
        tk.Label(
            titles,
            text="АНАЛІТИЧНА СИСТЕМА",
            fg="#c7e56c",
            bg="#17372c",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="BuildSales Insight",
            fg="white",
            bg="#17372c",
            font=("Georgia", 25, "bold"),
        ).pack(anchor="w")
        tk.Label(
            titles,
            text="Продажі будівельних матеріалів · локальний режим",
            fg="#d3dfd9",
            bg="#17372c",
            font=("Segoe UI", 10),
        ).pack(anchor="w")
        actions = tk.Frame(header, bg="#17372c")
        actions.pack(side="right")
        ttk.Button(actions, text="Допомога", command=self.show_help).pack(side="left", padx=(0, 8))
        ttk.Button(
            actions,
            text="Ваги CPRI",
            command=self.open_cpri_settings,
        ).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Журнал", command=self.open_event_log).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Резервна копія", command=self.create_backup).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Матеріали", command=self.open_materials).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Експортувати CSV", command=self.export_csv).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(actions, text="Імпортувати CSV", command=self.import_csv).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            actions,
            text="+ Додати продаж",
            style="Accent.TButton",
            command=self.open_sale_form,
        ).pack(side="left")
        body = self._scrollable_body()
        self._filter_bar(body)
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

    def _scrollable_body(self) -> tk.Frame:
        """Create the vertically scrollable dashboard area below the header."""
        container = tk.Frame(self, bg="#f7f8f3")
        container.pack(fill="both", expand=True)
        self.main_canvas = tk.Canvas(container, bg="#f7f8f3", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.main_canvas.yview)
        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        self.main_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        body = tk.Frame(self.main_canvas, bg="#f7f8f3", padx=24, pady=20)
        self.main_content_window = self.main_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>", self._update_scroll_region)
        self.main_canvas.bind("<Configure>", self._resize_scrollable_body)
        self.bind_all("<MouseWheel>", self._scroll_main_content, add="+")
        return body

    def _update_scroll_region(self, _event: object = None) -> None:
        """Update the main scrollbar after dashboard content changes size."""
        self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))

    def _resize_scrollable_body(self, event: tk.Event) -> None:
        """Keep the scrollable dashboard as wide as the application window."""
        self.main_canvas.itemconfigure(self.main_content_window, width=event.width)

    def _scroll_main_content(self, event: tk.Event) -> str | None:
        """Scroll the dashboard unless the pointer is over an analytical table."""
        widget = event.widget
        while widget is not None:
            if isinstance(widget, ttk.Treeview):
                return None
            parent_name = widget.winfo_parent()
            if not parent_name:
                break
            try:
                widget = self.nametowidget(parent_name)
            except KeyError:
                break
        self.main_canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    @staticmethod
    def _add_table_scrollbars(
        parent: tk.Widget, table: ttk.Treeview, horizontal: bool = False
    ) -> None:
        """Place a table in a frame with vertical and optional horizontal scrolling."""
        vertical = ttk.Scrollbar(parent, orient="vertical", command=table.yview)
        table.configure(yscrollcommand=vertical.set)
        vertical.pack(side="right", fill="y")
        if horizontal:
            bottom = ttk.Scrollbar(parent, orient="horizontal", command=table.xview)
            table.configure(xscrollcommand=bottom.set)
            bottom.pack(side="bottom", fill="x")
        table.pack(side="left", fill="both", expand=True)

    def _filter_bar(self, parent: tk.Frame) -> None:
        filters = ttk.LabelFrame(parent, text=" Фільтри аналітики ", padding=10)
        filters.pack(fill="x", pady=(0, 14))
        for column, (title, variable, width) in enumerate(
            [
                ("Дата від (YYYY-MM-DD)", self.filter_start, 15),
                ("Дата до (YYYY-MM-DD)", self.filter_end, 15),
            ]
        ):
            tk.Label(filters, text=title).grid(row=0, column=column * 2, sticky="w", padx=(0, 5))
            ttk.Entry(filters, textvariable=variable, width=width).grid(
                row=1, column=column * 2, sticky="w", padx=(0, 12)
            )
        tk.Label(filters, text="Матеріал").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.material_filter_combo = ttk.Combobox(
            filters, textvariable=self.filter_material, state="readonly", width=23
        )
        self.material_filter_combo.grid(row=1, column=4, sticky="w", padx=(0, 12))
        tk.Label(filters, text="Менеджер").grid(row=0, column=5, sticky="w", padx=(0, 5))
        self.manager_filter_combo = ttk.Combobox(
            filters, textvariable=self.filter_manager, state="readonly", width=21
        )
        self.manager_filter_combo.grid(row=1, column=5, sticky="w", padx=(0, 12))
        tk.Label(filters, text="Категорія").grid(
            row=2, column=0, sticky="w", padx=(0, 5), pady=(10, 0)
        )
        self.category_filter_combo = ttk.Combobox(
            filters, textvariable=self.filter_category, state="readonly", width=23
        )
        self.category_filter_combo.grid(row=3, column=0, sticky="w", padx=(0, 12))
        tk.Label(filters, text="Клієнт").grid(
            row=2, column=2, sticky="w", padx=(0, 5), pady=(10, 0)
        )
        self.customer_filter_combo = ttk.Combobox(
            filters, textvariable=self.filter_customer, state="readonly", width=23
        )
        self.customer_filter_combo.grid(row=3, column=2, sticky="w", padx=(0, 12))
        ttk.Button(
            filters,
            text="Застосувати",
            style="Accent.TButton",
            command=self.apply_filters,
        ).grid(row=3, column=4, sticky="w")
        ttk.Button(filters, text="Скинути", command=self.reset_filters).grid(
            row=3, column=5, sticky="w", padx=(8, 0)
        )

    def show_help(self) -> None:
        """Display a compact guide to the main user workflows."""
        messagebox.showinfo(
            "Як користуватися програмою",
            "1. Додайте продаж вручну або імпортуйте CSV.\n"
            "2. Використайте фільтри для потрібного періоду, матеріалу, клієнта чи менеджера.\n"
            "3. Двічі натисніть рядок CPRI, щоб побачити пояснення індексу.\n"
            "4. Експортуйте відфільтровані продажі до CSV.\n\n"
            "Детальна інструкція: файл START_HERE.md у папці програми.",
            parent=self,
        )

    def _overview(self, parent: tk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=" Місячна виручка, ₴ ", padding=14)
        frame.pack(fill="x", pady=(0, 14))
        self.chart = tk.Canvas(frame, height=175, bg="white", highlightthickness=0)
        self.chart.pack(fill="x")
        lower = tk.Frame(parent, bg="#f7f8f3", height=250)
        lower.pack(fill="both", expand=True)
        lower.pack_propagate(False)
        risk_frame = ttk.LabelFrame(lower, text=" Індекс пріоритету закупівлі CPRI ", padding=10)
        risk_frame.pack(side="left", fill="both", expand=True, padx=(0, 7))
        manager_frame = ttk.LabelFrame(lower, text=" Ефективність менеджерів ", padding=10)
        manager_frame.pack(side="left", fill="both", expand=True, padx=(7, 0))
        self.risk_table = ttk.Treeview(
            risk_frame,
            columns=("risk", "level", "stock", "order", "anomaly"),
            show="tree headings",
            height=7,
        )
        self.risk_table.heading("#0", text="Матеріал")
        self.risk_table.column("#0", width=175)
        self.manager_table = ttk.Treeview(
            manager_frame,
            columns=("score", "deals", "revenue"),
            show="headings",
            height=7,
        )
        for table, headings in (
            (
                self.risk_table,
                [
                    ("risk", "CPRI"),
                    ("level", "Рівень"),
                    ("stock", "Запас"),
                    ("order", "Закупити"),
                    ("anomaly", "Аномалія"),
                ],
            ),
            (
                self.manager_table,
                [("score", "Індекс"), ("deals", "Угод"), ("revenue", "Виручка, ₴")],
            ),
        ):
            for key, title in headings:
                table.heading(key, text=title)
                table.column(key, anchor="center", width=95)
            self._add_table_scrollbars(table.master, table)
        self.risk_table.bind("<Double-1>", self.open_cpri_explanation)

    def _forecast(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text=(
                "Прогноз: трендово-сезонна декомпозиція на 3 місяці. "
                "MAE, RMSE та MAPE — rolling backtesting. «Виграш» показує, на "
                "скільки % MAE моделі менша за наївний сезонний прогноз; "
                "від'ємне значення означає гірший результат. Базова MAE та виграш "
                "обчислюються лише за місяцями з відомим попереднім роком. "
                "«Закупити» додає страховий запас з похибки прогнозу; "
                "надійність показує відносну точність прогнозу. Сезонна аномалія "
                "порівнює останній місяць із тим самим місяцем попередніх років."
            ),
            bg="#f7f8f3",
            fg="#53645b",
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 10))
        columns = (
            "category",
            "stock",
            "risk",
            "month1",
            "month2",
            "month3",
            "mae",
            "rmse",
            "mape",
            "baseline_mae",
            "gain",
            "order",
            "confidence",
            "anomaly",
        )
        self.forecast_table = ttk.Treeview(parent, columns=columns, show="tree headings")
        self.forecast_table.heading("#0", text="Матеріал")
        self.forecast_table.column("#0", width=205)
        for key, title, width in [
            ("category", "Категорія", 125),
            ("stock", "Запас", 90),
            ("risk", "CPRI", 65),
            ("month1", "Місяць +1", 105),
            ("month2", "Місяць +2", 105),
            ("month3", "Місяць +3", 105),
            ("mae", "MAE", 65),
            ("rmse", "RMSE", 65),
            ("mape", "MAPE, %", 75),
            ("baseline_mae", "MAE базова", 85),
            ("gain", "Виграш, %", 80),
            ("order", "Закупити", 90),
            ("confidence", "Надійність, %", 105),
            ("anomaly", "Сезонна аномалія", 130),
        ]:
            self.forecast_table.heading(key, text=title)
            self.forecast_table.column(key, anchor="center", width=width)
        self._add_table_scrollbars(parent, self.forecast_table, horizontal=True)

    def metrics(self) -> tuple[dict, list[dict]]:
        """Calculate dashboard data for the active filter selection."""
        self.cpri_weights = get_cpri_weights()
        clauses: list[str] = []
        params: list[object] = []
        material_names = {item["name"]: item for item in fetch_materials()}
        selected_material = material_names.get(self.filter_material.get())
        scoped_materials = list(material_names.values())
        if self.filter_category.get() != "Усі категорії":
            scoped_materials = [
                material
                for material in scoped_materials
                if material["category"] == self.filter_category.get()
            ]
        if selected_material is not None:
            scoped_materials = [selected_material] if selected_material in scoped_materials else []
        if self.filter_start.get():
            clauses.append("sold_at >= ?")
            params.append(self.filter_start.get())
        if self.filter_end.get():
            clauses.append("sold_at <= ?")
            params.append(self.filter_end.get())
        if scoped_materials:
            placeholders = ", ".join("?" for _ in scoped_materials)
            clauses.append(f"material_id IN ({placeholders})")
            params.extend(material["id"] for material in scoped_materials)
        elif self.filter_category.get() != "Усі категорії":
            clauses.append("1 = 0")
        if self.filter_manager.get() != "Усі менеджери":
            clauses.append("manager = ?")
            params.append(self.filter_manager.get())
        if self.filter_customer.get() != "Усі клієнти":
            clauses.append("customer = ?")
            params.append(self.filter_customer.get())
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connection() as conn:
            sales = [
                dict(row)
                for row in conn.execute(f"SELECT * FROM sales{where} ORDER BY sold_at", params)
            ]
        monthly: dict[str, float] = {}
        for row in sales:
            period = row["sold_at"][:7]
            monthly[period] = monthly.get(period, 0) + row["quantity"] * row["unit_price"]
        materials = []
        for material in scoped_materials:
            material_clauses = ["material_id = ?", *clauses]
            material_params = [material["id"], *params]
            with connection() as conn:
                points = conn.execute(
                    "SELECT substr(sold_at, 1, 7) period, SUM(quantity) qty "
                    f"FROM sales WHERE {' AND '.join(material_clauses)} "
                    "GROUP BY period ORDER BY period",
                    material_params,
                ).fetchall()
            series = [(row["period"], row["qty"]) for row in points]
            forecast = demand_forecast(series)
            accuracy = forecast_accuracy(series)
            anomaly = seasonal_anomaly(series)
            materials.append(
                {
                    **material,
                    "forecast": forecast,
                    "accuracy": accuracy,
                    "anomaly": anomaly,
                    "weights": dict(self.cpri_weights),
                    "risk": shortage_risk(
                        [v for _, v in series][-12:],
                        material["stock"],
                        material["lead_time_days"],
                        forecast[0]["quantity"] if forecast else None,
                        weights=self.cpri_weights,
                    ),
                    "procurement": procurement_recommendation(
                        forecast[0]["quantity"] if forecast else None,
                        material["stock"],
                        material["lead_time_days"],
                        accuracy["mae"],
                    ),
                }
            )
        return {
            "sales": sales,
            "monthly": monthly,
            "materials": materials,
            "managers": manager_scores(sales),
        }, materials

    def apply_filters(self) -> None:
        """Validate date filters and update the dashboard."""
        try:
            start = date.fromisoformat(self.filter_start.get()) if self.filter_start.get() else None
            end = date.fromisoformat(self.filter_end.get()) if self.filter_end.get() else None
            if start and end and start > end:
                raise ValueError("Початкова дата не може бути пізніше кінцевої.")
            self.refresh()
        except ValueError as error:
            messagebox.showerror("Некоректний період", str(error), parent=self)

    def reset_filters(self) -> None:
        """Restore default filters and refresh all dashboard outputs."""
        self.filter_start.set("")
        self.filter_end.set("")
        self.filter_category.set("Усі категорії")
        self.filter_material.set("Усі матеріали")
        self.filter_manager.set("Усі менеджери")
        self.filter_customer.set("Усі клієнти")
        self.refresh()

    def refresh_filter_values(self) -> None:
        """Synchronise filter values with available materials and managers."""
        materials = fetch_materials()
        material_values = ["Усі матеріали", *[item["name"] for item in materials]]
        category_values = ["Усі категорії", *sorted({item["category"] for item in materials})]
        with connection() as conn:
            managers = [
                row[0]
                for row in conn.execute("SELECT DISTINCT manager FROM sales ORDER BY manager")
            ]
            customers = [
                row[0]
                for row in conn.execute("SELECT DISTINCT customer FROM sales ORDER BY customer")
            ]
        manager_values = ["Усі менеджери", *managers]
        customer_values = ["Усі клієнти", *customers]
        self.material_filter_combo["values"] = material_values
        self.category_filter_combo["values"] = category_values
        self.manager_filter_combo["values"] = manager_values
        self.customer_filter_combo["values"] = customer_values
        if self.filter_material.get() not in material_values:
            self.filter_material.set("Усі матеріали")
        if self.filter_manager.get() not in manager_values:
            self.filter_manager.set("Усі менеджери")
        if self.filter_category.get() not in category_values:
            self.filter_category.set("Усі категорії")
        if self.filter_customer.get() not in customer_values:
            self.filter_customer.set("Усі клієнти")

    def refresh(self) -> None:
        """Recalculate and redraw every dashboard component."""
        self.refresh_filter_values()
        data, materials = self.metrics()
        for child in self.kpi_frame.winfo_children():
            child.destroy()
        revenue = sum(s["quantity"] * s["unit_price"] for s in data["sales"])
        values = [
            (f"{revenue:,.0f} ₴", "Загальна виручка"),
            (str(len(data["sales"])), "Кількість угод"),
            (str(len(materials)), "Матеріали"),
            (
                str(sum(m["risk"]["level"] == "високий" for m in materials)),
                "Високий ризик",
            ),
        ]
        for value, label in values:
            card = tk.Frame(
                self.kpi_frame,
                bg="white",
                padx=16,
                pady=13,
                highlightbackground="#e6e9df",
                highlightthickness=1,
            )
            card.pack(side="left", fill="x", expand=True, padx=5)
            tk.Label(card, text=value, bg="white", fg="#17372c", font=("Georgia", 18, "bold")).pack(
                anchor="w"
            )
            tk.Label(card, text=label, bg="white", fg="#708078", font=("Segoe UI", 9)).pack(
                anchor="w", pady=(4, 0)
            )
        self.draw_chart(data["monthly"])
        for table in (self.risk_table, self.manager_table, self.forecast_table):
            table.delete(*table.get_children())
        self.risk_details = {}
        for m in materials:
            item_id = str(m["id"])
            self.risk_details[item_id] = m
            self.risk_table.insert(
                "",
                "end",
                iid=item_id,
                text=m["name"],
                values=(
                    m["risk"]["score"],
                    m["risk"]["level"],
                    f"{m['stock']} {m['unit']}",
                    f"{m['procurement']['order_quantity']} {m['unit']}",
                    "—" if m["anomaly"]["score"] is None else f"{m['anomaly']['score']:+.1f}%",
                ),
            )
            forecast = [f"{point['period']}: {point['quantity']}" for point in m["forecast"]]
            accuracy = m["accuracy"]
            quality = [
                "—" if accuracy[key] is None else accuracy[key] for key in ("mae", "rmse", "mape")
            ]
            quality += [
                "—" if accuracy["baseline"][key] is None else accuracy["baseline"][key]
                for key in ("mae", "gain_pct")
            ]
            self.forecast_table.insert(
                "",
                "end",
                text=m["name"],
                values=(
                    m["category"],
                    f"{m['stock']} {m['unit']}",
                    m["risk"]["score"],
                    *forecast,
                    *quality,
                    f"{m['procurement']['order_quantity']} {m['unit']}",
                    "—"
                    if m["procurement"]["confidence"] is None
                    else m["procurement"]["confidence"],
                    "—"
                    if m["anomaly"]["score"] is None
                    else f"{m['anomaly']['score']:+.1f}% ({m['anomaly']['direction']})",
                ),
            )
        for m in data["managers"]:
            self.manager_table.insert(
                "",
                "end",
                text=m["manager"],
                values=(m["score"], m["deals"], f"{m['revenue']:,.0f}"),
            )

    def open_cpri_explanation(self, _event: object = None) -> None:
        """Show component values and weighted contributions of the selected CPRI score."""
        selection = self.risk_table.selection()
        if not selection:
            return
        material = self.risk_details.get(selection[0])
        if material is None:
            return
        risk = material["risk"]
        window = tk.Toplevel(self)
        window.title(f"Пояснення CPRI — {material['name']}")
        window.transient(self)
        window.resizable(False, False)
        frame = tk.Frame(window, padx=24, pady=20)
        frame.pack()
        tk.Label(frame, text=material["name"], font=("Segoe UI", 16, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text=f"CPRI: {risk['score']} · {risk['level']} пріоритет закупівлі",
            fg="#176b4c",
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(4, 14))
        procurement = material["procurement"]
        anomaly = material["anomaly"]
        confidence = procurement["confidence"]
        confidence_text = "недостатньо даних" if confidence is None else f"{confidence}%"
        tk.Label(
            frame,
            text=(
                f"Рекомендована закупівля: {procurement['order_quantity']} {material['unit']} · "
                f"страховий запас: {procurement['safety_stock']} {material['unit']} · "
                f"надійність: {confidence_text} ({procurement['confidence_level']})"
            ),
            fg="#53645b",
            wraplength=590,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        anomaly_text = (
            "недостатньо даних"
            if anomaly["score"] is None
            else (
                f"{anomaly['score']:+.1f}% ({anomaly['direction']}); "
                f"база: {anomaly['baseline']}, факт: {anomaly['actual']}"
            )
        )
        tk.Label(
            frame,
            text=f"Сезонна аномалія останнього місяця: {anomaly_text}",
            fg="#53645b",
            wraplength=590,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        tk.Label(
            frame,
            text="Формула: 100 × ("
            + " + ".join(
                f"{material['weights'][key]:.2f}{letter}"
                for key, letter in (
                    ("demand", "D"),
                    ("volatility", "V"),
                    ("lead", "L"),
                    ("seasonality", "S"),
                )
            )
            + ")",
            fg="#53645b",
        ).pack(anchor="w", pady=(0, 8))
        table = ttk.Treeview(
            frame,
            columns=("value", "weight", "contribution"),
            show="headings",
            height=4,
        )
        for key, title, width in [
            ("value", "Нормоване значення", 160),
            ("weight", "Вага", 80),
            ("contribution", "Внесок у CPRI", 130),
        ]:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="center")
        components = [
            (
                "D — попит на строк постачання",
                risk["demand_component"],
                material["weights"]["demand"],
            ),
            (
                "V — нестабільність попиту",
                risk["volatility_component"],
                material["weights"]["volatility"],
            ),
            ("L — строк постачання", risk["lead_component"], material["weights"]["lead"]),
            (
                "S — сезонне прискорення",
                risk["seasonality_component"],
                material["weights"]["seasonality"],
            ),
        ]
        for label, value, weight in components:
            table.insert(
                "",
                "end",
                values=(f"{value:.3f}", f"{weight:.0%}", f"{value * weight * 100:.1f}"),
                text=label,
            )
        table["show"] = "tree headings"
        table.heading("#0", text="Компонент")
        table.column("#0", width=220)
        table.pack(fill="x")
        tk.Label(
            frame,
            text=(
                "Нормовані значення лежать у межах 0–1. Більший внесок означає "
                "вищий пріоритет поповнення запасу."
            ),
            wraplength=590,
            justify="left",
            fg="#53645b",
        ).pack(anchor="w", pady=(12, 0))

    def open_cpri_settings(self) -> None:
        """Allow an analyst to configure and persist explainable CPRI weights."""
        window = tk.Toplevel(self)
        window.title("Налаштування ваг CPRI")
        window.transient(self)
        window.grab_set()
        window.resizable(False, False)
        frame = tk.Frame(window, padx=24, pady=20)
        frame.pack()
        tk.Label(
            frame,
            text="Ваги індексу CPRI",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=(
                "Сума ваг повинна дорівнювати 1. Зміна ваг впливає на майбутні "
                "аналітичні розрахунки, але не змінює історію продажів."
            ),
            fg="#53645b",
            wraplength=440,
            justify="left",
        ).pack(anchor="w", pady=(4, 14))
        labels = {
            "demand": "D — попит на строк постачання",
            "volatility": "V — нестабільність попиту",
            "lead": "L — строк постачання",
            "seasonality": "S — сезонне прискорення",
        }
        entries: dict[str, ttk.Entry] = {}
        for key in CPRI_WEIGHTS:
            row = tk.Frame(frame)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=labels[key], width=34, anchor="w").pack(side="left")
            entry = ttk.Entry(row, width=10)
            entry.insert(0, str(self.cpri_weights[key]))
            entry.pack(side="right")
            entries[key] = entry
        total_label = tk.Label(frame, fg="#53645b")
        total_label.pack(anchor="w", pady=(10, 0))

        def current_weights() -> dict[str, float]:
            return {key: float(entry.get().replace(",", ".")) for key, entry in entries.items()}

        def show_total(*_args: object) -> None:
            try:
                total_label.configure(text=f"Поточна сума: {sum(current_weights().values()):.3f}")
            except ValueError:
                total_label.configure(text="Поточна сума: некоректне числове значення")

        for entry in entries.values():
            entry.bind("<KeyRelease>", show_total)
        show_total()

        def calibrate() -> None:
            """Offer weights calibrated on the stored sales history."""
            recommendation = self._cpri_calibration_recommendation()
            if recommendation["weights"] is None:
                messagebox.showinfo(
                    "Недостатньо даних",
                    "Для калібрування потрібні щонайменше 7 місячних значень продажів "
                    "хоча б для одного матеріалу.",
                    parent=window,
                )
                return
            weights = recommendation["weights"]
            for key, entry in entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, f"{weights[key]:.1f}")
            show_total()
            improvement = recommendation["improvement_pct"]
            improvement_text = "—" if improvement is None else f"{improvement:+.2f}%"
            messagebox.showinfo(
                "Рекомендація калібрування CPRI",
                "Ваги підготовлено у полях, але ще не збережено.\n\n"
                f"Ретроспективних спостережень: {recommendation['observations']}\n"
                f"Похибка експертних ваг: {recommendation['expert_mae']:.2f} в.п.\n"
                f"Похибка рекомендації: {recommendation['mae']:.2f} в.п.\n"
                f"Зміна похибки: {improvement_text}\n\n"
                "Перевірте значення та натисніть «Зберегти», щоб застосувати їх.",
                parent=window,
            )

        def restore_defaults() -> None:
            for key, entry in entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, str(CPRI_WEIGHTS[key]))
            show_total()

        def save() -> None:
            try:
                save_cpri_weights(current_weights())
            except ValueError as error:
                messagebox.showerror("Неможливо зберегти", str(error), parent=window)
                return
            window.destroy()
            self.refresh()

        controls = tk.Frame(frame)
        controls.pack(fill="x", pady=(16, 0))
        ttk.Button(controls, text="Калібрувати за історією", command=calibrate).pack(side="left")
        ttk.Button(controls, text="Стандартні ваги", command=restore_defaults).pack(side="left")
        ttk.Button(controls, text="Скасувати", command=window.destroy).pack(side="right")
        ttk.Button(
            controls,
            text="Зберегти",
            style="Accent.TButton",
            command=save,
        ).pack(side="right", padx=(0, 8))

    def _cpri_calibration_recommendation(self) -> dict:
        """Build historical one-period CPRI calibration scenarios from sales data."""
        scenarios: list[dict] = []
        with connection() as conn:
            rows = conn.execute(
                "SELECT material_id, substr(sold_at, 1, 7) AS period, SUM(quantity) AS quantity "
                "FROM sales GROUP BY material_id, period ORDER BY material_id, period"
            ).fetchall()
        series_by_material: dict[int, list[tuple[str, float]]] = {}
        for row in rows:
            series_by_material.setdefault(row["material_id"], []).append(
                (row["period"], float(row["quantity"]))
            )
        for material in fetch_materials():
            series = series_by_material.get(material["id"], [])
            for point in range(6, len(series)):
                history = series[:point]
                forecast = demand_forecast(history, horizon=1)[0]["quantity"]
                scenarios.append(
                    {
                        "values": [value for _, value in history][-12:],
                        "stock": material["stock"],
                        "lead_time_days": material["lead_time_days"],
                        "forecast": forecast,
                        "actual": series[point][1],
                    }
                )
        return calibrate_cpri_weights(scenarios)

    def draw_chart(self, monthly: dict[str, float]) -> None:
        """Draw the monthly-revenue bar chart on the canvas."""
        self.chart.delete("all")
        self.update_idletasks()
        width = max(self.chart.winfo_width(), 600)
        height = 160
        points = list(monthly.items())[-12:]
        maximum = max((value for _, value in points), default=1)
        gap = width / max(len(points), 1)
        for i, (period, value) in enumerate(points):
            x = i * gap + 12
            bar_height = (height - 25) * value / maximum
            self.chart.create_rectangle(
                x,
                height - 22 - bar_height,
                x + gap - 14,
                height - 22,
                fill="#176b4c",
                width=0,
            )
            self.chart.create_text(
                x + gap / 2 - 7,
                height - 10,
                text=period[5:],
                fill="#708078",
                font=("Segoe UI", 8),
            )

    def open_sale_form(self) -> None:
        """Open the form used to add one sales record."""
        window = tk.Toplevel(self)
        window.title("Новий продаж")
        window.transient(self)
        window.grab_set()
        window.resizable(False, False)
        form = tk.Frame(window, padx=24, pady=20)
        form.pack()
        fields = [
            ("Дата", "sold_at", date.today().isoformat()),
            ("Менеджер", "manager", ""),
            ("Клієнт", "customer", ""),
            ("Кількість", "quantity", ""),
            ("Ціна за одиницю, ₴", "unit_price", ""),
        ]
        entries = {}
        for title, key, default in fields:
            tk.Label(form, text=title, anchor="w").pack(fill="x", pady=(7, 0))
            entry = ttk.Entry(form, width=42)
            entry.insert(0, default)
            entry.pack(fill="x")
            entries[key] = entry
        tk.Label(form, text="Матеріал", anchor="w").pack(fill="x", pady=(7, 0))
        materials = fetch_materials()
        names = [m["name"] for m in materials]
        selected = tk.StringVar(value=names[0])
        ttk.Combobox(form, values=names, textvariable=selected, state="readonly", width=39).pack(
            fill="x"
        )

        def save() -> None:
            try:
                material = next(item for item in materials if item["name"] == selected.get())
                add_sale(
                    {
                        "sold_at": entries["sold_at"].get(),
                        "material_id": material["id"],
                        "manager": entries["manager"].get(),
                        "customer": entries["customer"].get(),
                        "quantity": entries["quantity"].get(),
                        "unit_price": entries["unit_price"].get(),
                    }
                )
                window.destroy()
                self.refresh()
            except (ValueError, StopIteration) as error:
                messagebox.showerror("Помилка введення", str(error), parent=window)

        ttk.Button(form, text="Зберегти продаж", style="Accent.TButton", command=save).pack(
            fill="x", pady=(16, 0)
        )

    def export_csv(self) -> None:
        """Save the active, filtered sales dataset to a local CSV file."""
        path = filedialog.asksaveasfilename(
            title="Зберегти експорт продажів",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="buildsales-export.csv",
        )
        if not path:
            return
        data, materials = self.metrics()
        material_map = {material["id"]: material for material in materials}
        rows = []
        for sale in data["sales"]:
            material = material_map.get(sale["material_id"])
            if material is None:
                continue
            rows.append(
                {
                    **sale,
                    "material": material["name"],
                    "category": material["category"],
                    "revenue": round(sale["quantity"] * sale["unit_price"], 2),
                }
            )
        try:
            destination = export_sales_csv(rows, path)
            messagebox.showinfo(
                "Експорт завершено",
                f"Експортовано записів: {len(rows)}.\nФайл: {destination}",
                parent=self,
            )
        except OSError as error:
            messagebox.showerror("Помилка експорту", str(error), parent=self)

    def open_materials(self) -> None:
        """Open the material directory and its create, update, and delete actions."""
        window = tk.Toplevel(self)
        window.title("Довідник матеріалів")
        window.geometry("800x430")
        window.transient(self)
        container = tk.Frame(window, padx=18, pady=18)
        container.pack(fill="both", expand=True)
        tk.Label(
            container,
            text="Матеріали та параметри постачання",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            container,
            text=(
                "Матеріали з історією продажів не можна видалити, щоб не втратити аналітичні дані."
            ),
            fg="#53645b",
        ).pack(anchor="w", pady=(3, 12))
        columns = ("category", "unit", "stock", "lead_time")
        table = ttk.Treeview(container, columns=columns, show="tree headings", selectmode="browse")
        table.heading("#0", text="Назва")
        table.column("#0", width=250)
        for key, title, width in [
            ("category", "Категорія", 180),
            ("unit", "Од.", 80),
            ("stock", "Запас", 100),
            ("lead_time", "Постачання, дн.", 130),
        ]:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="center")
        table.pack(fill="both", expand=True)

        def reload_table() -> None:
            table.delete(*table.get_children())
            for material in fetch_materials():
                table.insert(
                    "",
                    "end",
                    iid=str(material["id"]),
                    text=material["name"],
                    values=(
                        material["category"],
                        material["unit"],
                        material["stock"],
                        material["lead_time_days"],
                    ),
                )
            self.refresh()

        def selected_material() -> dict | None:
            selected = table.selection()
            if not selected:
                messagebox.showwarning(
                    "Оберіть матеріал",
                    "Спочатку оберіть матеріал у таблиці.",
                    parent=window,
                )
                return None
            return next(
                (item for item in fetch_materials() if item["id"] == int(selected[0])),
                None,
            )

        def open_editor(material: dict | None = None) -> None:
            editor = tk.Toplevel(window)
            editor.title("Новий матеріал" if material is None else "Редагувати матеріал")
            editor.transient(window)
            editor.grab_set()
            editor.resizable(False, False)
            form = tk.Frame(editor, padx=22, pady=18)
            form.pack()
            fields = [
                ("Назва", "name"),
                ("Категорія", "category"),
                ("Одиниця виміру", "unit"),
                ("Поточний запас", "stock"),
                ("Строк постачання, днів", "lead_time_days"),
            ]
            entries: dict[str, ttk.Entry] = {}
            for title, key in fields:
                tk.Label(form, text=title, anchor="w").pack(fill="x", pady=(6, 0))
                entry = ttk.Entry(form, width=42)
                if material is not None:
                    entry.insert(0, str(material[key]))
                entry.pack(fill="x")
                entries[key] = entry

            def save() -> None:
                payload = {key: entry.get() for key, entry in entries.items()}
                try:
                    if material is None:
                        add_material(payload)
                    else:
                        update_material(material["id"], payload)
                    editor.destroy()
                    reload_table()
                except ValueError as error:
                    messagebox.showerror("Помилка збереження", str(error), parent=editor)

            ttk.Button(form, text="Зберегти", style="Accent.TButton", command=save).pack(
                fill="x", pady=(14, 0)
            )

        controls = tk.Frame(container)
        controls.pack(fill="x", pady=(12, 0))
        ttk.Button(controls, text="+ Новий", command=open_editor).pack(side="left")

        def edit_selected() -> None:
            material = selected_material()
            if material is not None:
                open_editor(material)

        ttk.Button(controls, text="Редагувати", command=edit_selected).pack(side="left", padx=8)

        def remove() -> None:
            material = selected_material()
            if material is None or not messagebox.askyesno(
                "Підтвердження", f"Видалити «{material['name']}»?", parent=window
            ):
                return
            try:
                delete_material(material["id"])
                reload_table()
            except ValueError as error:
                messagebox.showerror("Неможливо видалити", str(error), parent=window)

        ttk.Button(controls, text="Видалити", command=remove).pack(side="left")
        reload_table()

    def import_csv(self) -> None:
        """Choose a CSV file, validate it locally, and open its review window."""
        path = filedialog.askopenfilename(
            title="Оберіть CSV-файл продажів",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            report = preview_sales_csv(path)
            self.open_import_preview(report)
        except (OSError, ValueError) as error:
            messagebox.showerror("Помилка імпорту", str(error), parent=self)

    def create_backup(self) -> None:
        """Create a timestamped manual database backup."""
        try:
            path = backup_database()
            log_event("manual_backup", f"Створено резервну копію: {path.name}")
            messagebox.showinfo(
                "Резервна копія створена",
                f"Базу даних збережено тут:\n{path}",
                parent=self,
            )
        except (OSError, ValueError) as error:
            messagebox.showerror("Помилка резервного копіювання", str(error), parent=self)

    def open_event_log(self) -> None:
        """Show recent imports and manual backup events."""
        window = tk.Toplevel(self)
        window.title("Журнал операцій")
        window.geometry("760x420")
        window.transient(self)
        frame = tk.Frame(window, padx=18, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Журнал операцій", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        tk.Label(
            frame,
            text="Показано останні 100 подій, пов'язаних зі зміною даних і резервним копіюванням.",
            fg="#53645b",
        ).pack(anchor="w", pady=(3, 12))
        table = ttk.Treeview(frame, columns=("time", "type", "details"), show="headings")
        for key, title, width in [
            ("time", "Час", 165),
            ("type", "Операція", 140),
            ("details", "Деталі", 390),
        ]:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="w")
        table.pack(fill="both", expand=True)
        names = {"csv_import": "Імпорт CSV", "manual_backup": "Резервна копія"}
        for event in fetch_events():
            table.insert(
                "",
                "end",
                values=(
                    event["created_at"].replace("T", " "),
                    names.get(event["event_type"], event["event_type"]),
                    event["details"],
                ),
            )

    def open_import_preview(self, report: dict) -> None:
        """Show validated CSV records and require explicit confirmation before saving."""
        if not report["records"]:
            details = "\n".join([*report["errors"][:5], *report["duplicate_details"][:5]])
            summary = (
                f"Дублікатів пропущено: {report['duplicates']}. " if report["duplicates"] else ""
            )
            messagebox.showwarning(
                "Немає даних для імпорту",
                f"{summary}Нових коректних записів не знайдено.\n{details}",
                parent=self,
            )
            return
        window = tk.Toplevel(self)
        window.title("Попередній перегляд імпорту")
        window.geometry("930x500")
        window.transient(self)
        window.grab_set()
        frame = tk.Frame(window, padx=18, pady=18)
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame,
            text="Перевірте дані перед збереженням",
            font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        details = f"Коректних рядків: {report['valid']}."
        if report["skipped"]:
            details += f" Пропущено з помилками: {report['skipped']}. " + " ".join(
                report["errors"][:2]
            )
        if report["duplicates"]:
            details += f" Дублікатів не буде імпортовано: {report['duplicates']}. " + " ".join(
                report["duplicate_details"][:2]
            )
        tk.Label(frame, text=details, fg="#53645b", wraplength=860, justify="left").pack(
            anchor="w", pady=(4, 12)
        )
        columns = ("date", "material", "manager", "customer", "quantity", "price")
        table = ttk.Treeview(frame, columns=columns, show="headings")
        for key, title, width in [
            ("date", "Дата", 95),
            ("material", "Матеріал", 180),
            ("manager", "Менеджер", 145),
            ("customer", "Клієнт", 180),
            ("quantity", "Кількість", 95),
            ("price", "Ціна, ₴", 100),
        ]:
            table.heading(key, text=title)
            table.column(key, width=width, anchor="center")
        table.pack(fill="both", expand=True)
        for row in report["records"][:100]:
            table.insert(
                "",
                "end",
                values=(
                    row["sold_at"],
                    row["material"],
                    row["manager"],
                    row["customer"],
                    row["quantity"],
                    row["unit_price"],
                ),
            )
        footer = tk.Frame(frame)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(
            footer,
            text="Показано перші 100 рядків." if report["valid"] > 100 else "Усі рядки показано.",
            fg="#53645b",
        ).pack(side="left")

        def confirm() -> None:
            inserted = save_import_records(report["records"])
            window.destroy()
            self.refresh()
            messagebox.showinfo(
                "Імпорт завершено", f"Імпортовано записів: {inserted}.", parent=self
            )

        ttk.Button(footer, text="Скасувати", command=window.destroy).pack(side="right")
        ttk.Button(footer, text="Підтвердити імпорт", style="Accent.TButton", command=confirm).pack(
            side="right", padx=(0, 8)
        )


def main() -> None:
    """Initialise the local store and start the desktop application."""
    initialize()
    BuildSalesApp().mainloop()


if __name__ == "__main__":
    main()
