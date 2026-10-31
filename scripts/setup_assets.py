"""Download local category illustration photos, never actual mock dish evidence."""

import urllib.request
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "frontend" / "public" / "images"
SOURCES = {
    "rice": "photo-1512058564366-18510be2db19",
    "noodles": "photo-1569718212165-3a8278d5f624",
    "salad": "photo-1546069901-ba9599a7e63c",
    "sichuan": "photo-1525755662778-989d0524087e",
    "breakfast": "photo-1533089860892-a7c6f0a88666",
    "night": "photo-1547592180-85f173990554",
}


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, source in SOURCES.items():
        url = f"https://images.unsplash.com/{source}?auto=format&fit=crop&w=1400&q=85"
        path = TARGET / f"{name}.jpg"
        urllib.request.urlretrieve(url, path)
        print(f"{name}: {path.stat().st_size} bytes; {url}")


if __name__ == "__main__":
    main()
