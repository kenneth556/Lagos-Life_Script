import csv
import io
import re
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SITE_URL = "https://lagoslife.eliysites.com/"
TRANSFER_AMOUNT = 475_000
MINIMUM_LISTED_BALANCE = 500_000
TRANSFER_MODES = {
    "500k": {"listed_balance": 500_000, "transfer_amount": 475_000},
    "96k": {"listed_balance": 96_000, "transfer_amount": 91_000},
}
MAX_TRANSFER_ACCOUNTS = 20
MAX_CONCURRENT_TRANSFERS = 2


def parse_naira(value):
    match = re.search(r"([\d,]+(?:\.\d{1,2})?)", value)
    if not match:
        raise ValueError(f"Could not read a Naira amount from {value!r}.")
    return float(match.group(1).replace(",", ""))


def _visible_fee(button_text):
    match = re.search(
        r"\bfee\s*₦\s*([\d,]+(?:\.\d{1,2})?)",
        button_text,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("The transfer fee was not visible; transfer blocked.")
    return float(match.group(1).replace(",", ""))


def _open_transfer_form(account, recipient, transfer_amount=TRANSFER_AMOUNT):
    options = Options()
    options.add_argument("--start-maximized")
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 20)

    try:
        driver.get(SITE_URL)
        try:
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable((
                By.XPATH, "//button[normalize-space(.)='Essential only']",
            ))).click()
        except TimeoutException:
            pass

        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[normalize-space(.)='Log in']",
        ))).click()

        username_input = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[@placeholder='tolu_eko' or @type='email' "
            "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'username') "
            "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'email')]",
        )))
        username_input.send_keys(account["username"])
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@type='password']",
        ))).send_keys(account["password"])
        wait.until(EC.element_to_be_clickable((
            By.XPATH, "(//button[normalize-space(.)='Log in'])[last()]",
        ))).click()

        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((
                By.XPATH, "//button[normalize-space(.)='Later']",
            ))).click()
        except TimeoutException:
            pass

        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[normalize-space(.)='Continue']",
        ))).click()

        phone_xpath = (
            "//*[self::button or self::a][contains(normalize-space(.), 'Phone') "
            "or @id='phone' or contains(@class, 'phone') "
            "or contains(@aria-label, 'hone')]"
        )
        wait.until(EC.element_to_be_clickable((By.XPATH, phone_xpath))).click()
        wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//*[contains(normalize-space(.), 'Messages') "
            "and not(*[contains(normalize-space(.), 'Messages')])]",
        ))).click()

        search_box = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[@type='search' or contains(translate(@placeholder, "
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'search') "
            "or contains(@placeholder, '@username') "
            "or contains(@placeholder, 'Message someone')]",
        )))
        search_box.send_keys(recipient)
        recipient_xpath = (
            "//*[translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            f"'abcdefghijklmnopqrstuvwxyz')='{recipient.casefold()}' or "
            "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            f"'abcdefghijklmnopqrstuvwxyz')='@{recipient.casefold()}']"
        )
        wait.until(EC.element_to_be_clickable((
            By.XPATH, recipient_xpath,
        ))).click()
        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[contains(normalize-space(.), 'Send money')]",
        ))).click()

        balance_element = wait.until(EC.visibility_of_element_located((
            By.XPATH, "//*[contains(text(), '₦')]",
        )))
        current_balance = parse_naira(balance_element.text)
        amount_input = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//input[@type='number' or @inputmode='numeric' "
            "or contains(translate(@placeholder, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
            "'abcdefghijklmnopqrstuvwxyz'), 'amount')]",
        )))
        amount_input.clear()
        amount_input.send_keys(Keys.CONTROL, "a")
        amount_input.send_keys(Keys.BACKSPACE)
        amount_input.send_keys(str(transfer_amount))
        entered_amount = amount_input.get_attribute("value") or ""
        if parse_naira(entered_amount) != transfer_amount:
            raise ValueError(
                f"Amount field did not contain exactly ₦{transfer_amount:,}."
            )

        send_button_xpath = (
            "//button[contains(normalize-space(.), 'Send') "
            f"and contains(normalize-space(.), '{transfer_amount:,}')]"
        )
        send_button = wait.until(EC.presence_of_element_located((
            By.XPATH, send_button_xpath,
        )))
        fee = _visible_fee(send_button.text)
        return driver, wait, current_balance, fee, send_button
    except Exception:
        driver.quit()
        raise


def preview_transfer_from_account(account, recipient, transfer_amount=TRANSFER_AMOUNT):
    preview = {
        "name": account["name"],
        "username": account["username"],
        "amount": f"₦{transfer_amount:,}",
        "fee": None,
        "balance": None,
        "total": None,
        "status": "blocked",
        "message": "",
    }
    driver = None
    try:
        driver, _, balance, fee, _ = _open_transfer_form(
            account, recipient, transfer_amount
        )
        total = transfer_amount + fee
        preview.update({
            "fee": f"₦{fee:,.2f}".rstrip("0").rstrip("."),
            "balance": f"₦{balance:,.2f}".rstrip("0").rstrip("."),
            "total": f"₦{total:,.2f}".rstrip("0").rstrip("."),
        })
        if balance < total:
            preview["message"] = "Insufficient live balance for transfer plus fee."
        else:
            preview["status"] = "ready"
            preview["message"] = "Fee and live balance checked; awaiting confirmation."
    except (TimeoutException, WebDriverException, ValueError) as error:
        preview["message"] = f"{type(error).__name__}: {error}"
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException as error:
                preview["message"] = (
                    f"{preview['message']} Browser cleanup: {error}".strip()
                )
                preview["status"] = "blocked"
    return preview


def preview_transfers(
    accounts, recipient, progress_callback=None, transfer_amount=TRANSFER_AMOUNT
):
    recipient = recipient.strip().lstrip("@")
    if not recipient or not re.fullmatch(r"[A-Za-z0-9_.-]+", recipient):
        raise ValueError("Recipient must contain only letters, numbers, _, . or -.")
    previews = {}
    futures = {}
    next_index = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TRANSFERS) as executor:
        while next_index < len(accounts) and len(futures) < MAX_CONCURRENT_TRANSFERS:
            future = executor.submit(
                preview_transfer_from_account,
                accounts[next_index],
                recipient,
                transfer_amount,
            )
            futures[future] = next_index
            if progress_callback:
                progress_callback({
                    "type": "account_started",
                    "account_number": next_index + 1,
                    "username": accounts[next_index]["username"],
                })
            next_index += 1

        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                index = futures.pop(future)
                try:
                    preview = future.result()
                except Exception as error:
                    preview = {
                        "name": accounts[index]["name"],
                        "username": accounts[index]["username"],
                        "amount": f"₦{transfer_amount:,}",
                        "fee": None,
                        "balance": None,
                        "total": None,
                        "status": "blocked",
                        "message": f"{type(error).__name__}: {error}",
                    }
                previews[index] = preview
                if progress_callback:
                    progress_callback({
                        "type": "account_completed",
                        "account_number": index + 1,
                        "username": preview["username"],
                        "fee": preview["fee"] or "Unknown",
                        "balance": preview["balance"] or "Unknown",
                        "total": preview["total"] or "Unknown",
                        "status": preview["status"],
                        "message": preview["message"],
                    })

            while (
                next_index < len(accounts)
                and len(futures) < MAX_CONCURRENT_TRANSFERS
            ):
                future = executor.submit(
                    preview_transfer_from_account,
                    accounts[next_index],
                    recipient,
                    transfer_amount,
                )
                futures[future] = next_index
                if progress_callback:
                    progress_callback({
                        "type": "account_started",
                        "account_number": next_index + 1,
                        "username": accounts[next_index]["username"],
                    })
                next_index += 1

    return [previews[index] for index in sorted(previews)]


def transfer_from_account(account, recipient, transfer_amount=TRANSFER_AMOUNT):
    result = {
        "name": account["name"],
        "username": account["username"],
        "amount": f"₦{transfer_amount:,}",
        "status": "failed",
        "message": "",
    }
    driver = None
    transfer_submitted = False

    try:
        driver, _, current_balance, fee, send_button = _open_transfer_form(
            account, recipient, transfer_amount
        )
        total = transfer_amount + fee
        if current_balance < total:
            raise ValueError(
                f"Live balance is below transfer plus fee "
                f"(₦{total:,.2f}); transfer skipped."
            )
        send_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[contains(normalize-space(.), 'Send') "
                f"and contains(normalize-space(.), '{transfer_amount:,}')]",
            ))
        )
        transfer_submitted = True
        result["status"] = "uncertain"
        result["message"] = (
            "Transfer submission was attempted; verify the account if status is uncertain."
        )
        send_button.click()
        result["status"] = "submitted"
        result["message"] = "Transfer submitted; completion was not independently confirmed."

        try:
            WebDriverWait(driver, 15).until(
                lambda current_driver: parse_naira(
                    current_driver.find_element(
                        By.XPATH, "//*[contains(text(), '₦')]"
                    ).text
                ) != current_balance
            )
        except (TimeoutException, ValueError):
            pass
        else:
            result["status"] = "confirmed"
            result["message"] = "Balance changed after the transfer submission."

    except (TimeoutException, WebDriverException, ValueError) as error:
        result["status"] = "uncertain" if transfer_submitted else "failed"
        result["message"] = f"{type(error).__name__}: {error}"
    finally:
        if driver is not None:
            try:
                driver.quit()
            except WebDriverException as error:
                cleanup_message = f"Browser cleanup failed: {type(error).__name__}: {error}"
                if transfer_submitted:
                    result["status"] = "uncertain"
                result["message"] = (
                    f"{result['message']} {cleanup_message}".strip()
                )

    return result


def run_transfers(
    accounts,
    recipient,
    progress_callback=None,
    stop_event=None,
    transfer_amount=TRANSFER_AMOUNT,
):
    recipient = recipient.strip().lstrip("@")
    if not recipient or not re.fullmatch(r"[A-Za-z0-9_.-]+", recipient):
        raise ValueError("Recipient must contain only letters, numbers, _, . or -.")
    if not 1 <= len(accounts) <= MAX_TRANSFER_ACCOUNTS:
        raise ValueError(
            f"Upload between 1 and {MAX_TRANSFER_ACCOUNTS} accounts."
        )

    results = {}
    futures = {}
    next_index = 0

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_TRANSFERS) as executor:
        while next_index < len(accounts) and len(futures) < MAX_CONCURRENT_TRANSFERS:
            if stop_event is not None and stop_event.is_set():
                break
            future = executor.submit(
                transfer_from_account,
                accounts[next_index],
                recipient,
                transfer_amount,
            )
            futures[future] = next_index
            if progress_callback:
                progress_callback({
                    "type": "account_started",
                    "account_number": next_index + 1,
                    "username": accounts[next_index]["username"],
                })
            next_index += 1

        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                index = futures.pop(future)
                account_number = index + 1
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        "name": accounts[index]["name"],
                        "username": accounts[index]["username"],
                        "amount": f"₦{transfer_amount:,}",
                        "status": "failed",
                        "message": f"{type(error).__name__}: {error}",
                    }
                results[account_number] = result
                if progress_callback:
                    progress_callback({
                        "type": "account_completed",
                        "account_number": account_number,
                        "username": result["username"],
                        "status": result["status"],
                        "message": result["message"],
                    })

            while (
                next_index < len(accounts)
                and len(futures) < MAX_CONCURRENT_TRANSFERS
                and (stop_event is None or not stop_event.is_set())
            ):
                future = executor.submit(
                    transfer_from_account,
                    accounts[next_index],
                    recipient,
                    transfer_amount,
                )
                futures[future] = next_index
                if progress_callback:
                    progress_callback({
                        "type": "account_started",
                        "account_number": next_index + 1,
                        "username": accounts[next_index]["username"],
                    })
                next_index += 1

    transfer_results = [results[index] for index in sorted(results)]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    report_filename = f"lagos_life_transfer_report_{timestamp}.csv"
    report_buffer = io.StringIO(newline="")
    fieldnames = ["name", "username", "amount", "status", "message"]
    writer = csv.DictWriter(report_buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(transfer_results)

    return {
        "results": transfer_results,
        "csv_content": "\ufeff" + report_buffer.getvalue(),
        "csv_filename": report_filename,
        "stopped": stop_event is not None and stop_event.is_set(),
        "requested": len(accounts),
    }
