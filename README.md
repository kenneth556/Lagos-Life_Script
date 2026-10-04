# Lagos Life Account Runner

A local Python dashboard and Selenium automation scripts for Lagos Life account creation, CSV filtering, and reviewed transfers.

> **Use responsibly.** These scripts automate a third-party website and can create accounts or submit money transfers. Use them only with accounts you own or are authorized to operate, and check the website's rules before automating it. Transfers may be irreversible.

## Contents

| File | Purpose |
| --- | --- |
| `lagos_life_dashboard.py` | Local Flask web dashboard for account creation, CSV filtering, and transfer workflows. |
| `lagos_life_automation_multi.py` | Creates multiple accounts in Chrome, up to two concurrently and 40 per run. It does not transfer money. |
| `lagos_life_transfer.py` | Shared transfer preview and Selenium transfer implementation used by the dashboard. |
| `lagos_life_automation.py` | Standalone, single-account script. It creates an account and attempts a transfer to the recipient configured in the script. |
| `requirements.txt` | Python package requirements. |

## Requirements

- Windows 10 or later.
- Python 3.10 or newer is recommended.
- Google Chrome installed.
- Internet access to reach the Lagos Life website and install Python packages.

The browser automation uses Selenium and Chrome. Selenium Manager normally obtains the matching ChromeDriver when the browser starts. If that fails, update Chrome and Selenium, or troubleshoot the ChromeDriver installation.

## Installation (Windows PowerShell)

Open PowerShell in the project folder:

```powershell
cd "$HOME\Desktop\LL"
```

Create and activate a virtual environment:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation scripts, either allow activation for this PowerShell session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

or skip activation and use the environment's Python and pip directly:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If you activated the environment, install dependencies with:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Start the dashboard

From the project folder, with the virtual environment active:

```powershell
python .\lagos_life_dashboard.py
```

Or without activating the environment:

```powershell
.\.venv\Scripts\python.exe .\lagos_life_dashboard.py
```

Open **http://127.0.0.1:5000** in your browser. The dashboard binds to the loopback address, so it is intended to be available only on the same computer. Keep the PowerShell window open while using it. Press **Ctrl+C** in that window to stop the server.

The dashboard does not automatically create accounts or send transfers when it starts. Select a mode and explicitly start or confirm an operation in the UI.

## Dashboard modes

### Create accounts

- Choose between 1 and 40 accounts.
- Up to two browser sessions run concurrently.
- The runner selects the configured traits **Hustler** and **Tech Bro or Sis**, then continues through onboarding.
- The results distinguish fully onboarded accounts, failures, and accounts created but left partway through onboarding. Partial results include the last recorded onboarding stage.
- The account CSV uses the columns `name,username,password,balance`.
- No transfers are performed in this dashboard mode.

### Sort accounts

This mode filters a CSV and retains only records whose parsed balance is exactly **₦500,000**. It previews the kept and removed row counts before preparing the output. The output keeps all four columns: `name,username,password,balance`.

Quoted CSV fields may contain commas or line breaks. The CSV header must be exactly:

```csv
name,username,password,balance
```

### Transfer from CSV

Upload a CSV with the exact header and column order above, then enter the recipient username. The dashboard has four transfer choices:

| Choice | Eligible listed balance | Planned recipient transfer |
| --- | ---: | ---: |
| ₦1,096,000 balance | Exactly ₦1,096,000 | ₦1,000,000 |
| ₦500,000 balance | Exactly ₦500,000 | ₦475,000 |
| ₦96,000 balance | Exactly ₦96,000 | ₦91,000 |
| Custom total recipient amount | Accounts in any of the three tiers | Allocation toward a target from ₦100,000 to ₦10,000,000 |

For each fixed mode, only matching listed-balance rows are included. The custom mode uses only the ₦1,096,000, ₦500,000, and ₦96,000 tiers, prioritizing accounts in that order. It can assign a smaller final amount when needed to approach the target; allocations use ₦1,000 increments. There is no eligible-account row-count cap. The dashboard still limits each uploaded request to 256 KiB.

The custom target is the amount intended to reach the recipient; fees are additional. The custom preview displays the live balance and the fee shown by the website for each account and blocks an account if its current balance does not cover the transfer plus fee. After those live checks, the dashboard updates the planned amount and remainder based on accounts marked ready. If some accounts are blocked, the plan may fall short; it does not automatically replace them with other accounts.

Transfer steps:

1. Select a transfer mode and upload the CSV.
2. Enter the recipient and, for custom mode, the target amount.
3. Click **Preview transfer**. This opens the accounts to inspect the live balance and fee but does not press Send.
4. Review the recipient, amount, fee, balance, total, and status for every row.
5. Check the confirmation box and click **Confirm and send transfers** to submit only rows marked ready.

The fee is read from the transfer form at preview time. The confirmed run opens the form again, rechecks the live balance and fee, and will skip the transfer if the live balance no longer covers the transfer plus fee.

Up to two accounts are processed concurrently during preview and transfer. If a transfer has an uncertain result, the dashboard flags it and stops scheduling new accounts. Other transfers already in flight may still finish. **Do not retry an uncertain account until you have checked its transfer history and balance**, because a retry could duplicate a transfer.

## CSV handling and sensitive data

- The dashboard handles uploaded and generated CSV content in server memory; it does not intentionally save those dashboard CSVs to disk.
- The dashboard offers manual download and automatic download. In manual mode, click the download link yourself. A dashboard CSV is available for one download per run.
- Account CSV files contain passwords in plain text. Anyone who can access the file can use those credentials. Store downloads securely and delete them when no longer needed.
- Transfer credentials are retained in the running dashboard process while a transfer preview is pending and while transfers are being processed. They are not included in the transfer report.
- The account-creation CSV includes passwords so that the created accounts can be recovered. Protect it accordingly.
- Avoid uploading real credentials to a dashboard exposed beyond your own computer. Do not change the host binding to `0.0.0.0` without adding appropriate authentication and security controls.

## Standalone scripts

### Multiple-account creation

From the project folder, with dependencies installed:

```powershell
python .\lagos_life_automation_multi.py
```

This starts the default 40-account run. The script reports its success, failure, and incomplete-onboarding summary in the console. Its result CSV is built in memory by the script; use the dashboard if you need the dashboard's manual/automatic download controls.

### Single-account automation

```powershell
python .\lagos_life_automation.py
```

This is a separate, older-style flow that creates one account and attempts a transfer to the `RECIPIENT` value in the script. Review that value and the script before running it. Unlike the dashboard, this script writes its account CSV and error screenshot to the user's Desktop. Do not run it if you only want to create an account without a transfer.

This standalone script also prints the generated password and account details in its console output. Keep that console private.

## Troubleshooting

- **`py` is not recognized:** Install Python from python.org or the Microsoft Store, then reopen PowerShell.
- **Chrome does not start:** Confirm Chrome is installed and up to date. Reinstall the requirements in the active virtual environment.
- **ChromeDriver error:** Update Selenium and Chrome. Selenium Manager needs internet access to obtain a compatible driver.
- **Dashboard does not open:** Confirm the script is still running, then visit `http://127.0.0.1:5000`.
- **CSV header or row error:** Use the exact four-column header. Quote any field containing commas or line breaks, and provide a balance for every account row.
- **No transfer rows qualify:** Choose the tier matching the CSV balances, or use custom mode with rows in either supported tier.
- **A transfer is uncertain:** Check the account's transfer history and balance manually before deciding what to do. The automation intentionally does not retry it.

## Important limitations

- Website labels, page structure, fees, and workflows may change. Selenium selectors may then need updating.
- A transfer preview is a snapshot. The live balance and fee can change before confirmation; the transfer worker checks them again, but the website remains authoritative.
- A result marked submitted or uncertain is not proof that the recipient received the transfer. Verify it on the website.
- The dashboard is a local utility, not a secure credential vault or a financial system. Review every transfer before confirming.
