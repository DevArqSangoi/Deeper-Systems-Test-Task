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


def parse_price_and_spread(bet_value):
    # Parses the price and spread from a string
    if bet_value in ["N/A", ""]:
        return "N/A", "N/A"

    if "O " in bet_value or "U " in bet_value:
        spread, price = bet_value.replace("O ", "").replace("U ", "").split("\n")
    else:
        parts = bet_value.split("\n")
        spread = parts[0]
        price = parts[1] if len(parts) > 1 else spread

    price = price.strip("()")

    try:
        spread = float(spread.replace("½", ".5"))
    except ValueError:
        spread = "N/A"

    return price, spread


def create_betting_structure(bet_details, sport_league, event_date_utc, team1, team2):
    games_data = []

    if len(bet_details) != 2:
        raise ValueError("bet_details must contain exactly 2 elements.")

    # Order of lines should be: moneyline team 1, moneyline team 2, spread team 1, spread team 2, over, under
    # First, handle moneyline and spread for both teams
    for line_type in ["moneyline", "spread"]:
        for i, team_bets in enumerate(bet_details):
            team_name = team1 if i == 0 else team2
            bet_value = team_bets.get(line_type, "N/A")
            price, spread = parse_price_and_spread(bet_value)

            bet_data = {
                "sport_league": sport_league,
                "event_date_utc": event_date_utc,
                "team1": team1,
                "team2": team2,
                "pitcher": "",
                "period": "FULL GAME",
                "line_type": line_type,
                "price": price,
                "side": team_name,
                "team": team_name,
                "spread": spread if line_type == "spread" else "0",
            }
            games_data.append(bet_data)

    # Now, handle over/under separately
    over_under_values = [bet_details[0]["total"], bet_details[1]["total"]]
    for ou_value in over_under_values:
        price, spread = parse_price_and_spread(ou_value)
        side = "over" if "O " in ou_value else "under"
        bet_data = {
            "sport_league": sport_league,
            "event_date_utc": event_date_utc,
            "team1": team1,
            "team2": team2,
            "pitcher": "",
            "period": "FULL GAME",
            "line_type": "over/under",
            "price": price,
            "side": side,
            "team": "total",
            "spread": spread,
        }
        games_data.append(bet_data)

    return games_data


options = Options()
options.headless = True
options.add_argument("--log-level=3")

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
rows = driver.find_elements(By.CSS_SELECTOR, "#odds-picks > tbody > tr")
total_rows = len(rows)
bar_width = 100
# Adding a progress bar for rows processing
for row in tqdm(
    rows,
    desc="Scraping data",
    unit="%",
    total=total_rows,
    ncols=bar_width,
    bar_format="{l_bar}{bar}| {percentage:3.0f}%",
):
    # Tente encontrar as duas divisões que representam as tabelas de aposta dentro da row
    betting_divs = row.find_elements(By.XPATH, ".//div[@class='col col-md']")

    for index, div in enumerate(betting_divs):
        try:
            # Tente encontrar o elemento da liga esportiva na tabela de aposta
            league_element = div.find_element(
                By.XPATH,
                ".//span[contains(@class, 'text-muted') and contains(@class, 'text-wrap') and contains(@class, 'text-left')]/a",
            )
            sport_league = (
                league_element.text.strip()
            )  # Atualiza a variável se encontrada
        except NoSuchElementException:
            pass  # Mantém o valor padrão de sport_league se o elemento não for encontrado

        try:
            # Tente encontrar o elemento da data na tabela de aposta
            date_element = div.find_element(
                By.XPATH,
                ".//span[contains(@class, 'badge-light') and contains(@class, 'text-wrap') and contains(@class, 'text-left')]",
            )
            date = date_element.text.strip()
            event_date_utc = convert_to_utc(date)  # Atualiza a variável se encontrada
        except NoSuchElementException:
            pass

        team_elements = div.find_elements(
            By.XPATH,
            ".//td[not(@width)]//a[contains(@href, 'betting-trends')]/span[contains(@class, 'text-muted')]",
        )
        teams = [
            team_element.text.strip()
            for team_element in team_elements
            if team_element.text.strip()
        ]

        # Encontra todos os tds dentro do tr que contém os valores de aposta
        # Localizar o tr que contém as informações de aposta
        bet_trs = div.find_elements(
            By.XPATH, ".//table/tbody/tr[position()=2 or position()=3]"
        )

        bet_details = []
        for bet_tr in bet_trs:
            bet_tds = bet_tr.find_elements(By.XPATH, "./td[@width='54']")

            if len(bet_tds) == 3:
                bet_info = {
                    "moneyline": bet_tds[0].text.strip(),
                    "spread": bet_tds[1].text.strip(),
                    "total": bet_tds[2].text.strip(),
                }
                bet_details.append(bet_info)
            else:
                print(
                    f"Unexpected number of betting info found: {len(bet_tds)} in bet_tr"
                )

        # Verifique se temos dois conjuntos de detalhes de aposta para os dois times
        if len(bet_details) == 2:
            structured_bets = create_betting_structure(
                bet_details, sport_league, event_date_utc, teams[0], teams[1]
            )

            items.append(structured_bets)
        else:
            print(f"Unexpected number of bet details found: {len(bet_details)} in div")

driver.quit()

json_output = json.dumps(items, indent=2)
# print(json_output)

with open("output.json", "w") as file:
    file.write(json_output)

print("Data saved in 'output.json'")

# Print the total number of 'incoming events'
print(f"Total incoming events: {len(items)}")
