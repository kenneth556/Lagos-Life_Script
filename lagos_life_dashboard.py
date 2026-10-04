import csv
import io
import re
import secrets
import threading
import time
from datetime import datetime
from flask import Flask, jsonify, make_response, render_template_string, request

from lagos_life_automation_multi import (
    MAX_ACCOUNTS_PER_SESSION,
    NUM_ACCOUNTS,
    run_accounts,
)
from lagos_life_transfer import (
    MAX_TRANSFER_ACCOUNTS,
    MINIMUM_LISTED_BALANCE,
    TRANSFER_MODES,
    preview_transfers,
    run_transfers,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 256 * 1024
state_lock = threading.Lock()
stop_event = None
pending_operation = None
job_state = {
    "job_id": None,
    "mode": "create",
    "status": "idle",
    "requested": 0,
    "started": 0,
    "completed": 0,
    "failed": 0,
    "onboarding_incomplete": 0,
    "account_results": [],
    "active_accounts": [],
    "messages": [],
    "csv_content": None,
    "csv_filename": None,
    "csv_downloaded": False,
    "download_mode": "manual",
    "preview": [],
    "preview_id": None,
    "uncertain": 0,
    "error": None,
}

PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Lagos Life Account Runner</title>
  <style>
    body { font: 16px/1.5 system-ui, sans-serif; max-width: 620px; margin: 48px auto; padding: 0 18px; color: #17212b; background: #f5f7fa; }
    main { background: white; border: 1px solid #dce3ea; border-radius: 12px; padding: 24px; }
    h1 { font-size: 1.4rem; margin: 0 0 8px; }
    p { color: #536273; }
    label { display: block; font-weight: 600; margin: 18px 0 6px; }
    input { box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid #aab6c2; border-radius: 7px; font: inherit; }
    input[type="checkbox"] { width: auto; }
    button, .download { display: inline-block; margin: 16px 8px 0 0; padding: 10px 16px; border: 0; border-radius: 7px; background: #087e59; color: white; font: inherit; text-decoration: none; cursor: pointer; }
    button.secondary { background: #596979; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    #status { margin-top: 20px; font-weight: 600; }
    progress { width: 100%; height: 18px; }
    pre { max-height: 240px; overflow: auto; white-space: pre-wrap; background: #f2f4f6; border-radius: 7px; padding: 12px; font: 13px/1.5 ui-monospace, monospace; }
    table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: .9rem; }
    th, td { border: 1px solid #dce3ea; padding: 7px; text-align: left; }
    .warning { font-size: .88rem; }
  </style>
</head>
<body>
<main>
  <h1>Lagos Life Account Runner</h1>
  <div>
  <button id="createMode" type="button">Create accounts</button>
  <button id="filterMode" type="button" class="secondary">Sort accounts</button>
  <button id="transferMode" type="button" class="secondary">Transfer from CSV</button>
  </div>
  <section id="createPanel">
  <p>Creates accounts in Chrome, two at a time. No money transfers are performed.</p>
  <label for="count">Accounts to create (1–{{ maximum }})</label>
  <input id="count" type="number" min="1" max="{{ maximum }}" value="{{ default_count }}">
  </section>
  <section id="transferPanel" hidden>
  <p>Upload a CSV with exactly these columns, in this order: name,username,password,balance. Choose a balance mode; only matching listed balances are included. The script checks each live balance and the displayed fee before submission.</p>
  <label for="transferModeSelect">Balance and transfer amount</label>
  <select id="transferModeSelect">
    <option value="500k" selected>₦500,000 balance → send ₦475,000</option>
    <option value="96k">₦96,000 balance → send ₦91,000</option>
  </select>
  <label for="recipientUsername">Recipient username</label>
  <input id="recipientUsername" type="text" maxlength="40" autocomplete="off" placeholder="Enter recipient username">
  <label for="csvFile">Account CSV</label>
  <input id="csvFile" type="file" accept=".csv,text/csv">
  <button id="previewTransfer" type="button">Preview transfer</button>
  <label id="transferConfirmLabel" for="transferConfirm" hidden><input id="transferConfirm" type="checkbox"> I reviewed the rows, recipient, exact amount, displayed fees, and balances; submit the ready transfers. Transfers cannot be undone.</label>
  <div id="transferPreview"></div>
  <p class="warning">Transfers can incur fees and may not be reversible. Login details are kept in memory only for this run and are not included in its report.</p>
  </section>
  <section id="filterPanel" hidden>
  <p>Upload a CSV with exactly these columns, in this order: name,username,password,balance. Keeps only rows whose balance is exactly ₦500,000 and downloads the same four columns. Other rows are removed from the filtered output.</p>
  <label for="filterCsvFile">CSV to filter</label>
  <input id="filterCsvFile" type="file" accept=".csv,text/csv">
  <button id="previewFilter" type="button">Preview filter</button>
  <p id="filterPreview"></p>
  </section>
  <button id="start">Start</button>
  <button id="stop" class="secondary" disabled>Stop after active accounts</button>
  <label for="downloadMode">CSV handling</label>
  <select id="downloadMode">
    <option value="manual" selected>Manual — download only when I click</option>
    <option value="automatic">Automatic — download when the run finishes</option>
  </select>
  <div id="status">Status: idle</div>
  <progress id="progress" value="0" max="{{ default_count }}"></progress>
  <p id="summary"></p>
  <section id="creationResults" hidden>
    <h2>Account-creation results</h2>
    <div id="creationResultsTable"></div>
  </section>
  <a id="download" class="download" href="/download" hidden>Download CSV</a>
  <pre id="messages">Ready.</pre>
  <p class="warning">The CSV contains passwords in plain text. Keep it private. This dashboard listens only on this computer.</p>
</main>
<script>
const startButton = document.getElementById("start");
const stopButton = document.getElementById("stop");
const countInput = document.getElementById("count");
const createModeButton = document.getElementById("createMode");
const transferModeButton = document.getElementById("transferMode");
const filterModeButton = document.getElementById("filterMode");
const createPanel = document.getElementById("createPanel");
const transferPanel = document.getElementById("transferPanel");
const filterPanel = document.getElementById("filterPanel");
const csvFile = document.getElementById("csvFile");
const transferModeSelect = document.getElementById("transferModeSelect");
const filterCsvFile = document.getElementById("filterCsvFile");
const transferConfirm = document.getElementById("transferConfirm");
const transferConfirmLabel = document.getElementById("transferConfirmLabel");
const recipientUsername = document.getElementById("recipientUsername");
const previewTransferButton = document.getElementById("previewTransfer");
const previewFilterButton = document.getElementById("previewFilter");
const transferPreview = document.getElementById("transferPreview");
const filterPreview = document.getElementById("filterPreview");
const downloadMode = document.getElementById("downloadMode");
const statusText = document.getElementById("status");
const progress = document.getElementById("progress");
const summary = document.getElementById("summary");
const creationResults = document.getElementById("creationResults");
const creationResultsTable = document.getElementById("creationResultsTable");
const messages = document.getElementById("messages");
const download = document.getElementById("download");
let mode = "create";
let lastAutoDownloadedJob = null;
let currentPreviewId = null;

function setMode(selectedMode) {
  mode = selectedMode;
  createPanel.hidden = mode !== "create";
  transferPanel.hidden = mode !== "transfer";
  filterPanel.hidden = mode !== "filter";
  createModeButton.classList.toggle("secondary", mode !== "create");
  transferModeButton.classList.toggle("secondary", mode !== "transfer");
  filterModeButton.classList.toggle("secondary", mode !== "filter");
  download.textContent = mode === "transfer" ? "Download transfer report" : mode === "filter" ? "Download filtered CSV" : "Download CSV";
  previewTransferButton.hidden = mode !== "transfer";
  previewFilterButton.hidden = mode !== "filter";
  startButton.hidden = mode !== "create";
  startButton.disabled = false;
  transferConfirmLabel.hidden = true;
}

async function updateStatus() {
  const response = await fetch("/api/status");
  const data = await response.json();
  const busy = data.status === "running" || data.status === "stopping" || data.status === "previewing";
  const previewing = data.status === "previewing";
  startButton.disabled = busy || previewing;
  startButton.hidden = mode === "create"
    ? false
    : !(mode === data.mode && data.status === "preview_ready");
  if (mode === "transfer") {
    startButton.textContent = "Confirm and send transfers";
    transferConfirmLabel.hidden = !(data.mode === "transfer" && data.status === "preview_ready");
    startButton.disabled = data.status !== "preview_ready"
      || !(data.preview || []).some(row => row.status === "ready");
  } else if (mode === "filter") {
    startButton.textContent = "Filter & prepare CSV";
    startButton.disabled = data.status !== "preview_ready";
  } else {
    startButton.textContent = "Start account creation";
  }
  countInput.disabled = busy;
  csvFile.disabled = busy;
  recipientUsername.disabled = busy;
  transferModeSelect.disabled = busy;
  filterCsvFile.disabled = busy;
  transferConfirm.disabled = busy;
  previewTransferButton.disabled = busy || previewing;
  previewFilterButton.disabled = busy || previewing;
  downloadMode.disabled = busy;
  createModeButton.disabled = busy;
  transferModeButton.disabled = busy;
  filterModeButton.disabled = busy;
  stopButton.disabled = data.status !== "running";
  statusText.textContent = "Status: " + data.status;
  progress.max = data.requested || Number(countInput.value) || {{ default_count }};
  progress.value = data.completed + data.failed + (data.uncertain || 0)
    + (data.onboarding_incomplete || 0);
  creationResults.hidden = data.mode !== "create" || !(data.account_results || []).length;
  if (data.mode === "create") {
    summary.textContent = `${data.completed} succeeded, ${data.failed} failed, `
      + `${data.onboarding_incomplete || 0} onboarding incomplete; `
      + `${data.active_accounts.length} active`;
    renderCreationResults(data.account_results || []);
  } else {
    summary.textContent = `${data.completed} finished, ${data.failed} failed; `
      + `${data.active_accounts.length} active`;
  }
  if (data.uncertain) {
    summary.textContent += `; ${data.uncertain} uncertain — do not retry without checking`;
  }
  messages.textContent = data.messages.length ? data.messages.join("\\n") : "Ready.";
  messages.scrollTop = messages.scrollHeight;
  download.hidden = !data.has_csv;
  download.textContent = data.mode === "transfer" ? "Download transfer report" : data.mode === "filter" ? "Download filtered CSV" : "Download CSV";
  renderTransferPreview(data.preview || []);
  currentPreviewId = data.preview_id || null;
  if (data.mode === "filter" && data.preview?.length) {
    filterPreview.textContent = data.preview[0].message;
  }
  if (
    (data.status === "completed" || data.status === "stopped")
    && data.download_mode === "automatic"
    && data.has_csv
    && data.job_id !== lastAutoDownloadedJob
  ) {
    lastAutoDownloadedJob = data.job_id;
    window.location.assign("/download");
  }
}

function renderTransferPreview(rows) {
  transferPreview.replaceChildren();
  if (!rows.length) return;
  const table = document.createElement("table");
  const header = document.createElement("tr");
  for (const title of ["Account", "Recipient", "Amount", "Fee", "Balance", "Total", "Status"]) {
    const cell = document.createElement("th");
    cell.textContent = title;
    header.appendChild(cell);
  }
  table.appendChild(header);
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const value of [
      row.username, row.recipient, row.amount, row.fee || "Unknown",
      row.balance || "Unknown", row.total || "Unknown", row.status
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.appendChild(cell);
    }
    table.appendChild(tr);
  }
  transferPreview.appendChild(table);
}

function renderCreationResults(rows) {
  creationResultsTable.replaceChildren();
  if (!rows.length) return;
  const table = document.createElement("table");
  const header = document.createElement("tr");
  for (const title of ["#", "Name", "Username", "Result", "Last stage / details"]) {
    const cell = document.createElement("th");
    cell.textContent = title;
    header.appendChild(cell);
  }
  table.appendChild(header);
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const value of [
      row.account_number, row.name || "Unknown", row.username || "Unknown",
      row.status, [row.stage, row.message].filter(Boolean).join(": ")
    ]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      tr.appendChild(cell);
    }
    table.appendChild(tr);
  }
  creationResultsTable.appendChild(table);
}

startButton.addEventListener("click", async () => {
  let response;
  if (mode === "create") {
    const count = Number(countInput.value);
    response = await fetch("/api/start", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-LagosLife-Local": "1"},
      body: JSON.stringify({count, download_mode: downloadMode.value})
    });
  } else if (mode === "transfer") {
    if (!transferConfirm.checked) {
      statusText.textContent = "Confirm the transfer action before starting.";
      return;
    }
    if (!currentPreviewId) {
      statusText.textContent = "Preview the accounts and fees first.";
      return;
    }
    response = await fetch("/api/confirm-transfer", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-LagosLife-Local": "1"},
      body: JSON.stringify({preview_id: currentPreviewId, confirmed: true})
    });
  } else if (mode === "filter") {
    if (!currentPreviewId) {
      statusText.textContent = "Preview the CSV rows first.";
      return;
    }
    response = await fetch("/api/confirm-filter", {
      method: "POST",
      headers: {"Content-Type": "application/json", "X-LagosLife-Local": "1"},
      body: JSON.stringify({preview_id: currentPreviewId})
    });
  }
  if (!response.ok) {
    const error = await response.json();
    await updateStatus();
    statusText.textContent = "Could not start: " + error.error;
    return;
  }
  await updateStatus();
});

previewTransferButton.addEventListener("click", async () => {
  transferConfirm.checked = false;
  transferPreview.replaceChildren();
  const file = csvFile.files[0];
  if (!file || !recipientUsername.value.trim()) {
    statusText.textContent = "Choose a CSV and enter a recipient before previewing.";
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  formData.append("recipient", recipientUsername.value.trim());
  formData.append("balance_mode", transferModeSelect.value);
  formData.append("download_mode", downloadMode.value);
  const response = await fetch("/api/preview-transfer", {
    method: "POST",
    headers: {"X-LagosLife-Local": "1"},
    body: formData
  });
  if (!response.ok) {
    const error = await response.json();
    statusText.textContent = "Preview failed: " + error.error;
  }
  await updateStatus();
});

previewFilterButton.addEventListener("click", async () => {
  filterPreview.textContent = "";
  currentPreviewId = null;
  if (!filterCsvFile.files.length) {
    statusText.textContent = "Choose a CSV file to preview.";
    return;
  }
  const formData = new FormData();
  formData.append("file", filterCsvFile.files[0]);
  formData.append("download_mode", downloadMode.value);
  const response = await fetch("/api/preview-filter", {
    method: "POST",
    headers: {"X-LagosLife-Local": "1"},
    body: formData
  });
  if (!response.ok) {
    const error = await response.json();
    filterPreview.textContent = "Preview failed: " + error.error;
  }
  await updateStatus();
});

stopButton.addEventListener("click", async () => {
  await fetch("/api/stop", {
    method: "POST",
    headers: {"X-LagosLife-Local": "1"}
  });
  await updateStatus();
});

createModeButton.addEventListener("click", () => setMode("create"));
transferModeButton.addEventListener("click", () => setMode("transfer"));
filterModeButton.addEventListener("click", () => setMode("filter"));
setMode("create");
updateStatus();
setInterval(updateStatus, 1000);
</script>
</body>
</html>
"""


@app.before_request
def restrict_to_local_computer():
    host = request.host.split(":", 1)[0].lower()
    if request.remote_addr not in ("127.0.0.1", "::1") or host not in ("127.0.0.1", "localhost"):
        return jsonify(error="This dashboard is only available on this computer."), 403
    if request.method == "POST" and request.headers.get("X-LagosLife-Local") != "1":
        return jsonify(error="Missing local request header."), 403
    return None


@app.get("/")
def index():
    return render_template_string(
        PAGE,
        maximum=MAX_ACCOUNTS_PER_SESSION,
        default_count=NUM_ACCOUNTS,
        minimum_balance=f"{MINIMUM_LISTED_BALANCE:,}",
    )


@app.get("/api/status")
def status():
    with state_lock:
        snapshot = {
            key: value.copy() if isinstance(value, list) else value
            for key, value in job_state.items()
            if key not in ("csv_content", "csv_filename")
        }
        snapshot["has_csv"] = bool(job_state["csv_content"])
    return jsonify(snapshot)


@app.post("/api/start")
def start():
    global pending_operation, stop_event
    payload = request.get_json(silent=True) or {}
    count = payload.get("count")
    if isinstance(count, bool) or not isinstance(count, int):
        return jsonify(error="Account count must be a whole number."), 400
    if not 1 <= count <= MAX_ACCOUNTS_PER_SESSION:
        return jsonify(error=f"Choose between 1 and {MAX_ACCOUNTS_PER_SESSION} accounts."), 400
    download_mode = payload.get("download_mode", "manual")
    if download_mode not in ("manual", "automatic"):
        return jsonify(error="Download mode must be manual or automatic."), 400

    with state_lock:
        if job_state["status"] in ("running", "stopping", "previewing"):
            return jsonify(error="A run is already active."), 409

        pending_operation = None
        job_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        stop_event = threading.Event()
        job_state.update({
            "job_id": job_id,
            "mode": "create",
            "status": "running",
            "requested": count,
            "started": 0,
            "completed": 0,
            "failed": 0,
            "onboarding_incomplete": 0,
            "account_results": [],
            "uncertain": 0,
            "active_accounts": [],
            "preview": [],
            "preview_id": None,
            "messages": [f"Starting a run for {count} accounts."],
            "csv_content": None,
            "csv_filename": None,
            "csv_downloaded": False,
            "download_mode": download_mode,
            "error": None,
        })
        worker = threading.Thread(
            target=run_job,
            args=(job_id, "create", count, None, stop_event),
            daemon=True,
        )
        worker.start()

    return jsonify(status="running", job_id=job_id), 202


def parse_uploaded_accounts_csv(file_storage):
    raw = file_storage.stream.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("CSV must be UTF-8 encoded.") from error

    reader = csv.DictReader(io.StringIO(text))
    expected_headers = ["name", "username", "password", "balance"]
    if reader.fieldnames != expected_headers:
        raise ValueError(
            "CSV header must be exactly: name,username,password,balance"
        )
    accounts = []
    for row_number, row in enumerate(reader, start=2):
        account = {
            key: (row.get(key) or "").strip()
            for key in expected_headers
        }
        if not any(account.values()):
            continue
        if None in row:
            raise ValueError(f"CSV row {row_number} has extra comma-separated values.")
        if not all(account[key] for key in expected_headers):
            raise ValueError(f"CSV row {row_number} has a missing value.")
        try:
            account["parsed_balance"] = parse_balance_value(account["balance"])
        except ValueError as error:
            raise ValueError(f"CSV row {row_number}: {error}") from error

        accounts.append(account)

    if not accounts:
        raise ValueError("CSV contains no account rows.")
    return accounts


def parse_account_csv(file_storage, listed_balance=MINIMUM_LISTED_BALANCE):
    accounts = parse_uploaded_accounts_csv(file_storage)
    usernames = set()
    eligible_accounts = []
    for row_number, account in enumerate(accounts, start=2):
        if account["username"] in usernames:
            raise ValueError(
                f"CSV row {row_number} repeats username {account['username']!r}."
            )
        usernames.add(account["username"])
        if account["parsed_balance"] != listed_balance:
            continue
        eligible_accounts.append(account)
    if len(eligible_accounts) > MAX_TRANSFER_ACCOUNTS:
        raise ValueError(
            f"At most {MAX_TRANSFER_ACCOUNTS} rows may qualify for transfer."
        )
    return [
        {key: account[key] for key in ("name", "username", "password", "balance")}
        for account in eligible_accounts
    ], len(accounts) - len(eligible_accounts)


def parse_balance_value(value):
    match = re.search(r"([\d,]+(?:\.\d{1,2})?)", value)
    if not match:
        raise ValueError(f"Invalid balance value {value!r}.")
    return float(match.group(1).replace(",", ""))


@app.post("/api/preview-filter")
def preview_filter():
    global pending_operation
    with state_lock:
        if job_state["status"] in ("running", "stopping", "previewing"):
            return jsonify(error="Another operation is already active."), 409
        pending_operation = None
        job_state.update({
            "mode": "filter",
            "status": "idle",
            "preview": [],
            "preview_id": None,
            "messages": ["Checking the selected CSV."],
        })

    uploaded_file = request.files.get("file")
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify(error="Choose a CSV file to preview."), 400
    download_mode = request.form.get("download_mode", "manual")
    if download_mode not in ("manual", "automatic"):
        return jsonify(error="Download mode must be manual or automatic."), 400
    try:
        rows = parse_uploaded_accounts_csv(uploaded_file)
    except ValueError as error:
        return jsonify(error=str(error)), 400

    kept_rows = [
        {key: row[key] for key in ("name", "username", "password", "balance")}
        for row in rows
        if row["parsed_balance"] == MINIMUM_LISTED_BALANCE
    ]
    csv_buffer = io.StringIO(newline="")
    fieldnames = ["name", "username", "password", "balance"]
    writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(kept_rows)
    csv_content = "\ufeff" + csv_buffer.getvalue()
    preview_id = secrets.token_urlsafe(24)
    with state_lock:
        pending_operation = {
            "kind": "filter",
            "preview_id": preview_id,
            "expires_at": time.monotonic() + 900,
            "csv_content": csv_content,
            "kept_count": len(kept_rows),
            "row_count": len(rows),
            "download_mode": download_mode,
        }
        job_state.update({
            "job_id": secrets.token_urlsafe(12),
            "mode": "filter",
            "status": "preview_ready",
            "requested": len(rows),
            "started": 0,
            "completed": 0,
            "failed": 0,
            "uncertain": 0,
            "active_accounts": [],
            "preview_id": preview_id,
            "preview": [{
                "message": (
                    f"{len(kept_rows)} row(s) will be kept and "
                    f"{len(rows) - len(kept_rows)} removed."
                )
            }],
            "messages": ["Review the counts, then select Filter & prepare CSV."],
            "csv_content": None,
            "csv_filename": None,
            "csv_downloaded": False,
            "download_mode": download_mode,
            "error": None,
        })
    return jsonify(status="preview_ready", preview_id=preview_id), 200


@app.post("/api/confirm-filter")
def confirm_filter():
    global pending_operation
    payload = request.get_json(silent=True) or {}
    with state_lock:
        pending = pending_operation
        if (
            not pending or pending["kind"] != "filter"
            or pending["preview_id"] != payload.get("preview_id")
        ):
            return jsonify(error="Filter preview expired; preview the file again."), 409
        if time.monotonic() > pending["expires_at"]:
            pending_operation = None
            return jsonify(error="Filter preview expired; preview the file again."), 409
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        job_state.update({
            "status": "completed",
            "completed": pending["row_count"],
            "csv_content": pending["csv_content"],
            "csv_filename": f"lagos_life_filtered_accounts_{timestamp}.csv",
            "csv_downloaded": False,
            "messages": [
                f"Kept {pending['kept_count']} row(s) with exactly ₦{MINIMUM_LISTED_BALANCE:,}.",
                f"Removed {pending['row_count'] - pending['kept_count']} row(s).",
                "Filtered CSV is ready in memory for download.",
            ],
        })
        pending_operation = None
    return jsonify(status="completed"), 200


@app.post("/api/preview-transfer")
def preview_transfer():
    global pending_operation
    uploaded_file = request.files.get("file")
    recipient = request.form.get("recipient", "").strip().lstrip("@")
    balance_mode = request.form.get("balance_mode", "500k")
    if balance_mode not in TRANSFER_MODES:
        return jsonify(error="Choose a supported balance and transfer mode."), 400
    mode_config = TRANSFER_MODES[balance_mode]
    listed_balance = mode_config["listed_balance"]
    transfer_amount = mode_config["transfer_amount"]
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify(error="Choose a CSV file first."), 400
    if not recipient or not re.fullmatch(r"[A-Za-z0-9_.-]+", recipient):
        return jsonify(error="Enter a valid recipient username."), 400
    try:
        accounts, excluded_count = parse_account_csv(uploaded_file, listed_balance)
    except ValueError as error:
        return jsonify(error=str(error)), 400
    if not accounts:
        return jsonify(
            error=f"No CSV accounts have the exact ₦{listed_balance:,} listed balance."
        ), 400
    download_mode = request.form.get("download_mode", "manual")
    if download_mode not in ("manual", "automatic"):
        return jsonify(error="Download mode must be manual or automatic."), 400

    preview_id = secrets.token_urlsafe(24)
    job_id = secrets.token_urlsafe(12)
    with state_lock:
        if job_state["status"] in ("running", "stopping", "previewing"):
            return jsonify(error="Another operation is already active."), 409
        pending_operation = {
            "kind": "transfer",
            "preview_id": preview_id,
            "expires_at": time.monotonic() + 900,
            "accounts": accounts,
            "recipient": recipient,
            "balance_mode": balance_mode,
            "listed_balance": listed_balance,
            "transfer_amount": transfer_amount,
            "download_mode": download_mode,
            "excluded_count": excluded_count,
        }
        job_state.update({
            "job_id": job_id,
            "mode": "transfer",
            "status": "previewing",
            "requested": len(accounts),
            "started": 0,
            "completed": 0,
            "failed": 0,
            "uncertain": 0,
            "active_accounts": [],
            "preview": [],
            "preview_id": preview_id,
            "messages": [
                f"Checking {len(accounts)} eligible account(s) two at a time.",
                f"Skipped {excluded_count} row(s) that do not have exactly ₦{listed_balance:,} listed balance.",
                "No transfers are being submitted during preview.",
            ],
            "csv_content": None,
            "csv_filename": None,
            "csv_downloaded": False,
            "download_mode": download_mode,
            "error": None,
        })
        worker = threading.Thread(
            target=run_transfer_preview,
            args=(job_id, preview_id, accounts, recipient, transfer_amount),
            daemon=True,
        )
        worker.start()
    return jsonify(status="previewing", preview_id=preview_id), 202


def run_transfer_preview(job_id, preview_id, accounts, recipient, transfer_amount):
    global pending_operation

    def record_event(event):
        with state_lock:
            if job_state["job_id"] != job_id:
                return
            number = event["account_number"]
            if event["type"] == "account_started":
                job_state["started"] += 1
                job_state["active_accounts"].append(number)
                job_state["messages"].append(
                    f"Previewing account {event.get('username', '')}."
                )
            else:
                job_state["completed"] += 1
                if number in job_state["active_accounts"]:
                    job_state["active_accounts"].remove(number)
                job_state["preview"].append({
                    "account_number": number,
                    "username": event.get("username", ""),
                    "recipient": recipient,
                    "amount": f"₦{transfer_amount:,}",
                    "fee": event.get("fee", "Unknown"),
                    "balance": event.get("balance", "Unknown"),
                    "total": event.get("total", "Unknown"),
                    "status": event.get("status", "blocked"),
                    "message": event.get("message", ""),
                })
                job_state["preview"].sort(key=lambda row: row["account_number"])
                job_state["messages"].append(
                    f"{event.get('username', '')}: {event.get('status', 'blocked')} — "
                    f"{event.get('message', '')}"
                )
            job_state["messages"] = job_state["messages"][-100:]

    try:
        previews = preview_transfers(
            accounts,
            recipient,
            progress_callback=record_event,
            transfer_amount=transfer_amount,
        )
    except Exception as error:
        with state_lock:
            if job_state["job_id"] == job_id:
                job_state["status"] = "error"
                job_state["error"] = f"{type(error).__name__}: {error}"
                job_state["messages"].append(f"Transfer preview failed: {job_state['error']}")
                pending_operation = None
        return

    with state_lock:
        if job_state["job_id"] != job_id or not pending_operation:
            return
        pending_operation["previews"] = previews
        pending_operation["preview_id"] = preview_id
        job_state["active_accounts"] = []
        job_state["status"] = "preview_ready"
        ready_count = sum(row["status"] == "ready" for row in previews)
        job_state["messages"].append(
            f"Preview complete: {ready_count} ready, "
            f"{len(previews) - ready_count} blocked. Review each fee before confirming."
        )


@app.post("/api/confirm-transfer")
def confirm_transfer():
    global pending_operation, stop_event
    payload = request.get_json(silent=True) or {}
    if payload.get("confirmed") is not True:
        return jsonify(error="Final transfer confirmation is required."), 400

    with state_lock:
        pending = pending_operation
        if (
            not pending or pending["kind"] != "transfer"
            or pending["preview_id"] != payload.get("preview_id")
            or job_state["status"] != "preview_ready"
        ):
            return jsonify(error="Transfer preview expired; preview the CSV again."), 409
        if time.monotonic() > pending["expires_at"]:
            pending_operation = None
            return jsonify(error="Transfer preview expired; preview the CSV again."), 409

        ready_usernames = {
            row["username"] for row in pending["previews"]
            if row["status"] == "ready"
        }
        accounts = [
            account for account in pending["accounts"]
            if account["username"] in ready_usernames
        ]
        if not accounts:
            return jsonify(error="No accounts passed the live fee and balance checks."), 400

        recipient = pending["recipient"]
        transfer_amount = pending["transfer_amount"]
        download_mode = pending["download_mode"]
        pending_operation = None
        stop_event = threading.Event()
        job_state.update({
            "status": "running",
            "requested": len(accounts),
            "started": 0,
            "completed": 0,
            "failed": 0,
            "uncertain": 0,
            "active_accounts": [],
            "messages": [
                f"Submitting transfers for {len(accounts)} preview-approved account(s).",
                "Uncertain transfers are not retried automatically.",
            ],
            "csv_content": None,
            "csv_filename": None,
            "csv_downloaded": False,
            "download_mode": download_mode,
        })
        worker = threading.Thread(
            target=run_job,
            args=(
                job_state["job_id"],
                "transfer",
                len(accounts),
                accounts,
                stop_event,
                recipient,
                transfer_amount,
            ),
            daemon=True,
        )
        worker.start()
    return jsonify(status="running"), 202


@app.post("/api/stop")
def stop():
    with state_lock:
        if job_state["status"] != "running" or stop_event is None:
            return jsonify(error="There is no active run to stop."), 409
        job_state["status"] = "stopping"
        job_state["messages"].append(
            "Stop requested. Current browser tasks will finish before no new accounts are started."
        )
        stop_event.set()
    return jsonify(status="stopping"), 202


@app.get("/download")
def download_csv():
    with state_lock:
        content = job_state["csv_content"]
        filename = job_state["csv_filename"]
        if not content or not filename:
            if job_state["csv_downloaded"]:
                return jsonify(error="This run's CSV has already been downloaded."), 410
            return jsonify(error="The CSV is not ready yet."), 404
        job_state["csv_content"] = None
        job_state["csv_filename"] = None
        job_state["csv_downloaded"] = True

    response = make_response(content.encode("utf-8"))
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    response.headers["Cache-Control"] = "no-store"
    return response


def run_job(
    job_id,
    mode,
    count,
    accounts,
    job_stop_event,
    recipient=None,
    transfer_amount=TRANSFER_MODES["500k"]["transfer_amount"],
):
    def record_event(event):
        with state_lock:
            if job_state["job_id"] != job_id:
                return
            account_number = event.get("account_number")
            event_type = event["type"]
            if event_type == "account_started":
                job_state["started"] += 1
                job_state["active_accounts"].append(account_number)
                message = f"Account {account_number}: started."
            elif event_type == "account_completed":
                result_status = event.get("status")
                if mode == "create" and result_status == "onboarding_incomplete":
                    job_state["onboarding_incomplete"] += 1
                    job_state["account_results"].append({
                        "account_number": account_number,
                        "name": event.get("name", ""),
                        "username": event.get("username", ""),
                        "status": result_status,
                        "stage": event.get("stage", ""),
                        "message": event.get("message", ""),
                    })
                elif result_status == "uncertain":
                    job_state["uncertain"] += 1
                elif result_status == "failed":
                    job_state["failed"] += 1
                else:
                    job_state["completed"] += 1
                    if mode == "create":
                        job_state["account_results"].append({
                            "account_number": account_number,
                            "name": event.get("name", ""),
                            "username": event.get("username", ""),
                            "status": result_status or "success",
                            "stage": event.get("stage", ""),
                            "message": event.get("message", ""),
                        })
                if account_number in job_state["active_accounts"]:
                    job_state["active_accounts"].remove(account_number)
                username = event.get("username", "")
                detail = result_status or "created"
                message = f"Account {account_number} {username}: {detail}."
                if event.get("message"):
                    message += f" {event['message']}"
                if mode == "transfer":
                    for preview_row in job_state["preview"]:
                        if preview_row.get("username") == username:
                            preview_row["status"] = detail
                            preview_row["message"] = event.get("message", "")
                            break
            else:
                job_state["failed"] += 1
                if account_number in job_state["active_accounts"]:
                    job_state["active_accounts"].remove(account_number)
                message = f"Account {account_number}: failed — {event.get('message', 'Unknown error')}"
                if mode == "create":
                    job_state["account_results"].append({
                        "account_number": account_number,
                        "name": event.get("name", ""),
                        "username": event.get("username", ""),
                        "status": "failed",
                        "stage": event.get("stage", ""),
                        "message": event.get("message", "Unknown error"),
                    })
                if mode == "transfer":
                    username = event.get("username")
                    for preview_row in job_state["preview"]:
                        if preview_row.get("username") == username:
                            preview_row["status"] = "failed"
                            preview_row["message"] = event.get("message", "")
                            break
            job_state["messages"].append(message)
            job_state["messages"] = job_state["messages"][-100:]

    try:
        if mode == "create":
            result = run_accounts(
                num_accounts=count,
                progress_callback=record_event,
                stop_event=job_stop_event,
            )
        else:
            result = run_transfers(
                accounts=accounts or [],
                recipient=recipient or "",
                progress_callback=record_event,
                stop_event=job_stop_event,
                transfer_amount=transfer_amount,
            )
    except Exception as error:
        with state_lock:
            if job_state["job_id"] == job_id:
                job_state["status"] = "error"
                job_state["error"] = f"{type(error).__name__}: {error}"
                job_state["messages"].append(f"Run failed: {job_state['error']}")
        return

    with state_lock:
        if job_state["job_id"] == job_id:
            job_state["status"] = "stopped" if result["stopped"] else "completed"
            job_state["active_accounts"] = []
            job_state["csv_content"] = result["csv_content"]
            job_state["csv_filename"] = result["csv_filename"]
            if result["csv_content"]:
                job_state["messages"].append("CSV is ready in memory for download.")
            else:
                job_state["messages"].append("No CSV was generated for this run.")
            if mode == "create":
                job_state["messages"].append(
                    f"Account summary: {result['successful']} succeeded, "
                    f"{result['failed']} failed, "
                    f"{len(result['onboarding_incomplete'])} onboarding incomplete."
                )


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)
