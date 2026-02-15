from flask import Flask, render_template, request, redirect, url_for, session, Response, jsonify
import sqlite3
import pandas as pd
import os
import csv
import io
from datetime import date

app = Flask(__name__)
app.secret_key = "mic_transport_key"
DB_NAME = "bus_data.db"

# Admin credentials
ADMINS = {
    "Sravani": "Sravani12",
    "BRK Singh": "Singh12",
    "Abhishek": "abhi123"
}

# Principal credentials
PRINCIPALS = {
    "Vamseekiran": "Vamsee12"
}



# -------------------------------------------------
# DB CONNECTION
# -------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# -------------------------------------------------
# INIT DATABASE (SINGLE EXCEL SHEET)
# -------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS routes")
    cur.execute("DROP TABLE IF EXISTS buses")

    cur.execute("CREATE TABLE routes (route_no TEXT)")

    cur.execute("""
        CREATE TABLE buses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bus_rgdno TEXT,
            route_no TEXT,
            starting_at TEXT,
            driver_name TEXT,
            contact_no TEXT,
            year_reg TEXT,
            make_model TEXT,
            year_expiry TEXT,
            capacity TEXT,
            fc_date TEXT,
            insurance_date TEXT,
            permit_expiry TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS fuel_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            veh_no TEXT,
            reading TEXT,
            oil TEXT,
            kms TEXT,
            mileage TEXT
        )
    """)

    try:
        file_path = "Project Data.xlsx"
        if not os.path.exists(file_path):
            print("❌ Excel file not found")
            return

        xls = pd.ExcelFile(file_path)
        print("📄 Available Excel Sheets:", xls.sheet_names)

        sheet_name = xls.sheet_names[0]
        df = pd.read_excel(file_path, sheet_name=sheet_name)

        df.columns = [
            str(c).strip().lower()
            .replace(".", "")
            .replace("/", "")
            .replace(" ", "")
            for c in df.columns
        ]

        # ROUTES
        if "routeno" in df.columns:
            for r in df["routeno"].dropna().unique():
                cur.execute("INSERT INTO routes (route_no) VALUES (?)", (str(r),))

        # BUSES
        for _, row in df.iterrows():
            if pd.isna(row.get("busrgdno")):
                continue

            cur.execute("""
                INSERT INTO buses (
                    bus_rgdno, route_no, starting_at, driver_name, contact_no,
                    year_reg, make_model, year_expiry,
                    capacity, fc_date, insurance_date, permit_expiry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(row.get("busrgdno", "")),
                str(row.get("routeno", "")),
                str(row.get("startingat", "")),
                str(row.get("driver", "")),
                str(row.get("cell", "")).split(",")[0].strip(), 
                str(row.get("yearoffirstregistration", "")),
                str(row.get("makemodelofvehicle", "")),
                str(row.get("yearofexpairy", "")),
                str(row.get("capacity", "")),
                str(row.get("fcdateupto", "")),
                str(row.get("insurancedateupto", "")),
                str(row.get("permitexpireon", ""))
            ))

        print("✅ Master data loaded successfully")

    except Exception as e:
        print("❌ DB INIT ERROR:", e)

    conn.commit()
    conn.close()

# -------------------------------------------------
# ROUTES
# -------------------------------------------------
@app.route("/")
def home():
    conn = get_db_connection()
    routes = [r['route_no'] for r in conn.execute("SELECT route_no FROM routes").fetchall()]
    conn.close()
    return render_template("page1_home.html", routes=routes)

@app.route("/login", methods=['GET', 'POST'])
def login():
    route_no = request.args.get('route')
    if route_no:
        session['selected_route'] = route_no
    if request.method == 'POST':
        username = request.form.get('user')
        password = request.form.get('pwd')
        role = request.form.get('role')
        
        # Check admin credentials
        if role == 'Admin':
            if username in ADMINS and ADMINS[username] == password:
                session['role'] = 'admin'
                session['username'] = username
                return redirect(url_for('driver_entry'))
            else:
                return render_template("page2_login.html", error="Invalid admin credentials")
        elif role == 'Principal':
            if username in PRINCIPALS and PRINCIPALS[username] == password:
                session['role'] = 'principal'
                session['username'] = username
                return redirect(url_for('driver_entry'))
            else:
                return render_template("page2_login.html", error="Invalid principal credentials")
        else:
            # Non-admin users can proceed
            session['role'] = 'user'
            return redirect(url_for('driver_entry'))
    return render_template("page2_login.html")

@app.route("/driver_entry", methods=['GET', 'POST'])
def driver_entry():
    if request.method == 'POST':
        return redirect(url_for('fuel_entry'))
    return render_template("page3_driver.html")

@app.route("/fuel_entry", methods=['GET', 'POST'])
def fuel_entry():
    conn = get_db_connection()

    if request.method == 'POST':
        veh_no = ""  # Model number removed from form
        old_reading = float(request.form.get('old_reading', 0) or 0)
        today_reading = float(request.form.get('today_reading', 0) or 0)
        
        # Store old reading in 'oil' column and today's reading in 'reading' column
        conn.execute("""
            INSERT INTO fuel_entries (date, veh_no, reading, oil, kms, mileage)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            request.form.get('date'),
            veh_no,
            today_reading,
            old_reading,
            "",
            ""
        ))
        conn.commit()
        conn.close()
        return redirect(url_for('fuel_entry'))

    # Get the last reading to populate as old reading for the next entry
    # Use 'oil' column which stores the combined (old + new) value
    last_entry = conn.execute("SELECT oil FROM fuel_entries ORDER BY id DESC LIMIT 1").fetchone()
    last_reading = last_entry['oil'] if last_entry else 0
    
    entries = conn.execute("SELECT * FROM fuel_entries ORDER BY id DESC").fetchall()
    conn.close()
    today = date.today().strftime('%Y-%m-%d')
    return render_template("page4_fuel.html", entries=entries, today=today, last_reading=last_reading)

@app.route("/master_details", methods=['GET', 'POST'])
def master_details():
    conn = get_db_connection()

    # --- HANDLE THE UPDATE (POST) ---
    if request.method == 'POST':
        try:
            bus_id = request.form.get('bus_id')
            
            # Collect all data from the modal form
            updated_values = (
                request.form.get('route_no'),
                request.form.get('starting_at'),
                request.form.get('driver_name'),
                request.form.get('contact_no'),
                request.form.get('Year of First Registration'),
                request.form.get('make_model'),
                request.form.get('Year of Expairy'),
                request.form.get('capacity'),
                request.form.get('fc_date'),
                request.form.get('insurance_date'),
                request.form.get('permit_expiry'),
                bus_id
            )

            # Update the record in SQLite
            conn.execute("""
                UPDATE buses 
                SET route_no=?, starting_at=?, driver_name=?, contact_no=?, 
                    year_reg=?, make_model=?, year_expiry=?, capacity=?, 
                    fc_date=?, insurance_date=?, permit_expiry=? 
                WHERE id=?
            """, updated_values)
            
            conn.commit()
            print(f"Bus ID {bus_id} updated successfully!")
        except Exception as e:
            print(f"Error updating: {e}")
        finally:
            conn.close()
            # Redirect back to the same page to refresh the table
            return redirect(url_for('master_details'))

    # --- HANDLE THE VIEW (GET) ---
    buses = conn.execute("SELECT * FROM buses").fetchall()
    conn.close()
    return render_template("page5_master.html", buses=buses)

@app.route("/get_bus_details/<bus_no>")
def get_bus_details(bus_no):
    bus_no = bus_no.replace(" ", "").upper()

    conn = get_db_connection()
    bus = conn.execute("""
        SELECT * FROM buses
        WHERE REPLACE(UPPER(bus_rgdno), ' ', '') = ?
    """, (bus_no,)).fetchone()
    conn.close()

    if not bus:
        return jsonify({"error": "Bus not found"}), 404

    return jsonify({
        "bus_rgdno": bus["bus_rgdno"],
        "route_no": bus["route_no"],
        "driver_name": bus["driver_name"],
        "contact_no": bus["contact_no"],
        "starting_at": bus["starting_at"]
    })

# -------------------------------------------------
# ✅ CSV EXPORT (THIS FIXES THE ERROR)
# -------------------------------------------------
@app.route("/download_csv")
def download_csv():
    conn = get_db_connection()
    entries = conn.execute("SELECT * FROM fuel_entries").fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Vehicle No", "Reading", "Oil", "KMs", "Mileage"])

    for e in entries:
        writer.writerow([
            e["date"], e["veh_no"], e["reading"],
            e["oil"], e["kms"], e["mileage"]
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=fuel_report.csv"}
    )

# -------------------------------------------------
# START
# -------------------------------------------------
if __name__ == "__main__":
    init_db()
    app.run(debug=False)
else:
    # For production (Gunicorn)
    init_db()
