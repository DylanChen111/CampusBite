import argparse
import json

from .database import DEFAULT_DB, connection, initialize, validate_database
from .repository import FoodRepository


def main():
    parser = argparse.ArgumentParser(description="CampusBite 模拟数据初始化和验证")
    parser.add_argument("command", choices=["init", "check", "query"])
    parser.add_argument("--db", default=str(DEFAULT_DB))
    args = parser.parse_args()
    if args.command == "init":
        result = initialize(args.db)
    elif args.command == "check":
        with connection(args.db) as conn:
            result = validate_database(conn)
    else:
        repo = FoodRepository(args.db)
        result = {"metadata": repo.metadata(), "sample": repo.dishes(budget=15, sort="price")[:3]}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
