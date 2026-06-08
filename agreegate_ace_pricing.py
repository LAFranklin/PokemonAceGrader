import csv
from collections import defaultdict

def clean_price(p):
    if not p:
        return 0.0
    p = p.replace("£", "").replace(",", "").strip()
    return float(p)

def load_ace_prices(path):
    """
    Loads pokemon_ace_mapped_prices.csv and aggregates prices by:
    { id: { "ACE 8": [...], "ACE 9": [...], "ACE 10": [...] } }
    """
    ace_data = defaultdict(lambda: defaultdict(list))

    def clean_price(p):
        if not p:
            return 0.0
        p = p.replace("£", "").replace(",", "").strip()
        return float(p)

    with open(path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        for row in reader:
            card_id = row["id"]
            grade = row["grade"]
            price = clean_price(row["price"])

            ace_data[card_id][grade].append(price)

    return ace_data


def compute_average(prices):
    if not prices:
        return ""
    return round(sum(prices) / len(prices), 2)


def update_pokemon_cards(cards_path, ace_data, output_path):
    """
    Reads pokemon_cards_full.csv, updates ace8_estimate, ace9_estimate, ace10_estimate,
    and writes to a new CSV.
    """
    rows = []

    with open(cards_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames

        # Ensure estimate columns exist
        needed_cols = ["ace8_estimate", "ace9_estimate", "ace10_estimate"]
        for col in needed_cols:
            if col not in fieldnames:
                fieldnames.append(col)

        for row in reader:
            card_id = row["id"]

            # Get ACE prices for this card
            grades = ace_data.get(card_id, {})

            row["ace8_estimate"] = compute_average(grades.get("ACE 8", []))
            row["ace9_estimate"] = compute_average(grades.get("ACE 9", []))
            row["ace10_estimate"] = compute_average(grades.get("ACE 10", []))

            rows.append(row)

    # Write updated CSV
# Write updated CSV
    with open(output_path, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fieldnames,
            extrasaction="ignore"
        )

        writer.writeheader()
        writer.writerows(rows)

    print(f"Updated file written to {output_path}")


def main():
    ace_prices_path = "pokemon_ace_mapped_prices.csv"
    cards_path = "pokemon_cards_full.csv"
    output_path = "pokemon_cards_full_updated.csv"

    ace_data = load_ace_prices(ace_prices_path)
    update_pokemon_cards(cards_path, ace_data, output_path)


if __name__ == "__main__":
    main()
