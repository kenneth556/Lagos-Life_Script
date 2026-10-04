from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, WebDriverException
import random
import string
import time
import csv
import io
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime

SITE_URL = "https://lagoslife.eliysites.com/"
NUM_ACCOUNTS = 40
MAX_ACCOUNTS_PER_SESSION = 40
MAX_CONCURRENT_ACCOUNTS = 2
TRAITS_TO_SELECT = ("Hustler", "Tech Bro or Sis")


def generate_random_name():
    first_names = [
        "Tolu", "Ade", "Chioma", "Emeka", "Funmi", "Bola", "Yemi", "Ngozi",
        "Kunle", "Amina", "Chika", "Obinna", "Zainab", "Seyi", "Ifeoma",
        "Dayo", "Amaka", "Kelechi", "Lola", "Tunde",
    ]
    last_names = [
        "Adebayo", "Okafor", "Balogun", "Eze", "Ojo", "Ibrahim", "Obi",
        "Kalu", "Musa", "Fashola", "Adeyemi", "Nwosu", "Bello", "Okeke",
        "Lawal", "Umeh", "Danladi", "Bakare", "Onyeka", "Yusuf",
    ]
    return f"{random.choice(first_names)} {random.choice(last_names)}"


def generate_random_username():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))


def generate_random_password():
    return ''.join(random.choices(string.ascii_letters + string.digits + "!@#$%", k=12))


def create_account(account_number):
    data = {
        "name": "",
        "username": "",
        "password": "",
        "balance": "",
    }
    driver = None
    account_created = False
    stage = "Opening sign-up page"

    try:
        print(f"\n--- Creating Account #{account_number} ---")

        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        driver = webdriver.Chrome(options=chrome_options)
        wait = WebDriverWait(driver, 15)

        driver.get(SITE_URL)
        signup_button = wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//*[self::button or self::a][contains(normalize-space(.), 'Sign up')]",
        )))
        signup_button.click()

        stage = "Preparing account details"
        data["name"] = generate_random_name()
        data["username"] = generate_random_username()
        data["password"] = generate_random_password()

        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@placeholder='e.g. Tolu Adebayo']",
        ))).send_keys(data["name"])
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[contains(@placeholder, 'tolu_eko')]",
        ))).send_keys(data["username"])
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@type='password']",
        ))).send_keys(data["password"])

        checkbox = wait.until(EC.presence_of_element_located((
            By.XPATH, "//input[@type='checkbox']",
        )))
        if not checkbox.is_selected():
            driver.execute_script("arguments[0].click();", checkbox)

        wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//button[contains(normalize-space(.), 'Sign up') and contains(normalize-space(.), 'free')]",
        ))).click()
        account_created = True
        stage = "Continuing through onboarding"
        time.sleep(2)

        try:
            wait.until(EC.element_to_be_clickable((
                By.XPATH, "//button[normalize-space(.)='Essential only']",
            ))).click()
        except TimeoutException:
            pass

        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[contains(normalize-space(.), 'Continue')]",
        ))).click()

        stage = "Selecting account traits"
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//*[contains(normalize-space(.), 'Choose 2 traits')]",
        )))
        for trait in TRAITS_TO_SELECT:
            wait.until(EC.element_to_be_clickable((
                By.XPATH, f"//*[normalize-space(text())='{trait}']",
            ))).click()
            time.sleep(0.4)

        stage = "Finalizing selected traits"
        wait.until(lambda current_driver: not current_driver.find_elements(
            By.XPATH,
            "//button[contains(normalize-space(.), 'more') and starts-with(normalize-space(.), 'Choose')]",
        ))
        next_button = driver.find_elements(By.XPATH, "//button[normalize-space(.)='Next']")
        if next_button:
            wait.until(EC.element_to_be_clickable((
                By.XPATH, "//button[normalize-space(.)='Next']",
            ))).click()
        else:
            wait.until(EC.element_to_be_clickable((
                By.XPATH, "//button[contains(normalize-space(.), 'Continue')]",
            ))).click()

        stage = "Completing birth lottery"
        wait.until(EC.element_to_be_clickable((
            By.XPATH, "//button[normalize-space(.)='Continue']",
        ))).click()
        wait.until(EC.presence_of_element_located((
            By.XPATH, "//*[normalize-space(text())='Birth lottery']",
        )))
        stage = "Choosing a place to live"
        wait.until(EC.element_to_be_clickable((
            By.XPATH,
            "//button[contains(normalize-space(.), 'Choose where to live') "
            "or starts-with(normalize-space(.), 'Move in')]",
        ))).click()

        home_heading = driver.find_elements(
            By.XPATH, "//*[normalize-space(text())='Home']"
        )
        if home_heading:
            stage = "Moving into the selected home"
            wait.until(EC.element_to_be_clickable((
                By.XPATH, "(//button[normalize-space(.)='Move in'])[last()]",
            ))).click()

        stage = "Loading the completed account"
        balance_element = wait.until(EC.visibility_of_element_located((
            By.XPATH, "//*[contains(text(), '₦')]",
        )))
        data["balance"] = balance_element.text.strip()
        data["_status"] = "success"
        data["_stage"] = "Onboarding complete"
        data["_message"] = "Account created and onboarding completed."
        print(f"Account {account_number} created: {data['username']}")

    except (TimeoutException, WebDriverException) as error:
        print(f"Error on account {account_number}: {error}")
        if account_created:
            data["_status"] = "onboarding_incomplete"
            data["_stage"] = stage
            data["_message"] = (
                f"Account was created, but onboarding did not finish at {stage}: "
                f"{type(error).__name__}: {error}"
            )
            print("The account was created, but onboarding did not complete.")
        else:
            data["_status"] = "failed"
            data["_stage"] = stage
            data["_message"] = f"{type(error).__name__}: {error}"
    finally:
        if driver is not None:
            driver.quit()

    return data


def run_accounts(num_accounts=NUM_ACCOUNTS, progress_callback=None, stop_event=None):
    if not 1 <= num_accounts <= MAX_ACCOUNTS_PER_SESSION:
        raise ValueError(
            f"Account count must be between 1 and {MAX_ACCOUNTS_PER_SESSION}."
        )

    results = {}
    failed_count = 0
    futures = {}
    next_account = 1

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_ACCOUNTS) as executor:
        while next_account <= num_accounts and len(futures) < MAX_CONCURRENT_ACCOUNTS:
            if stop_event is not None and stop_event.is_set():
                break
            future = executor.submit(create_account, next_account)
            futures[future] = next_account
            if progress_callback:
                progress_callback({"type": "account_started", "account_number": next_account})
            next_account += 1

        while futures:
            completed, _ = wait(futures, return_when=FIRST_COMPLETED)
            for future in completed:
                account_number = futures.pop(future)
                try:
                    account_data = future.result()
                except Exception as error:
                    print(
                        f"Error on account {account_number}: "
                        f"{type(error).__name__}: {error}"
                    )
                    failed_count += 1
                    if progress_callback:
                        progress_callback({
                            "type": "account_failed",
                            "account_number": account_number,
                            "name": "",
                            "username": "",
                            "stage": "Account creation",
                            "message": f"{type(error).__name__}: {error}",
                        })
                    continue

                if account_data:
                    if account_data.get("_status") == "failed":
                        failed_count += 1
                        if progress_callback:
                            progress_callback({
                                "type": "account_failed",
                                "account_number": account_number,
                                "name": account_data["name"],
                                "username": account_data["username"],
                                "stage": account_data.get("_stage", ""),
                                "message": account_data.get("_message", "Account creation failed."),
                            })
                        continue

                    results[account_number] = account_data
                    if progress_callback:
                        progress_callback({
                            "type": "account_completed",
                            "account_number": account_number,
                            "name": account_data["name"],
                            "username": account_data["username"],
                            "status": account_data.get("_status", "success"),
                            "stage": account_data.get("_stage", ""),
                            "message": account_data.get("_message", ""),
                        })
                else:
                    failed_count += 1
                    if progress_callback:
                        progress_callback({
                            "type": "account_failed",
                            "account_number": account_number,
                            "name": "",
                            "username": "",
                            "stage": "Account creation",
                            "message": "Account creation did not complete.",
                        })

            while (
                next_account <= num_accounts
                and len(futures) < MAX_CONCURRENT_ACCOUNTS
                and (stop_event is None or not stop_event.is_set())
            ):
                future = executor.submit(create_account, next_account)
                futures[future] = next_account
                if progress_callback:
                    progress_callback({
                        "type": "account_started",
                        "account_number": next_account,
                    })
                next_account += 1

    all_accounts = [results[number] for number in sorted(results)]
    csv_content = None
    csv_filename = None
    if all_accounts:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        csv_filename = f"lagos_life_accounts_{num_accounts}_{timestamp}.csv"
        csv_buffer = io.StringIO(newline="")
        fieldnames = ["name", "username", "password", "balance"]
        writer = csv.DictWriter(csv_buffer, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {field: account.get(field, "") for field in fieldnames}
            for account in all_accounts
        )
        csv_content = "\ufeff" + csv_buffer.getvalue()

    successful_count = sum(
        account.get("_status") == "success" for account in all_accounts
    )
    incomplete_accounts = [
        {
            "account_number": number,
            "name": account["name"],
            "username": account["username"],
            "stage": account.get("_stage", ""),
            "message": account.get("_message", ""),
        }
        for number, account in sorted(results.items())
        if account.get("_status") == "onboarding_incomplete"
    ]
    return {
        "accounts": all_accounts,
        "successful": successful_count,
        "failed": failed_count,
        "onboarding_incomplete": incomplete_accounts,
        "csv_content": csv_content,
        "csv_filename": csv_filename,
        "stopped": stop_event is not None and stop_event.is_set(),
        "requested": num_accounts,
    }


def main():
    result = run_accounts()
    print(
        f"\nAccount summary: {result['successful']} fully onboarded, "
        f"{result['failed']} failed, "
        f"{len(result['onboarding_incomplete'])} onboarding incomplete."
    )
    if result["csv_content"]:
        print(f"CSV ready in memory: {result['csv_filename']}")
    elif result["stopped"]:
        print("Stopped before any accounts were created; no CSV was written.")


if __name__ == "__main__":
    main()
