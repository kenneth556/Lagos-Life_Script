from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import random
import string
import time
import csv
import os
import re

SITE_URL = "https://lagoslife.eliysites.com/"
RECIPIENT = "papa_himself"
LOW_BALANCE_THRESHOLD = 100_000
LOW_BALANCE_TRANSFER_AMOUNT = "71000"
HIGH_BALANCE_TRANSFER_AMOUNT = "475000"
TRAITS_TO_SELECT = ("Hustler", "Tech Bro or Sis")

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
CSV_PATH = os.path.join(DESKTOP, "lagos_life_account.csv")
ERROR_SCREENSHOT = os.path.join(DESKTOP, "lagos_life_error.png")


# Generate random credentials
def generate_random_name():
    first_names = ["Tolu", "Ade", "Chioma", "Emeka", "Funmi", "Bola", "Yemi", "Ngozi", "Kunle", "Amina"]
    last_names = ["Adebayo", "Okafor", "Balogun", "Eze", "Ojo", "Ibrahim", "Obi", "Kalu", "Musa", "Fashola"]
    return f"{random.choice(first_names)} {random.choice(last_names)}"

def generate_random_username():
    # No leading "@": the site shows its own "@" prefix next to the username box.
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

def generate_random_password():
    return ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=12))


# Helpers
# Use normalize-space(.) instead of text(): React buttons often wrap their label
# in a <span>, so text() on the button itself is empty and never matches.
def clickable(xpath, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.XPATH, xpath)))

def present(xpath, timeout=15):
    return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xpath)))

def click(xpath, timeout=15):
    el = clickable(xpath, timeout)
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
    el.click()
    return el

def try_click(xpath, timeout=5):
    """Click if the element shows up, otherwise carry on (for optional steps)."""
    try:
        click(xpath, timeout)
        return True
    except TimeoutException:
        return False

def wait_for(xpath, timeout=5):
    """True if the element appears within the timeout, otherwise False (no error)."""
    try:
        present(xpath, timeout)
        return True
    except TimeoutException:
        return False

def read_balance(timeout=15):
    """Return the text of the first visible element showing a ₦ amount."""
    el = WebDriverWait(driver, timeout).until(
        EC.visibility_of_element_located((By.XPATH, "//*[contains(text(), '₦')]"))
    )
    return el.text.strip()

def balance_to_number(balance_text):
    """Convert a displayed Naira balance such as '₦95,950' to an integer."""
    match = re.search(r"₦\s*([\d,]+(?:\.\d{1,2})?)", balance_text)
    if not match:
        raise ValueError(f"Could not parse Naira balance: {balance_text!r}")
    return float(match.group(1).replace(",", ""))


# Initialize browser
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
driver = webdriver.Chrome(options=chrome_options)

# Data storage
data = {
    "name": "",
    "username": "",
    "password": "",
    "birth_lottery": "",
    "opening_balance": "",
    "balance_after_transfer": "",
    "closing_balance": "",
    "status": "started",
}

try:
    # Step 1: Navigate to Lagos Life (it's a JS app, wait for it to boot)
    driver.get(SITE_URL)

    # Step 2: Click Sign up (may be a <button> or an <a>)
    click("//*[self::button or self::a][contains(normalize-space(.), 'Sign up')]", timeout=40)

    # Step 3: Fill in random credentials
    data["name"] = generate_random_name()
    data["username"] = generate_random_username()
    data["password"] = generate_random_password()

    present("//input[@placeholder='e.g. Tolu Adebayo']").send_keys(data["name"])
    # FIX: the "@" is a separate label, so the placeholder is just "tolu_eko".
    driver.find_element(By.XPATH, "//input[contains(@placeholder, 'tolu_eko')]").send_keys(data["username"])
    driver.find_element(By.XPATH, "//input[@type='password']").send_keys(data["password"])

    # Step 4: Tick 18+ checkbox (click via JS in case it's visually hidden behind a styled box)
    checkbox = driver.find_element(By.XPATH, "//input[@type='checkbox']")
    if not checkbox.is_selected():
        driver.execute_script("arguments[0].click();", checkbox)

    # Step 5: Click "Sign up - it's free"
    # FIX: the original XPath put "it's" inside single quotes, which is invalid XPath.
    # Match on the parts without the apostrophe instead.
    click("//button[contains(normalize-space(.), 'Sign up') and contains(normalize-space(.), 'free')]")
    data["status"] = "account created"

    # Dismiss the cookie banner (bottom-left) so it can't cover anything we click
    try_click("//button[normalize-space(.)='Essential only']", timeout=3)

    # Step 6: Click Continue on looks page
    click("//button[contains(normalize-space(.), 'Continue')]", timeout=20)

    # Step 7: Personality page - "Choose 2 traits". The bottom button stays
    # disabled ("Choose 2 more") until exactly 2 cards are selected.
    present("//*[contains(normalize-space(.), 'Choose 2 traits')]", timeout=20)
    for trait in TRAITS_TO_SELECT:
        click(f"//*[normalize-space(text())='{trait}']")
        time.sleep(0.4)
    # Wait until the page accepts the selection (the "Choose N more" label goes away)
    WebDriverWait(driver, 5).until(
        lambda d: not d.find_elements(By.XPATH, "//button[contains(normalize-space(.), 'more') and starts-with(normalize-space(.), 'Choose')]")
    )
    # Move on: the top-right "Next" button (falls back to the bottom button / Continue)
    if not try_click("//button[normalize-space(.)='Next']"):
        try_click("//button[contains(normalize-space(.), 'Continue')]")

    # Step 8: "Dream" page - one is already selected by default, so just Continue.
    click("//button[normalize-space(.)='Continue']", timeout=20)

    # Step 9: "Birth lottery" page - random outcome, decided once per account.
    #   - LAPO Baby -> button "Choose where to live" (then a Home page follows)
    #   - Nepo Baby -> button "Move into your Lekki flat" (goes straight in)
    present("//*[normalize-space(text())='Birth lottery']", timeout=20)
    time.sleep(1)
    try:
        data["birth_lottery"] = present("(//h1 | //h2 | //h3)[not(contains(., 'Birth lottery'))]", timeout=3).text.strip()
    except TimeoutException:
        pass
    print(f"Birth lottery: {data['birth_lottery'] or 'unknown'}")
    click("//button[contains(normalize-space(.), 'Choose where to live') or starts-with(normalize-space(.), 'Move in')]")

    # Step 9b: "Home" page (only after "Choose where to live") - keep the
    # pre-selected home and just Move in.
    if wait_for("//*[normalize-space(text())='Home']", timeout=5):
        time.sleep(1)
        # [last()] = the big bottom "Move in" button (there's also one top-right)
        click("(//button[normalize-space(.)='Move in'])[last()]")

    # Step 10: Get opening balance from top right
    # FIX: no more made-up fallback numbers - if it can't be read, the script stops.
    data["opening_balance"] = read_balance(timeout=30)
    opening_balance = balance_to_number(data["opening_balance"])
    if opening_balance < LOW_BALANCE_THRESHOLD:
        transfer_amount = LOW_BALANCE_TRANSFER_AMOUNT
    elif opening_balance > LOW_BALANCE_THRESHOLD:
        transfer_amount = HIGH_BALANCE_TRANSFER_AMOUNT
    else:
        raise ValueError(
            f"Opening balance is exactly ₦{LOW_BALANCE_THRESHOLD:,}; "
            "no transfer amount is configured for this balance."
        )
    print(f"Opening balance: {data['opening_balance']}")
    print(f"Transfer amount selected: ₦{int(transfer_amount):,}")

    # Step 11: Open phone
    click("//*[self::button or self::a][contains(normalize-space(.), 'Phone') or @id='phone' or contains(@class, 'phone') or contains(@aria-label, 'hone')]")

    # Step 12: Open messages
    click("//*[contains(normalize-space(.), 'Messages') and not(*[contains(normalize-space(.), 'Messages')])]")

    # Step 13: Search for the recipient
    search_box = present(
        "//input[@type='search' or contains(@placeholder, 'Search') "
        "or contains(@placeholder, 'search') or contains(@placeholder, '@username') "
        "or contains(@placeholder, 'Message someone')]"
    )
    search_box.send_keys(RECIPIENT)

    # Step 14: Open the recipient's chat (case-insensitive match)
    lower = "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    click(f"//*[contains({lower}, '{RECIPIENT}') and not(self::input) and not(*[contains({lower}, '{RECIPIENT}')])]")

    # Step 15: Click send money
    click("//button[contains(normalize-space(.), 'Send money')]")

    # Step 16: Enter amount and confirm
    amount_field = present("//input[@type='number' or @inputmode='numeric' or contains(@placeholder, 'mount')]")
    amount_field.clear()
    amount_field.send_keys(transfer_amount)

    # FIX: the original "contains 'Send'" could re-click the "Send money" button.
    # Prefer an exact "Send"/"Confirm" button, i.e. the one inside the transfer form.
    click("(//button[normalize-space(.)='Send' or normalize-space(.)='Confirm' or starts-with(normalize-space(.), 'Send ₦')])[last()]")
    data["status"] = "transfer submitted"

    # Step 17: Get balance after transfer (wait for it to actually change)
    try:
        WebDriverWait(driver, 15).until(lambda d: read_balance(5) != data["opening_balance"])
    except TimeoutException:
        print("Warning: balance did not change after the transfer - it may have been rejected.")
        data["status"] = "transfer submitted, balance unchanged"
    data["balance_after_transfer"] = read_balance()

    # Close the phone / let the UI settle, then read the final closing balance
    time.sleep(2)
    data["closing_balance"] = read_balance()
    if data["status"] == "transfer submitted":
        data["status"] = "completed"

    print("Automation completed successfully!")

except (TimeoutException, NoSuchElementException) as e:
    print(f"Stopped: couldn't find an element on the page ({type(e).__name__}).")
    print(f"Current URL: {driver.current_url}")
    driver.save_screenshot(ERROR_SCREENSHOT)
    print(f"Screenshot of where it got stuck: {ERROR_SCREENSHOT}")
    data["status"] = f"failed after: {data['status']}"

except Exception as e:
    print(f"Error occurred: {e}")
    print(f"Current URL: {driver.current_url}")
    data["status"] = f"error after: {data['status']}"

finally:
    print(f"Name: {data['name']}")
    print(f"Username: {data['username']}")
    print(f"Password: {data['password']}")
    print(f"Opening Balance: {data['opening_balance']}")
    print(f"Closing Balance: {data['closing_balance']}")

    # Step 18: Create CSV on desktop
    # FIX: always saved (even on failure) so you keep the login of any account
    # that was created; utf-8-sig so the ₦ sign doesn't crash on Windows and
    # shows correctly in Excel.
    if data["username"]:
        with open(CSV_PATH, 'w', newline='', encoding='utf-8-sig') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=list(data.keys()))
            writer.writeheader()
            writer.writerow(data)
        print(f"CSV file created at: {CSV_PATH}")

    time.sleep(5)  # Keep browser open for a moment to see result
    driver.quit()