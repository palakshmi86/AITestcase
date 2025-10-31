from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # type: ignore
import httpx
from flask import Flask, render_template_string, request, send_file, redirect, make_response
import io
import csv
import sqlite3
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

client = httpx.Client(verify=False)

# Recommended LLM for this use case: DeepSeek Coder V2 or Llama-3-70B-Instruct (strong at reasoning, classification, and code)
llm = ChatOpenAI(
    base_url="https://genailab.tcs.in",
    model="azure_ai/genailab-maas-Llama-3.2-90B-Vision-Instruct",  # Use Llama-3 or DeepSeek Coder V2 if available
    api_key="sk-PtyiLsD4c2vzzs9gXRK5Kw",
    http_client=client,
)

app = Flask(__name__)
DB_PATH = 'inventory.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        abc_class TEXT NOT NULL
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS thresholds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_name TEXT NOT NULL,
        min_threshold INTEGER NOT NULL,
        max_threshold INTEGER NOT NULL
    )''')
    conn.commit()
    conn.close()

init_db()

def get_inventory():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT name, quantity, unit_cost, abc_class FROM inventory')
    items = [
        {'name': row[0], 'quantity': row[1], 'unit_cost': row[2], 'abc_class': row[3]} for row in c.fetchall()
    ]
    conn.close()
    return items

def add_inventory_item(name, quantity, unit_cost, abc_class):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('INSERT INTO inventory (name, quantity, unit_cost, abc_class) VALUES (?, ?, ?, ?)',
              (name, quantity, unit_cost, abc_class))
    conn.commit()
    conn.close()

def get_thresholds():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT item_name, min_threshold, max_threshold FROM thresholds')
    thresholds = {row[0]: {'min': row[1], 'max': row[2]} for row in c.fetchall()}
    conn.close()
    return thresholds

def set_threshold(item_name, min_threshold, max_threshold):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO thresholds (id, item_name, min_threshold, max_threshold)
        VALUES ((SELECT id FROM thresholds WHERE item_name=?), ?, ?, ?)''',
        (item_name, item_name, min_threshold, max_threshold))
    conn.commit()
    conn.close()

HTML_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Inventory Dashboard</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    body { background: #f8f9fa; }
    .sidebar { min-height: 100vh; background: #fff; border-right: 1px solid #eee; }
    .sidebar .nav-link.active { background: #e9ecef; font-weight: bold; }
    .category-card { color: #fff; border-radius: 10px; }
    .category-a { background: #2563eb; }
    .category-b { background: #22c55e; }
    .category-c { background: #f59e42; }
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <nav class="col-md-2 d-none d-md-block sidebar p-3">
      <h5 class="mb-4">Smart Retail Ops platform</h5>
      <ul class="nav flex-column">
        <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold">Threshold</a></li>
        <li class="nav-item"><a class="nav-link" href="/inventory-management">Inventory management</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold-list">Threshold List</a></li>
      </ul>
    </nav>
    <!-- Main -->
    <main class="col-md-10 ms-sm-auto px-4">
      <div class="d-flex justify-content-between align-items-center pt-3 pb-2 mb-3 border-bottom">
        <h2>Dashboard</h2>
        <div>
          <button class="btn btn-primary ms-2" data-bs-toggle="modal" data-bs-target="#reportModal">Generate Report</button>
        </div>
      </div>
      <!-- Report Modal -->
      <div class="modal fade" id="reportModal" tabindex="-1" aria-labelledby="reportModalLabel" aria-hidden="true">
        <div class="modal-dialog">
          <div class="modal-content">
            <form method="post" action="/export-report">
              <div class="modal-header">
                <h5 class="modal-title" id="reportModalLabel">Export Inventory Report</h5>
                <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
              </div>
              <div class="modal-body">
                <div class="mb-3">
                  <label class="form-label">Select format:</label><br>
                  <div class="form-check form-check-inline">
                    <input class="form-check-input" type="radio" name="format" id="csvOption" value="csv" checked>
                    <label class="form-check-label" for="csvOption">CSV</label>
                  </div>
                  <div class="form-check form-check-inline">
                    <input class="form-check-input" type="radio" name="format" id="pdfOption" value="pdf">
                    <label class="form-check-label" for="pdfOption">PDF</label>
                  </div>
                </div>
              </div>
              <div class="modal-footer">
                <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                <button type="submit" class="btn btn-primary">Download</button>
              </div>
            </form>
          </div>
        </div>
      </div>
      <!-- Category Cards -->
      <div class="row mb-4">
        <div class="col-md-4">
          <div class="p-4 category-card category-a">
            <h5>Category A</h5>
            <h2>{{ summary['A'] }}</h2>
          </div>
        </div>
        <div class="col-md-4">
          <div class="p-4 category-card category-b">
            <h5>Category B</h5>
            <h2>{{ summary['B'] }}</h2>
          </div>
        </div>
        <div class="col-md-4">
          <div class="p-4 category-card category-c">
            <h5>Category C</h5>
            <h2>{{ summary['C'] }}</h2>
          </div>
        </div>
      </div>
      <!-- Inventory Table -->
      <div class="card mb-4">
        <div class="card-body">
          <h5>Inventory Items</h5>
          <table class="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Quantity</th>
                <th>Unit Cost</th>
              </tr>
            </thead>
            <tbody>
              {% for item in inventory %}
              <tr>
                <td>{{ item['name'] }}</td>
                <td>{{ item['quantity'] }}</td>
                <td>${{ '%.2f'|format(item['unit_cost']) }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
      <!-- Inventory Trends Chart -->
      <div class="card mb-4">
        <div class="card-body">
          <h5>Inventory Trends</h5>
          <canvas id="inventoryChart" height="80"></canvas>
        </div>
      </div>
      <!-- Recent Inventory Updates -->
      <div class="card mb-4">
        <div class="card-body">
          <h5>Recent Inventory Updates</h5>
          <table class="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Stock</th>
              </tr>
            </thead>
            <tbody>
              {% for item in inventory[-5:] %}
              <tr>
                <td>{{ item['name'] }}</td>
                <td>{{ item['abc_class'] }}</td>
                <td>{{ item['quantity'] }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
<script>
  const labels = {{ chart_labels|tojson }};
  const dataA = {{ dataA|tojson }};
  const dataB = {{ dataB|tojson }};
  const dataC = {{ dataC|tojson }};
  const ctx = document.getElementById('inventoryChart').getContext('2d');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: 'Category A', data: dataA, borderColor: '#2563eb', fill: false },
        { label: 'Category B', data: dataB, borderColor: '#22c55e', fill: false },
        { label: 'Category C', data: dataC, borderColor: '#f59e42', fill: false }
      ]
    },
    options: { responsive: true, plugins: { legend: { position: 'top' } } }
  });

  document.querySelectorAll('form[action="/export-report"]').forEach(function(form) {
    form.addEventListener('submit', function(e) {
      e.preventDefault();
      var formData = new FormData(form);
      var format = formData.get('format');
      var url = '/export-report';
      var filename = format === 'pdf' ? 'inventory_report.pdf' : 'inventory_report.csv';
      fetch(url, {
        method: 'POST',
        body: formData
      })
      .then(response => response.blob())
      .then(blob => {
        var link = document.createElement('a');
        link.href = window.URL.createObjectURL(blob);
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        // Close the modal immediately after Download is clicked
        setTimeout(function() {
          var modal = bootstrap.Modal.getInstance(document.getElementById('reportModal'));
          if (modal) modal.hide();
        }, 100);
      });
    });
  });
</script>
</body>
</html>
'''

THRESHOLD_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Item Threshold</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8f9fa; }
    .sidebar { min-height: 100vh; background: #fff; border-right: 1px solid #eee; }
    .sidebar .nav-link.active { background: #e9ecef; font-weight: bold; }
    .form-select, .form-control { margin-bottom: 1.5rem; }
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <nav class="col-md-2 d-none d-md-block sidebar p-3">
      <h5 class="mb-4">App Log</h5>
      <ul class="nav flex-column">
        <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
        <li class="nav-item"><a class="nav-link active" href="/threshold">Threshold</a></li>
        <li class="nav-item"><a class="nav-link" href="/inventory-management">Inventory management</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold-list">Threshold List</a></li>
      </ul>
    </nav>
    <!-- Main -->
    <main class="col-md-10 ms-sm-auto px-4">
      <div class="pt-3 pb-2 mb-3 border-bottom">
        <h2>Item Threshold</h2>
      </div>
      <form method="post" class="mt-4" style="max-width: 600px;">
        <label class="form-label">Item Name</label>
        <select class="form-select" name="item_name" required>
          <option value="">Select Item</option>
          {% for item in inventory %}
            <option value="{{ item['name'] }}">{{ item['name'] }}</option>
          {% endfor %}
        </select>
        <label class="form-label">Minimum Threshold</label>
        <select class="form-select" name="min_threshold" required>
          <option value="">Select minimum</option>
          {% for i in range(0, 1001) %}
            <option value="{{ i }}">{{ i }}</option>
          {% endfor %}
        </select>
        <label class="form-label">Maximum Threshold</label>
        <select class="form-select" name="max_threshold" required>
          <option value="">Select maximum</option>
          {% for i in range(0, 1001) %}
            <option value="{{ i }}">{{ i }}</option>
          {% endfor %}
        </select>
        <button type="submit" class="btn btn-primary">Save</button>
      </form>
      {% if message %}
      <div class="alert alert-success mt-4">{{ message }}</div>
      {% endif %}
    </main>
  </div>
</div>
</body>
</html>
'''

INVENTORY_MANAGEMENT_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Inventory Management</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8f9fa; }
    .sidebar { min-height: 100vh; background: #fff; border-right: 1px solid #eee; }
    .sidebar .nav-link.active { background: #e9ecef; font-weight: bold; }
    .table thead th { background: #f3f4f6; }
    .form-inline input { margin-right: 1rem; }
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <nav class="col-md-2 d-none d-md-block sidebar p-3">
      <h5 class="mb-4">App Log</h5>
      <ul class="nav flex-column">
        <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold">Threshold</a></li>
        <li class="nav-item"><a class="nav-link active" href="/inventory-management">Inventory management</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold-list">Threshold List</a></li>
      </ul>
    </nav>
    <!-- Main -->
    <main class="col-md-10 ms-sm-auto px-4">
      <div class="d-flex justify-content-between align-items-center pt-3 pb-2 mb-3 border-bottom">
        <h2>Inventory Management</h2>
      </div>
      <form id="addItemForm" method="post" class="mb-4" style="max-width: 900px;">
        <div class="row g-2 align-items-center">
          <div class="col-md-4">
            <input type="text" class="form-control" name="item_name" placeholder="Item Name" required>
          </div>
          <div class="col-md-4">
            <input type="number" class="form-control" name="quantity" placeholder="Quantity" required>
          </div>
          <div class="col-md-4">
            <input type="number" step="0.01" class="form-control" name="unit_cost" placeholder="Unit Cost" required>
          </div>
          <div class="col-md-12 mt-2">
            <button type="submit" class="btn btn-primary">Add Item</button>
          </div>
        </div>
      </form>
      <div class="card">
        <div class="card-body">
          <table class="table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Quantity</th>
                <th>Unit Cost</th>
              </tr>
            </thead>
            <tbody>
              {% for item in inventory %}
              <tr>
                <td>{{ item['name'] }}</td>
                <td>{{ item['quantity'] }}</td>
                <td>${{ '%.2f'|format(item['unit_cost']) }}</td>
              </tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</div>
</body>
</html>
'''

THRESHOLD_LIST_TEMPLATE = '''
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Item Thresholds</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background: #f8f9fa; }
    .sidebar { min-height: 100vh; background: #fff; border-right: 1px solid #eee; }
    .sidebar .nav-link.active { background: #e9ecef; font-weight: bold; }
    .table thead th { background: #f3f4f6; }
  </style>
</head>
<body>
<div class="container-fluid">
  <div class="row">
    <!-- Sidebar -->
    <nav class="col-md-2 d-none d-md-block sidebar p-3">
      <h5 class="mb-4">App Log</h5>
      <ul class="nav flex-column">
        <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
        <li class="nav-item"><a class="nav-link" href="/threshold">Threshold</a></li>
        <li class="nav-item"><a class="nav-link" href="/inventory-management">Inventory management</a></li>
        <li class="nav-item"><a class="nav-link active" href="/threshold-list">Threshold List</a></li>
      </ul>
    </nav>
    <!-- Main -->
    <main class="col-md-10 ms-sm-auto px-4">
      <div class="pt-3 pb-2 mb-3 border-bottom">
        <h2>Item Thresholds</h2>
      </div>
      <div class="card">
        <div class="card-body">
          <table class="table">
            <thead>
              <tr>
                <th>Item Name</th>
                <th>Min Threshold</th>
                <th>Max Threshold</th>
              </tr>
            </thead>
            <tbody>
              {% for name, th in item_thresholds.items() %}
              <tr>
                <td>{{ name }}</td>
                <td>{{ th['min'] }}</td>
                <td>{{ th['max'] }}</td>
              </tr>
            {% else %}
              <tr><td colspan="3" class="text-center">No thresholds set yet.</td></tr>
              {% endfor %}
            </tbody>
          </table>
        </div>
      </div>
    </main>
  </div>
</div>
</body>
</html>
'''

@app.route('/')
def root():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    inventory = get_inventory()
    # Prepare trend data for each category (A, B, C)
    categories = {'A': [], 'B': [], 'C': []}
    labels = []
    for item in inventory:
        cat = item['abc_class']
        categories[cat].append(item['quantity'])
        labels.append(item['name'])
    # Pad missing categories with zeros for chart.js compatibility
    dataA = categories['A'] if categories['A'] else [0]
    dataB = categories['B'] if categories['B'] else [0]
    dataC = categories['C'] if categories['C'] else [0]
    # Use all item names as labels (if none, fallback to generic)
    chart_labels = labels if labels else ['No Data']
    return render_template_string(
        HTML_TEMPLATE,
        inventory=inventory,
        summary=get_summary(inventory),
        thresholds=get_thresholds(),
        chart_labels=chart_labels,
        dataA=dataA,
        dataB=dataB,
        dataC=dataC
    )

@app.route('/threshold', methods=['GET', 'POST'])
def threshold():
    message = None
    inventory = get_inventory()
    if request.method == 'POST':
        item_name = request.form['item_name']
        min_threshold = int(request.form['min_threshold'])
        max_threshold = int(request.form['max_threshold'])
        set_threshold(item_name, min_threshold, max_threshold)
        message = f"Thresholds for '{item_name}' saved: Min={min_threshold}, Max={max_threshold}"
    return render_template_string(THRESHOLD_TEMPLATE, inventory=inventory, message=message)

@app.route('/inventory-management', methods=['GET', 'POST'])
def inventory_management():
    if request.method == 'POST':
        name = request.form['item_name']
        quantity = int(request.form['quantity'])
        unit_cost = float(request.form['unit_cost'])
        item = classify_item(name, quantity, unit_cost)
        add_inventory_item(item['name'], item['quantity'], item['unit_cost'], item['abc_class'])
    inventory = get_inventory()
    return render_template_string(INVENTORY_MANAGEMENT_TEMPLATE, inventory=inventory)

@app.route('/threshold-list')
def threshold_list():
    item_thresholds = get_thresholds()
    return render_template_string(THRESHOLD_LIST_TEMPLATE, item_thresholds=item_thresholds)

@app.route('/export', methods=['POST'])
def export_csv():
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Item Name', 'Quantity', 'Unit Cost', 'Total Value', 'ABC Class'])
    for item in get_inventory():
        writer.writerow([item['name'], item['quantity'], item['unit_cost'], item['quantity'] * item['unit_cost'], item['abc_class']])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode()), mimetype='text/csv', as_attachment=True, download_name='inventory.csv')

@app.route('/export-report', methods=['POST'])
def export_report():
    format = request.form.get('format', 'csv')
    conn = sqlite3.connect('inventory.db')
    c = conn.cursor()
    # Fetch correct details: name, quantity, unit_cost, quantity (again as 4th col)
    c.execute('SELECT name, quantity, unit_cost FROM inventory')
    rows = c.fetchall()
    conn.close()
    headers = ['Item name', 'Quantity', 'Price', 'Quantity']
    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        for row in rows:
            # row[0]=name, row[1]=quantity, row[2]=unit_cost, row[1]=quantity again
            writer.writerow([row[0], row[1], row[2], row[1]])
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode()),
            mimetype='text/csv',
            as_attachment=True,
            download_name='inventory_report.csv'
        )
    elif format == 'pdf':
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
        output = io.BytesIO()
        data = [headers] + [[row[0], row[1], row[2], row[1]] for row in rows]
        doc = SimpleDocTemplate(output, pagesize=letter)
        table = Table(data, colWidths=[120, 80, 80, 80])
        style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 11),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ])
        table.setStyle(style)
        elements = [table]
        doc.build(elements)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='inventory_report.pdf'
        )
    else:
        return '', 400

def classify_item(name, quantity, unit_cost):
    total_value = quantity * unit_cost
    prompt = (
        "Classify the following item using ABC analysis. "
        "A items: High-value, low-quantity. B items: Moderate value/quantity. C items: Low-value, high-quantity. "
        f"Item: {name}, Quantity: {quantity}, Unit Cost: {unit_cost}, Total Value: {total_value}. "
        "Return only the class (A, B, or C) and a short reason."
    )
    result = llm.invoke(prompt).content
    # Extract class (A/B/C) from LLM output
    abc_class = 'C'
    for c in ['A', 'B', 'C']:
        if c in result:
            abc_class = c
            break
    return {
        'name': name,
        'quantity': quantity,
        'unit_cost': unit_cost,
        'total_value': total_value,
        'abc_class': abc_class
    }

def get_summary(inventory):
    summary = {'A': 0, 'B': 0, 'C': 0}
    for item in inventory:
        summary[item['abc_class']] += 1
    return summary

if __name__ == "__main__":
    app.run(debug=True)

