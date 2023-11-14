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
    # Creates structured betting data for each game
    games_data = []

    if len(bet_details) != 2:
        raise ValueError("bet_details must contain exactly 2 elements.")

    for i, team_bets in enumerate(bet_details):
        team_name = team1 if i == 0 else team2
        for line_type in ["moneyline", "spread", "total"]:
            bet_value = team_bets.get(line_type, "")
            if bet_value in ["N/A", ""]:
                continue

            price, spread = parse_price_and_spread(bet_value) if line_type != "total" else (bet_value, None)

            # For 'total', set the side based on 'O' for over or 'U' for under
            side = ""
            if line_type == "total":
                ou_split = bet_value.split()
                side = "over" if ou_split[0].startswith("O") else "under"
                line_type = "over/under"  # Adjust the line_type for consistency

            games_data.append({
                "sport_league": sport_league,
                "event_date_utc": event_date_utc,
                "team1": team1,
                "team2": team2,
                "pitcher": "",
                "period": "FULL GAME",
                "line_type": line_type,
                "price": price,
                "side": side if side else team_name,
                "team": team_name,
                "spread": spread if spread else "",
            })

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
			sport_league = league_element.text.strip()  # Atualiza a variável se encontrada
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
			print(event_date_utc)
		except NoSuchElementException:
			pass

		team_elements = div.find_elements(
			By.XPATH,
			".//td[not(@width)]//a[contains(@href, 'betting-trends')]/span[contains(@class, 'text-muted')]"
		)
		teams = [team_element.text.strip() for team_element in team_elements if team_element.text.strip()]
		print(teams)

		bet_tds = div.find_elements(By.XPATH, ".//tr[2]/td")
		if len(bet_tds) == 4:
			bet_info = {
				"team": bet_tds[0].text.strip(),
				"moneyline": bet_tds[1].text.strip(),
				"spread": bet_tds[2].text.strip(),
				"total": bet_tds[3].text.strip(),
			}
		else:
			print(f"Unexpected number of betting data found: {len(bet_tds)}")
			continue

		bet_details = []
		bet_details.append(bet_info)

		if len(teams) == 2:
			structured_bets = create_betting_structure(
				bet_details, sport_league, event_date_utc, teams[0], teams[1]
			)
			items.append(structured_bets)
		else:
			print(f"Unexpected number of teams found: {len(teams)} in div {index}")


driver.quit()

json_output = json.dumps(items, indent=2)
# print(json_output)

with open("output.json", "w") as file:
	file.write(json_output)

print("Data saved in 'output.json'")

# Print the total number of 'incoming events'
print(f"Total incoming events: {len(items)}")
