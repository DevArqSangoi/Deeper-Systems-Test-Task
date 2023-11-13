import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from tqdm import tqdm
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import sys


@dataclass
class Item:
    # Data class to represent a betting item
    sport_league: str = ""
    event_date_utc: str = ""
    team1: str = ""
    team2: str = ""
    pitcher: str = ""
    period: str = ""
    line_type: str = ""
    price: str = ""
    side: str = ""
    team: str = ""
    spread: float = 0.0


def convert_to_utc(date_str):
    # Converts a date string to UTC format
    date_str = date_str.replace("ET", "").strip()

    if "(" in date_str and ")" in date_str:
        time_part, date_part = date_str.split("(")
        date_str = date_part.strip(")") + " " + time_part.strip()
        format_str = "%m/%d/%Y %I:%M %p"
    else:
        today = datetime.now()
        date_str = f"{today.strftime('%m/%d/%Y')} {date_str}"
        format_str = "%m/%d/%Y %I:%M %p"

    local_date = datetime.strptime(date_str, format_str)
    utc_date = local_date - timedelta(hours=5)

    return utc_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def parse_price_and_spread(value):
    # Parses the price and spread from a string
    if value == "N/A":
        return "", 0.0

    parts = value.split("\n")
    price = parts[1].strip("()") if len(parts) > 1 else ""
    spread_part = parts[0].split(" ")[-1] if parts[0] else "0"
    spread = 0.0 if spread_part == "N/A" else float(spread_part)

    return price, spread


def create_betting_structure(bet_details, sport_league, event_date_utc, team1, team2):
    # Creates structured betting data for each game, including N/A values
    games_data = []

    for i in range(0, len(bet_details), 2):
        game_data = []
        for line_type in ["moneyline", "spread", "over/under"]:
            for j in range(2):
                team = bet_details[i + j]

                price, spread = (
                    ("N/A", 0)
                    if team[line_type] == "N/A"
                    else parse_price_and_spread(team[line_type])
                )
                if line_type == "moneyline":
                    price = team[line_type] if team[line_type] != "N/A" else "N/A"

                if line_type == "over/under":
                    ou_split = team[line_type].split("\n")
                    side = "over" if ou_split[0].startswith("O") else "under"
                    team_name = "total"
                else:
                    side = team1 if j == 0 else team2
                    team_name = side

                game_data.append(
                    {
                        "sport_league": sport_league,
                        "event_date_utc": event_date_utc,
                        "team1": team1,
                        "team2": team2,
                        "pitcher": "",
                        "period": "FULL GAME",
                        "line_type": line_type,
                        "price": price,
                        "side": side,
                        "team": team_name,
                        "spread": spread,
                    }
                )

        if game_data:
            games_data.append(game_data)

    return games_data


options = Options()
options.headless = True
options.add_argument(
    "--log-level=3"
)  

service = Service(ChromeDriverManager().install())
if sys.platform == "win32":
    service.log_path = "NUL"
else:
    service.log_path = os.devnull

driver = webdriver.Chrome(service=service, options=options)
driver.get("https://veri.bet/odds-picks?filter=upcoming")

wait = WebDriverWait(driver, 30)
wait.until(EC.visibility_of_element_located((By.ID, "odds-picks_wrapper")))

items = []
rows = driver.find_elements(By.CSS_SELECTOR, "tr[role='row']")
total_rows = len(rows)
bar_width = 100

# Adding a progress bar for rows processing
for row in tqdm(rows, desc="Scraping data", unit="%", total=total_rows, ncols=bar_width, bar_format='{l_bar}{bar}| {percentage:3.0f}%'):
    try:
        league_xpath = ".//td/div/div/div/div[1]/div/div/div/div/table/tbody/tr[4]/td[1]/table/tbody/tr/td/span[@class='text-muted text-wrap text-left']/a"
        league_element = row.find_element(By.XPATH, league_xpath)
        sport_league = league_element.text.strip()
    except NoSuchElementException:
        sport_league = "Unknown"

    try:
        date_xpath = ".//td/div/div/div/div[1]/div/div/div/div/table/tbody/tr[4]/td[1]/table/tbody/tr/td/span[@class='badge badge-light text-wrap text-left']"
        date_element = row.find_element(By.XPATH, date_xpath)
        date = date_element.text.strip()
        event_date_utc = convert_to_utc(date)
    except NoSuchElementException:
        continue

    teams = []
    j = 1
    while True:
        try:
            team_xpath_1 = f".//div[div[{j}]]/div/table/tbody/tr[2]/td[1]/table/tbody/tr/td/table/tbody/tr/td[1]/a/span"
            team_xpath_2 = f".//div[div[{j}]]/div/table/tbody/tr[3]/td[1]/table/tbody/tr/td/table/tbody/tr/td[1]/a/span"

            team_element_1 = row.find_element(By.XPATH, team_xpath_1)
            team_element_2 = row.find_element(By.XPATH, team_xpath_2)

            team1 = team_element_1.text.strip()
            team2 = team_element_2.text.strip()

            teams.extend([team1, team2])

            j += 1

        except NoSuchElementException:
            break

    bet_details = []
    for j in range(1, 3):
        for k in range(2, 4):
            bet_info = {"moneyline": "", "spread": "", "over/under": ""}

            for l in range(2, 5):
                try:
                    bet_xpath = f".//div[div[{j}]]/div/table/tbody/tr[{k}]/td[{l}]/table/tbody/tr/td/span"
                    bet_element = row.find_element(By.XPATH, bet_xpath)
                    bet_text = bet_element.text.strip()

                    if l == 2:
                        bet_info["moneyline"] = bet_text
                    elif l == 3:
                        bet_info["spread"] = bet_text
                    elif l == 4:
                        bet_info["over/under"] = bet_text

                except NoSuchElementException:
                    continue

            bet_details.append(bet_info)

    structured_bets = create_betting_structure(
        bet_details, sport_league, event_date_utc, teams[0], teams[1]
    )
    items.extend(structured_bets)

driver.quit()

json_output = json.dumps(items, indent=2)
print(json_output)

with open("output.json", "w") as file:
    file.write(json_output)

print("Data saved in 'output.json'")

# Print the total number of 'incoming events'
print(f"Total incoming events: {len(items)}")
