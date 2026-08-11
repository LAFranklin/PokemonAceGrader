import subprocess
import sys

scripts = [
    "ebay_coldcomps_scrapper.py",
    "match_pokemon_to_price.py"
]

for script in scripts:
    print(f"\n{'=' * 60}")
    print(f"Running {script}")
    print(f"{'=' * 60}\n")

    result = subprocess.run([sys.executable, script])

    if result.returncode != 0:
        print(f"\nERROR: {script} failed with exit code {result.returncode}")
        sys.exit(result.returncode)

print("\nPipeline completed successfully!")
