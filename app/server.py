"""Dependency-free HTTP server for BuildSales Insight."""
from __future__ import annotations

import json
import mimetypes
import sqlite3
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from app.analytics import demand_forecast, manager_scores, shortage_risk
from app.database import add_sale, connection, fetch_materials, initialize

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def sales_rows() -> list[dict]:
    with connection() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM sales ORDER BY sold_at")]


def monthly_material_sales(material_id: int) -> list[tuple[str, float]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT substr(sold_at, 1, 7) period, SUM(quantity) quantity FROM sales WHERE material_id = ? GROUP BY period ORDER BY period",
            (material_id,),
        ).fetchall()
    return [(row["period"], row["quantity"]) for row in rows]


def dashboard() -> dict:
    rows = sales_rows()
    total_revenue = sum(row["quantity"] * row["unit_price"] for row in rows)
    monthly: dict[str, float] = {}
    for row in rows:
        key = row["sold_at"][:7]
        monthly[key] = monthly.get(key, 0) + row["quantity"] * row["unit_price"]
    materials = []
    for material in fetch_materials():
        series = monthly_material_sales(material["id"])
        quantities = [value for _, value in series]
        materials.append({**material, "forecast": demand_forecast(series), "risk": shortage_risk(quantities[-12:], material["stock"], material["lead_time_days"])})
    return {
        "kpi": {"revenue": round(total_revenue, 2), "deals": len(rows), "materials": len(materials), "high_risk": sum(item["risk"]["level"] == "високий" for item in materials)},
        "monthly_revenue": [{"period": period, "revenue": round(value, 2)} for period, value in monthly.items()],
        "materials": materials,
        "managers": manager_scores(rows),
    }


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/dashboard":
            return self.respond_json(dashboard())
        if path == "/api/materials":
            return self.respond_json(fetch_materials())
        if path == "/" or path == "/index.html":
            return self.serve_file(STATIC_DIR / "index.html")
        target = (STATIC_DIR / path.lstrip("/")).resolve()
        if STATIC_DIR.resolve() not in target.parents or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.serve_file(target)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/sales":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            sale_id = add_sale(payload)
            self.respond_json({"id": sale_id}, HTTPStatus.CREATED)
        except (ValueError, TypeError, json.JSONDecodeError, sqlite3.Error) as error:
            self.respond_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def serve_file(self, target: Path) -> None:
        content = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(target.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def respond_json(self, data: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, *_: object) -> None:
        return


def main() -> None:
    initialize()
    server = ThreadingHTTPServer(("127.0.0.1", 8000), Handler)
    print("BuildSales Insight: http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
