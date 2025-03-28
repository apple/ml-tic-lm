# For licensing see accompanying LICENSE file.
# Copyright (C) 2025 Apple Inc. All Rights Reserved.
#

import json

import requests
from bs4 import BeautifulSoup


def fetch_wikidata_properties():
    # URL of the webpage containing the table
    url = (
        "https://www.wikidata.org/wiki/Wikidata:Database_reports/List_of_properties/all"
    )

    # Fetch the webpage
    response = requests.get(url)
    response.raise_for_status()  # Raise an exception for HTTP errors

    # Parse the HTML content of the page
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the table by class or ID (adjust if needed)
    table = soup.find("table", class_="wikitable")

    # Create a dictionary to store the mappings
    id_to_label = {}

    # Loop through each row in the table except the header row
    for row in table.find_all("tr")[1:]:  # skip the header row
        cells = row.find_all("td")
        if len(cells) > 1:
            prop_id = cells[0].text.strip()
            label = cells[1].text.strip()
            id_to_label[prop_id] = label

    return id_to_label


def save_to_json(data, filename):
    # Write data to a JSON file
    with open(filename, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


if __name__ == "__main__":
    # Fetch data
    data = fetch_wikidata_properties()

    # Specify the JSON file name
    filename = "wikidata_properties.json"

    # Save the data to a JSON file
    save_to_json(data, filename)
    print(f"Data has been successfully written to {filename}")
