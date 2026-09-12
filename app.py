from datetime import datetime
from flask import Flask, render_template
import pandas as pd
import plotly
import plotly.graph_objects as go
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from bs4 import BeautifulSoup

app = Flask(__name__)

# Prevent browser and server-side caching
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def scrape_all_prediction_data():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    url = "https://predictionmarketspicks.com/tools/fed-rate-tracker/september-2026"

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "table"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")
        tables = soup.find_all("table")

        historical_df = None
        divergence_df = None

        for tbl in tables:
            text = tbl.get_text()

            # 1. Scrape Cross-Market Divergence Table
            if "Outcome" in text and "50bp+" in text and ("cut" in text or "hike" in text):
                rows = tbl.find_all("tr")
                parsed_div = []
                div_headers = ["Outcome", "Kalshi", "Polymarket", "Futures", "Spread"]
                for row in rows:
                    cols = row.find_all(["td", "th"])
                    col_texts = [c.get_text(strip=True) for c in cols]
                    if len(col_texts) >= 5 and not any(h in col_texts[0] for h in ["Outcome"]):
                        parsed_div.append(col_texts[:5])
                if parsed_div:
                    divergence_df = pd.DataFrame(parsed_div, columns=div_headers)

            # 2. Scrape Historical Daily Closes Table
            elif "Kalshi" in text and "Polymarket" in text and "Futures" in text and ("Sep" in text or "Aug" in text or "Day" in text):
                rows = tbl.find_all("tr")
                parsed_data = []
                headers = ["Day", "Kalshi", "Polymarket", "Futures", "Spread"]

                for row in rows:
                    cols = row.find_all(["td", "th"])
                    col_texts = [c.get_text(strip=True) for c in cols]

                    if len(col_texts) >= 4:
                        while len(col_texts) < 5:
                            col_texts.append("")
                        parsed_data.append(col_texts[:5])

                if parsed_data:
                    df_temp = pd.DataFrame(parsed_data, columns=headers)
                    df_temp = df_temp[~df_temp["Day"].str.lower().isin(["day", "format"])].reset_index(drop=True)
                    if not df_temp.empty:
                        historical_df = df_temp

        if historical_df is None and len(tables) > 1:
            target_table = tables[1]
            rows = target_table.find_all("tr")
            parsed_data = []
            headers = ["Day", "Kalshi", "Polymarket", "Futures", "Spread"]
            for row in rows:
                cols = row.find_all(["td", "th"])
                col_texts = [c.get_text(strip=True) for c in cols]
                if len(col_texts) >= 4:
                    while len(col_texts) < 5:
                        col_texts.append("")
                    parsed_data.append(col_texts[:5])
            if parsed_data:
                df_temp = pd.DataFrame(parsed_data, columns=headers)
                historical_df = df_temp[~df_temp["Day"].str.lower().isin(["day", "format"])].reset_index(drop=True)

        return historical_df, divergence_df

    except Exception as e:
        print(f"Scraping exception: {e}")
        return None, None
    finally:
        driver.quit()


def scrape_bull_bear_case():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(options=options)
    url = "https://predictionmarketspicks.com/tools/fed-rate-tracker/september-2026"

    try:
        driver.get(url)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        soup = BeautifulSoup(driver.page_source, "html.parser")
        
        container = None
        for div in soup.find_all("div"):
            text = div.get_text()
            if "BULL / BEAR CASE" in text and "Bull Case" in text and "Bear Case" in text:
                container = div
                break
        
        if not container:
            return None

        full_text = container.get_text()
        cut_prob = ""
        hold_text = ""
        
        for line in full_text.split('\n'):
            line_str = line.strip()
            if "Cut probability:" in line_str or ("probability:" in line_str and "%" in line_str):
                parts = line_str.split(":")
                if len(parts) > 1:
                    tokens = parts[1].strip().split()
                    if tokens:
                        cut_prob = tokens[0]
                        hold_text = " ".join(tokens[1:])

        bull_items = []
        bear_items = []
        
        lists = container.find_all("ul")
        if lists:
            for ul in lists:
                items = [li.get_text(strip=True) for li in ul.find_all("li")]
                ul_parent_text = ul.parent.get_text()
                if "Bull Case" in ul_parent_text and not "Bear Case" in ul_parent_text:
                    bull_items.extend(items)
                elif "Bear Case" in ul_parent_text and not "Bull Case" in ul_parent_text:
                    bear_items.extend(items)
                else:
                    if not bull_items:
                        bull_items = items
                    else:
                        bear_items = items

        if not bull_items and not bear_items:
            lines = [l.strip() for l in full_text.split('\n') if l.strip()]
            current_section = None
            for l in lines:
                if "Bull Case" in l:
                    current_section = "bull"
                    continue
                elif "Bear Case" in l:
                    current_section = "bear"
                    continue
                
                if current_section == "bull" and ("—" in l or len(l) > 5):
                    bull_items.append(l.lstrip("• -"))
                elif current_section == "bear" and ("—" in l or len(l) > 5):
                    bear_items.append(l.lstrip("• -"))

        return {
            "date_range": "Sep 15–16, 2026",
            "cut_probability": cut_prob,
            "hold_hike_text": hold_text,
            "bull_items": bull_items,
            "bear_items": bear_items
        }
    except Exception as e:
        print(f"Bull/Bear scraping exception: {e}")
        return None
    finally:
        driver.quit()


@app.route("/")
def index():
    df, divergence_df = scrape_all_prediction_data()

    if df is None or df.empty:
        return "Error: Historical prediction dataset could not be scraped. Check console logs.", 500

    table_data = df.to_dict(orient="records")
    table_columns = df.columns.tolist()

    divergence_data = (
        divergence_df.to_dict(orient="records")
        if divergence_df is not None and not divergence_df.empty
        else []
    )
    divergence_columns = divergence_df.columns.tolist() if divergence_df is not None else []
    
    bull_bear_data = scrape_bull_bear_case()

    return render_template(
        "index.html",
        table_data=table_data,
        table_columns=table_columns,
        divergence_data=divergence_data,
        divergence_columns=divergence_columns,
        bull_bear_data=bull_bear_data,
        last_updated=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


if __name__ == "__main__":
    app.run(debug=True, port=5000)